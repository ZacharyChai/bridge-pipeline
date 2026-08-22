# DECISIONS.md

Every non-obvious choice made during the dbt/Snowflake rebuild: the decision, the alternatives
considered, why this one, and what would change the answer. Organized by phase, in the order
the work actually happened — that order is itself part of the story (several entries exist
*because* something built in an earlier phase surfaced a problem that changed a later one, e.g.
Phase 2's vintage-cap discovery reshaping the ingest design, or Phase 4/5's two incidents
reshaping how seeds and CI are configured). `INTERVIEW_NOTES.md` is the short, spoken-register
companion to this document — grain statements in one sentence, the three hardest problems, the
questions an interviewer would actually ask. This file is the long-form backing for those
answers.

**Contents**: [Phase 1](#phase-1-snowflake-connection-and-the-duckdb-fallback) (Snowflake vs.
alternatives, DuckDB fallback, warehouse sizing) · [Phase 2](#phase-2-ingestion-into-the-raw-layer)
(series selection, the ALFRED vintage-cap discovery, idempotency, a real merge-key bug) ·
[Phase 3](#phase-3-staging-layer) (materialization, missing-value handling, DuckDB seeds) ·
[Phase 4](#phase-4-dimensional-marts) (grain statements, star vs. snowflake, the SCD Type 2
approach, surrogate keys, derived measures, a real production-data incident) ·
[Phase 5](#phase-5-testing-and-data-quality) (test severity policy, distributional bounds, a
second real incident) · [Phase 6](#phase-6-ci-and-documentation) (CI design, why docs build
against DuckDB, the lineage image, final verified status) ·
[Phase 8](#phase-8-orchestration) (Airflow vs. Dagster, LocalExecutor vs. managed/Celery, why
the live GCE cron entry stays put, idempotent backfills, real bugs hit standing this up).

---

## Phase 1: Snowflake, connection, and the DuckDB fallback

### Why Snowflake over BigQuery or Redshift

Snowflake was the brief's default and is kept for three reasons specific to this project's goal
(a portfolio piece for AE/data-analyst roles, not a production system):

- **Warehouse-native dbt story.** Snowflake's separation of storage and compute, and its
  time-travel/cloning features, are commonly discussed in dbt-adjacent interviews. BigQuery is
  an equally strong choice for the same reason and would have been fine; Snowflake was picked
  because it's the more common ask in the specific postings this project targets.
- **Trial economics fit a part-time build.** A 30-day free-credit trial with pause-friendly XS
  warehouses (see sizing below) covers the 6-8 week build if usage stays disciplined — but the
  DuckDB fallback (below) is what actually makes the trial's time limit a non-issue.
- **Redshift rejected**: its per-node pricing has no serverless/pause-on-idle trial-friendly
  tier as clean as Snowflake's `AUTO_SUSPEND`, and it's a less common ask in the target postings
  than Snowflake or BigQuery.

What would change the answer: if the target postings shifted toward a specific cloud (e.g. all
AWS shops wanting Redshift, or GCP shops wanting BigQuery), the warehouse choice would follow the
postings, since the dbt modeling work — the actual point of this project — is nearly identical
across all three.

### Why a DuckDB fallback exists

The Snowflake trial is time- and credit-limited. A portfolio repo that stops working the moment
the trial expires is a liability, not an asset — a recruiter cloning it six months from now must
get a working build. `dbt-duckdb` lets the entire project (same models, same tests) run against a
local file with zero cloud account, selected via `DBT_TARGET=duckdb` (the default) versus
`DBT_TARGET=snowflake`. This is a dbt target swap, not a second codebase — Phase 4's dimensional
models are written once and validated against both.

Alternative considered and rejected: documenting "you'll need your own Snowflake trial to run
this" in the README. Rejected because it fails the Phase 6 acceptance bar directly ("a stranger
can clone the repo and get a working build in under five minutes") and because most of this
project's audience (recruiters, interviewers skimming a repo) will not sign up for a trial just
to evaluate it.

### Warehouse sizing rationale

`BRIDGE_WH` is **XSMALL** with `AUTO_SUSPEND = 60` seconds and `AUTO_RESUME = TRUE`
(`infra/snowflake_setup.sql`). Rationale:

- 15-25 series, full-history daily-to-quarterly observations, is at most a few hundred thousand
  rows in `RAW` and far less after aggregation in `MARTS`. XS (the smallest size, 1 credit/hour
  while running) is not a compromise here — a larger warehouse would not make a `dbt build` over
  this data meaningfully faster, only more expensive.
- 60-second auto-suspend (versus Snowflake's 600-second/10-minute default) means the warehouse
  bills for compute only during the seconds it's actually executing a query, not for 10 minutes
  of idle time after every `dbt build`. This is the single biggest lever against burning trial
  credits during iterative development, where `dbt run` gets invoked dozens of times a day.
- **Cost estimate**: a `dbt build` over this project's model count typically completes in well
  under a minute of actual warehouse-active time. Even at a generous 5 minutes/day of active
  compute (accounting for iteration during active development), that's ~2.5 hours of XS compute
  a month — roughly 2.5 Snowflake credits, on the order of **$5-10/month** at standard
  per-credit pricing (varies by cloud/region/edition). Comfortably inside the trial's free
  credits, and cheap enough to keep running briefly past the trial if needed. This is an
  estimate, not a bill — actual spend should be checked against Snowflake's usage dashboard once
  the account exists.

**Verification status: verified live, 2026-08-06.** `infra/snowflake_setup.sql` ran clean
against the real trial account. `SHOW WAREHOUSES LIKE 'BRIDGE_WH'` confirms `size=X-Small,
auto_suspend=60, auto_resume=true, state=SUSPENDED` — not running, not billing, exactly as
designed. `dbt debug --target snowflake` passes end to end (account, role, warehouse, database
all resolve and connect).

One signup wrinkle worth recording since it cost real time: Snowflake's signup page has two
unrelated products behind two tabs — "AI Data Cloud / For Enterprise" (the $400-credit
warehouse trial this project needs, no card required) and "Snowflake CoCo / For Developers"
(Snowflake's own AI coding agent, a *different* product with its own paid-after-trial CLI
subscription, which is why it asked for a card). Easy to pick the wrong one since both live on
the same signup flow.

---

## Phase 2: Ingestion into the RAW layer

### Why these series

17 series, verified one-by-one against the live FRED `/fred/series` metadata endpoint before
being added to `ingest/series.py` — not guessed from memory or a search-results title (early
candidates like FRED's discontinued `DRTSCREL` or the wrong SLOOS code would have looked
plausible without that check). The full verification output is in the Phase 2 implementation
history; the resulting catalog:

| Group | Series | Why |
|---|---|---|
| Treasury curve | `DGS3MO`, `DGS1`, `DGS2`, `DGS5`, `DGS10`, `DGS30` | Six points across the curve — enough to compute short/long spreads and see inversion, without every maturity FRED publishes |
| Short rate | `SOFR` | The post-LIBOR reference short rate |
| Inflation | `CPIAUCSL`, `CPILFESL` | Headline and core CPI |
| Labor | `UNRATE`, `PAYEMS` | The two headline labor prints |
| Property prices | `COMREPUSQ159N` | The one FRED-hosted series that's actually CRE (not residential) prices — Dallas Fed's international house price database extension |
| Credit conditions (SLOOS) | `SUBLPDRCSC`, `SUBLPDRCSN`, `SUBLPDRCSM` | Bank tightening standards, split by CRE loan purpose (construction/land, nonfarm nonresidential, multifamily) — this granularity beats the single discontinued `DRTSCREL` series it replaces |
| Credit conditions (delinquency) | `DRCRELEXFACBS`, `DRCRELEXFT100S` | CRE delinquency, all banks vs. top-100 banks by assets — lets the mart show concentration risk, not just an aggregate |

17 sits in the middle of the 15-25 budget CLAUDE.md sets. Rejected additions: `T10Y2Y` (FRED's
own precomputed 10Y-2Y spread) — the mart is supposed to *derive* that spread from the raw
curve points in Phase 4, so ingesting FRED's precomputed version would undercut the point of
that exercise. `MORTGAGE30US` and other residential-market series — explicitly out of scope
per CLAUDE.md's "not a generic macro warehouse" instruction.

### Why vintages are preserved — and where they aren't

The spec's instruction was to preserve `realtime_start`/`realtime_end` on every observation.
Building that revealed a real API constraint that changed the design: **FRED periodically
re-stamps a daily series' *entire* observation history under a new `realtime_start`, even when
no value actually changed** — a bulk republish event, not a genuine revision. Verified live: a
full-history ALFRED pull for `DGS10` returns `400 Bad Request` — *"There are 5080 vintage dates
in the specified real-time period... This exceeds the maximum (2000)."* Fetching it anyway
(paginated, via the `/fred/series/vintagedates` + `vintage_dates=` parameter) confirmed why:
the value at `1962-01-02` is `4.06` in every single one of those 5080 vintages — it was never
actually revised, FRED just periodically re-issues the whole file. Chasing that "history" would
mean ~725,000 near-duplicate rows for one series alone, directly against CLAUDE.md's "a bloated
warehouse demonstrates nothing extra" instruction, and against the Phase 1 Snowflake cost
budget.

The other 6 daily/near-daily series in the catalog (`DGS3MO`, `DGS1`, `DGS2`, `DGS5`, `DGS30`,
`SOFR`) were checked the same way and hit the identical wall (`SOFR` technically returned data —
2175 rows — but only because it has a shorter observation history since 2018; the same bulk
re-stamping pattern is present).

**Resulting design**: `ingest/series.py` tags each series `vintage_tracked: True/False`.
- `True` (10 series — CPI, core CPI, UNRATE, PAYEMS, the CRE price index, all three SLOOS
  series, both delinquency series): full ALFRED history, every genuine revision preserved.
  Verified counts: `UNRATE` 942 distinct dates → 2196 vintage rows (real revisions, ~2.3x);
  `CPIAUCSL` 954 dates → 3360 rows (~3.5x); `PAYEMS` 1050 dates → 13,682 rows (~13x — payrolls
  really is revised that heavily). This is exactly the data Phase 4's SCD Type 2 work needs.
- `False` (the 7 rate/curve series): current vintage only. Still has `realtime_start`/
  `realtime_end` on every row (FRED returns them on every call, vintage-aware or not) — just
  one row per date instead of a noisy multi-thousand-row history that isn't tracking anything
  real. `ingest.fred.fetch_vintage_observations(..., full_history=False)` implements this: same
  function, same output shape, just without the wide realtime window.

What would change this answer: if a specific interview or use case needed to know "what did we
believe the 10Y yield was as of some past date" (e.g. modeling a data-vendor lag), the
`vintage_tracked=False` series would need the same paginated `/fred/series/vintagedates`
approach used to investigate this in the first place — technically possible, just not worth the
row-count cost for a portfolio project where daily rates are, in substance, never revised.

### Idempotency strategy (merge key choice)

`RAW.OBSERVATIONS` merges on `(series_id, obs_date, realtime_start)`, not on
`(series_id, obs_date)` alone (the legacy Postgres table's key). Reasoning: ALFRED vintage
semantics make `realtime_start` immutable once a vintage is published — it never changes on a
later pull. `realtime_end` is the one field that legitimately *does* change: it starts as
`9999-12-31` (still current) and gets closed off the moment a newer vintage supersedes it. So
the loader (`db_snowflake.py`) does a `MERGE`: match on the three-column key, `UPDATE
value/realtime_end` if matched (picking up exactly that kind of closure), `INSERT` if not.
Re-running the same pull twice is a no-op past the first load — verified in
`tests/test_pipeline_snowflake_integration.py::test_observations_vintage_upsert_handles_revisions`,
which loads the same second-pull data twice and asserts the row count doesn't move.

`RAW.SERIES_METADATA` merges on `series_id` alone — metadata isn't versioned, a later pull is
just a refresh of the same row.

### The current-value merge-key bug (found live, before it could do damage)

The three-column merge key above is correct for `vintage_tracked=True` series, but applying it
uniformly turned out to be a real bug for the other 7. FRED's default (non-vintage) pull stamps
*every* row in the response with `realtime_start = realtime_end = today`, uniformly across the
whole batch — not per observation, a single fixed value for the entire pull. Verified directly
against live `RAW.OBSERVATIONS` after the first production run: every one of `DGS10`'s 16,851
rows shared the identical `realtime_start`. That's fine for one run, but it means a second run
on a *different calendar day* would carry a different stamp, and under the three-column key none
of those rows would match the previous day's — the pipeline would insert a full duplicate
~84,000-row batch (across the 7 current-only series) every single day instead of updating in
place, silently breaking the "ingest is idempotent" requirement in exactly the way that's easy
to miss with same-day testing (a same-day re-run looks perfectly idempotent, because the stamp
hasn't changed yet).

Caught this by checking real stored values rather than trusting the row-count match after a
same-day re-run, then reproduced and fixed it: `db_snowflake.py` now has two loaders.
`load_observations_vintage` (unchanged) keys on the three columns for real ALFRED vintages.
`load_observations_current` keys on `(series_id, obs_date)` alone for the 7 never-revised
series, treating `realtime_start`/`realtime_end` as "last checked" metadata rather than part of
the row's identity — which is the honest description of what those fields actually mean for a
series that isn't being vintage-tracked. `ingest/pipeline_snowflake.py` picks the loader per
series from the same `vintage_tracked` flag that already governs the fetch.
`tests/test_pipeline_snowflake_integration.py::test_observations_current_upsert_survives_a_day_change`
is a regression test that simulates the exact day-change scenario directly (two loads with
different realtime stamps, same observation), rather than relying on running the suite across
two real calendar days to catch it. Verified the fix against production too: re-ran the live
pipeline after deploying it, total RAW row count held at 116,263 with zero duplicates.

### Row-count reconciliation (spot-checked against live FRED, 2026-08-06)

Per-series `RAW.OBSERVATIONS` counts after the first full production run, checked directly
against a fresh FRED API call for the same series (not against memory of the earlier
verification pass):

| Series | FRED pull rows | `RAW` rows | Match |
|---|---|---|---|
| `DGS10` (current-only) | 16,851 | 16,851 | exact |
| `SOFR` (current-only) | 2,176 | 2,176 | exact |
| `UNRATE` (vintage-tracked) | 942 (current value count) | 2,196 (full revision history) | consistent — `RAW` correctly holds every vintage, not just the 942 current values |

All 17 series loaded: 116,263 total observation rows, 17 distinct `series_id` values (confirmed
directly against `RAW.OBSERVATIONS`, after deleting two leftover rows the integration tests had
left behind before their `finally`-block cleanup was added — see the test file for that fix
too).

---

## Phase 3: Staging layer

### Materialization choice for staging

Both `stg_series_metadata` and `stg_observations` are views (`dbt_project.yml`'s
`staging: +materialized: view`), not tables. Staging does nothing expensive — rename, cast,
no joins or aggregation — so a view costs nothing extra to query and never goes stale between
`RAW` loads and a `dbt build`. Tables are reserved for `marts` (Phase 4), where the actual
compute (surrogate keys, the SCD point-in-time logic, derived measures) is worth caching.

### The FRED "." missing-value decision

FRED encodes "no observation on this day" (weekends, holidays, or a genuinely missing print) as
the string `"."`. Staging casts it to `null` via `try_cast(value as double)` rather than
filtering the row out. Two reasons: first, "raw means raw" cuts both ways — dropping rows is a
business decision (what counts as a valid observation), and Phase 3's job is renaming and
casting only, not deciding what's valid; second, keeping the row preserves the
`(series_id, obs_date, realtime_start)` grain even when the value itself is unknown, which
matters for `dim_date`/`fct_observations` joins in Phase 4 — a missing weekday CPI print is
still a real row in the observation calendar, just with a null measure. Rejected alternative:
filtering nulls out in staging, the way the original Python `transform.py` did (see AUDIT.md) —
rejected because that was the old single-series pipeline making a quality-gate decision at the
wrong layer; Phase 5's dbt tests are where "how much missingness is acceptable" belongs.

### Seeds as the DuckDB stand-in for Snowflake RAW

`stg_series_metadata`/`stg_observations` both read from a `source('raw_fred', ...)` pointing at
schema `raw`. On Snowflake, `ingest/pipeline_snowflake.py` populates that schema directly. DuckDB
has no equivalent always-on ingestion, so `dbt/seeds/series_metadata.csv` and
`dbt/seeds/observations.csv` — generated by `scripts/generate_dbt_seeds.py` from a live FRED
pull, trimmed to the last ~4 years — stand in via `dbt seed --target duckdb`. Both land in a
schema literally named `raw` (not dbt's default `<target_schema>_raw`) via a
`generate_schema_name` macro override in `dbt/macros/`, so the exact same `source()` reference
resolves correctly against either target — the staging models have no idea which one they're
reading from. This is what makes Phase 6's "five-minute DuckDB build" claim actually true: a
stranger cloning the repo runs `dbt seed && dbt build --target duckdb` and gets real (if
time-boxed) FRED data with real revisions in it, not synthetic placeholder rows. Rejected
alternative: hand-written synthetic fixture data — rejected because the point of a portfolio
project is showing the modeling work against real, occasionally messy data (the UNRATE
`3.7 -> 3.6` revision from `2022-08-01` is real, not invented), and generating it from the same
`ingest.fred` functions the production pipeline uses means the fixture can never silently drift
out of sync with what the real ingest actually returns.

### The realtime_start/realtime_end naming exception

CLAUDE.md's naming convention says dates get a `_date` suffix. `stg_observations` renames
`realtime_start`/`realtime_end` (raw FRED field names) to `realtime_start_date`/
`realtime_end_date` — applied uniformly rather than carved out as an exception, on the
reasoning that a consistent, literally-followed convention is more defensible in an interview
than "renamed observation_start but not realtime_start because ALFRED terminology felt
established enough" would have been.

### sqlfluff, brought forward from Phase 6

CLAUDE.md's definition-of-done lists `sqlfluff lint models/` as applying to *every* phase, not
just the Phase 6 CI wiring — so `dbt/.sqlfluff` (Snowflake dialect, dbt templater,
`target: duckdb` so linting needs no cloud account) and `make sqlfluff-lint` exist from this
phase on, not deferred. One config decision worth recording: `value` is a reserved word in
Snowflake, which sqlfluff's `references.keywords` rule flags by default. Rather than rename the
column, `ignore_words = value` was added to `.sqlfluff` — CLAUDE.md explicitly blesses `value`
as the one acceptable exception to "never a meaningless column name," and per CLAUDE.md's own
rule ("if style and sqlfluff disagree, fix sqlfluff's config"), the config yields, not the
column name.

---

## Phase 4: Dimensional marts

Grain declared before any model SQL, per CLAUDE.md's instruction. Four fact-grain objects this
phase builds, each answering a different question:

- **`fct_observations`** — grain: **one row per series, per observation date, per vintage**
  (`series_key`, `date_key`, `realtime_start_date`). This is the base fact and the one true
  source of history — every FRED/ALFRED revision is its own row, nothing collapsed. Directly
  inherited from `stg_observations`' grain (Phase 3), just with surrogate keys swapped in for
  the natural keys.
- **`fct_observations_latest`** — grain: **one row per series, per observation date.** For each
  `(series_key, date_key)`, the single vintage with the greatest `realtime_start_date` — the
  most recently known value, full stop. This is what "the current dataset" means for anyone who
  doesn't need history.
- **`fct_observations_point_in_time`** — grain: **one row per series, per observation date, as
  known on a given as-of date** (the as-of date is a dbt var, `as_of_date`, defaulting to today
  when not supplied). For each `(series_key, date_key)`, the single vintage whose
  `[realtime_start_date, realtime_end_date)` window covers the as-of date. This is the object
  that answers "what did we believe X was, as of some past date" — the actual point-in-time
  query the brief asks for, not just a description of one.
- **`dim_series`** — grain: one row per FRED series (`series_key` ~ `series_id`).
- **`dim_date`** — grain: one row per calendar date across the full observation range.
- **`mart_cre_macro_conditions`** — grain: **one row per calendar month.** (Rationale for
  monthly over daily is its own decision below, once the model exists to point at.)

Every fact's `.yml` description restates its grain, and a uniqueness test on the grain columns
enforces it — not just documents it.

### Star versus snowflake

Star, not snowflake: `fct_observations` (and its two derived views) join directly to `dim_series`
and `dim_date`, both flat — no `dim_series` → `dim_series_group` → `dim_group_region` chain.
With two dimensions and 17 rows in one of them, a snowflake schema would add join hops for
zero real normalization benefit; `dim_series` is small enough that even full denormalization
(carrying `category` directly on the dimension row, rather than a separate category dimension)
costs nothing in storage and saves a join on every query. If the series catalog grew to
hundreds of series with genuinely hierarchical categorization (category → subcategory →
region), snowflaking would start to pay for itself — at 17 series it would just be an extra
join for the sake of looking normalized.

### SCD Type 2 approach, and what was rejected

The brief calls this "the single most interesting modeling problem in the project," and the
approach here is deliberately not a textbook Type 2 dimension (no `dim_series` row versioning
— series metadata like title/units doesn't get revised the way observation values do). The
revision problem here is on the **fact**, not a dimension: the same `(series, obs_date)` gets
multiple values over time as FRED revises it. `fct_observations` carries every vintage as its
own row with a `[realtime_start_date, realtime_end_date)` validity window — that's the
Type-2-style mechanism (bitemporal, technically: transaction time via `realtime_start`/`_end`,
valid time via `obs_date`), just applied to a fact instead of a dimension, because that's where
this domain's actual revisions live.

Two views read that one fact differently rather than duplicating the revision logic:
`fct_observations_latest` (rank by `realtime_start_date desc`, take the newest — works
uniformly for both true multi-vintage series and the current-value-only ones from Phase 2,
since the latter always have exactly one row to "rank") and `fct_observations_point_in_time`
(same ranking, but filtered to vintages whose `realtime_start_date <= as_of_date` first).

**Rejected: keeping only latest values.** This is explicitly what the brief says not to do, and
for good reason — it would make `fct_observations` structurally incapable of answering "what
did we know then," which is the entire point of ingesting ALFRED vintages in Phase 2 in the
first place. Would have saved nothing at query time either; `fct_observations_latest` already
gives the simple case for free.

**Rejected: a separate physical table per as-of date, or a dbt snapshot.** dbt's `snapshot`
feature detects and records changes to a *source* over time by diffing successive runs — it's
built for sources that don't already carry their own history. `stg_observations` already *is*
full history (ALFRED gives it to us directly), so snapshotting it would be recording history of
a thing that's already all history — redundant, and it would only capture revisions that
happened to occur between two `dbt snapshot` runs, missing anything ALFRED knows about from
before this project started snapshotting.

**Rejected: materializing `fct_observations_point_in_time` as a table.** Its answer is only
valid for the `as_of_date` var it was last built with; a table would look queryable while
silently answering last week's question. It's a view specifically so that's structurally
impossible to do by accident — see the model file.

### Surrogate key strategy

Every dimension and fact join key is `dbt_utils.generate_surrogate_key(...)` over the natural
key (`series_id` for `dim_series`, `date_day` for `dim_date`) — a stable hash, not an
auto-incrementing integer. Rejected auto-increment: it requires the dimension to already exist
and be queried to know the next value, which doesn't compose well with `dbt build`'s
recompute-from-scratch model (a hash is pure and deterministic — the same `series_id` always
produces the same `series_key`, in any build, on any target, without needing to consult prior
state). The natural keys (`series_id`, `obs_date`) are kept alongside the surrogate keys in
`dim_series`/`stg_observations` for human readability and debugging, but `fct_observations` and
the marts join and filter on the surrogate keys only, per CLAUDE.md's "do not use raw natural
keys as joins into facts."

### Why the mart is monthly, not daily

Two of the five input groups (property prices, SLOOS lending standards, CRE delinquency) are
natively quarterly — a daily mart would mean those columns are 98%+ forward-filled repetition,
which overstates how much information the mart is actually delivering. Monthly is the coarsest
grain that still gives CPI, unemployment, and payrolls their own native, un-filled reading every
single row (they're monthly series), while the daily-frequency Treasury curve and SOFR still
comfortably summarize to a month-end snapshot without losing anything a CRE credit read needs —
nobody underwrites a loan against yesterday's exact 10-year yield versus today's. Daily was
rejected for the reason above; quarterly was rejected because it would throw away the monthly
resolution that CPI/unemployment/payrolls actually have, which is exactly the granularity a
"macro conditions for CRE credit" mart should be able to show for the series that support it.

The mart's date range starts 2015-01 rather than covering full history back to 1939 (PAYEMS) or
1962 (the Treasury curve) — a scoping choice, not a limitation of the data (`fct_observations`
itself has full history; only the mart is windowed). Two reasons: first, SOFR doesn't exist
before 2018-04, so any earlier start guarantees a large stretch of one column being
structurally null before its own inception, which is correctly-explained but not useful mart
content; second, a consumption table meant for CRE credit-conditions analysis doesn't benefit
from 90 years of thin, mostly-irrelevant history the way the underlying fact table's full
archive does. ~11 years gives enough runway for the 60-month trailing z-score (below) to be
meaningful from early in the mart's own history, while still deliberately showing a few years
of legitimate pre-SOFR nulls — proving the null-handling works rather than picking a start date
that conveniently avoids the question.

### Derived-measure definitions

- **`treasury_10y_2y_spread_pct`** = `treasury_10y_pct - treasury_2y_pct`. The standard curve-
  inversion signal; negative means inverted.
- **`real_10y_rate_pct`** = `treasury_10y_pct - cpi_yoy_pct` — nominal 10-year yield less
  *realized* headline CPI inflation, not a TIPS-based real yield. Rejected TIPS: no TIPS series
  (e.g. `DFII10`) is in the 17-series catalog, and adding one just for this one derived measure
  would mean carrying a series that serves no other purpose in a project that's deliberately
  scoped to ~17. The realized-inflation proxy is a well-understood simplification, just not the
  same thing as a market-implied real yield, and the column description says so.
- **YoY measures** (`cpi_yoy_pct`, `core_cpi_yoy_pct`, `unemployment_rate_yoy_change_pct`,
  `nonfarm_payrolls_yoy_change_thousands`): CPI/core CPI use percent change (`value / lag(value,
  12) - 1`) since they're index levels and the standard headline inflation figure is a percent
  change; unemployment uses a level (percentage-point) difference since it's already a rate,
  not an index; payrolls uses a level difference in thousands of jobs, the standard way jobs
  reports are discussed ("+180k jobs"), not a percent change.
- **`treasury_10y_2y_spread_zscore_60mo`**: z-score of the spread against its own trailing
  60-month (5-year) mean and sample stddev. 60 months chosen because it's long enough to span at
  least one full rate cycle (so "unusual" is measured against genuine regime variation, not just
  recent noise) while still being short enough to stay responsive to a structural shift rather
  than being anchored to multi-decade history that may no longer be representative. Applied
  only to the headline spread, not every measure in the mart — the spread is the one number a
  CRE credit read is most likely to want flagged as "unusually wide/narrow/inverted relative to
  recent history"; z-scoring every column would be noise for measures nobody reads that way.
  Null for the mart's first month (a single point has no sample stddev) and, on the duckdb
  target specifically, for its entire ~4-year trimmed fixture (never accumulates 60 months) —
  both expected, not bugs. Verified populated correctly against full Snowflake history: null
  only for 2015-01, populated from 2015-02 onward.

### A real incident: `dbt seed` silently overwrote production RAW data

While testing the mart against Snowflake, `treasury_10y_2y_spread_pct` and related columns were
null for 2015 through mid-2022 — investigation traced it to `RAW.OBSERVATIONS` on Snowflake
holding only 1,042 `DGS10` rows (2022-08 onward) instead of the 16,851-row full history the
Phase 2 production pipeline had loaded. Root cause: an unscoped `dbt build` against the
`snowflake` target runs every enabled seed, including `series_metadata`/`observations` — the
DuckDB-only fixture seeds from Phase 3. `dbt seed` is a full truncate-and-reload, not a merge,
so it silently replaced the real 116,263-row production `RAW.OBSERVATIONS` with the trimmed
~8,000-row DuckDB fixture. No error, no warning — just quietly wrong data that only surfaced
because the mart's early-history nulls didn't match what was expected.

Fixed at the config level, not by "remembering to always pass `--select`": `dbt_project.yml`'s
seeds config now sets `+enabled: "{{ target.name == 'duckdb' }}"` on both raw fixture seeds, so
an unscoped `dbt seed`/`dbt build` against `snowflake` structurally cannot touch them — verified
by running `dbt seed --target snowflake` and confirming it processes only `dim_series_category`
(1 seed, not 3). Restored production data with a fresh `ingest.pipeline_snowflake` run,
re-verified the mart's z-score and spread populate correctly across full history afterward.
Worth flagging in an interview: this is a real mistake, caught by noticing data looked wrong
rather than by any test — Phase 5's testing work should consider whether a row-count sanity
check on `RAW` (e.g. "did this table just shrink") would have caught it faster.

---

## Phase 5: Testing and data quality

### Test severity: which tests are warnings, and why

Deliberate two-tier policy, not left at dbt's blanket default (`error`):

- **Error** (fails the build): anything that represents a genuine modeling defect or a
  definitionally-impossible value. Primary-key/grain uniqueness, referential integrity,
  `not_null` on join/key columns, the point-in-time and spread-reconciliation singular tests
  (Phase 4/5's business-logic tests), and distributional bounds that are impossible by
  definition rather than just unusual — a rate `< 0` or `> 100`, an index `<= 0`, a SLOOS net
  percentage outside `[-100, 100]`, a delinquency rate outside `[0, 100]`, negative payrolls.
  These would mean the pipeline or a model is actually broken; a build should stop.
- **Warn** (reported, doesn't fail the build): distributional bounds sized to catch gross
  errors (a decimal-point bug, a unit mixup) rather than tight economic ranges, plus
  `assert_mart_recent_key_measures_not_null` (a recent-data gap is as likely to be FRED
  publishing late — genuinely happened, see the Phase 4 government-shutdown entry — as a real
  pipeline failure, and shouldn't block a build on that ambiguity alone).

This is not a hypothetical distinction. Running the full suite against Snowflake's real,
untrimmed history tripped two `warn`-tier bounds for real, both immediately explainable and
both proof the design works as intended rather than being too loose:

- `nonfarm_payrolls_yoy_change_thousands` at **2021-04** and **2021-05**: +14.16M and +12.03M
  jobs year-over-year. Not a data error — April/May 2020 was the deepest point of the COVID
  labor-market collapse, so the YoY comparison a year later is measured against that trough,
  producing a legitimately enormous rebound figure.
- `unemployment_rate_yoy_change_pct` at **2020-04**: +11.1 percentage points (14.8% versus
  3.7% a year prior) — the COVID unemployment spike itself.

Both are real, well-documented macro events landing exactly on the boundary the bounds were
sized around. Left as `warn`, not tightened to suppress them and not loosened to silence them
without looking — a human reviewing the build output sees exactly why these two months are
flagged, which is the point of a warning tier existing at all.

### What the distributional bounds are based on

Sized to catch the spec's own example category of bug — "an unemployment rate above 100 is a
bug, a Treasury yield of 400 is a bug" — not to encode tight, defensible economic ranges.
Concretely: Treasury/SOFR rates get `[-1, 25]` (historical peak was ~20% in 1981; a yield of
400 trips this by more than an order of magnitude, which is the point); CPI/core CPI indices
get `(0, 1000)` (currently ~330s, wide headroom, must be positive); the mart's YoY/spread/
real-rate columns get bounds wide enough to include real historical extremes (the payrolls
bound was explicitly sized around the 2020 COVID collapse) without being wide enough to mean
nothing. Values that are impossible by definition (a percentage above 100 or below 0, a net
SLOOS percentage outside +/-100) get exact, non-negotiable bounds and `error` severity, per
the severity policy above — those aren't "unusual," they're definitionally wrong.

### A second real incident: seeds and sources don't share a dbt DAG dependency

Adding `dbt-expectations` tests surfaced this indirectly: a fresh, unscoped `dbt build` against
`duckdb` (delete the `.duckdb` file, run one command) intermittently failed with `stg_observations`
and `stg_series_metadata` erroring that their source tables didn't exist — even though the
`observations`/`series_metadata` seeds are enabled on that exact target. Root cause: those
staging models read via `{{ source(...) }}`, and seeds are a completely separate node type in
dbt's DAG. dbt has no way to know the `observations` seed is what populates the `raw_fred.
observations` source on `duckdb` (on `snowflake`, that source is populated externally, by the
Python pipeline — dbt genuinely can't know the two are related on `duckdb` specifically). With
`dbt build`'s default 4-thread concurrency, nothing enforces that the seed finishes loading
before a model reading the same physical table starts — usually it happened to finish first by
luck; sometimes it didn't.

Fixed structurally, the same way as the earlier seed-overwrite incident: `make dbt-build` now
depends on `make dbt-seed` as an explicit Make prerequisite, so seeding is a fully separate,
completed process before `dbt build` ever starts — not a race within one process's thread pool.
Verified by repeatedly deleting `bridge.duckdb` and running `make dbt-build` fresh; 80/80 tests
green every time after the fix, where it had failed roughly one run in three before it.

### `dbt source freshness` and CI

Freshness thresholds were already configured on `raw_fred` in Phase 3 (`warn_after`/
`error_after`) and verified running manually then. Wiring `dbt source freshness` into the
actual CI workflow is Phase 6's task, not duplicated here — Phase 6 owns `.github/workflows/
ci.yml` and this project's own sequencing note says protect Phase 4 above everything else, not
front-load Phase 6's CI work into Phase 5.

---

## Phase 6: CI and documentation

### CI job design: isolated schema, sequenced after lint-and-test

`dbt-build` (the new job in `.github/workflows/ci.yml`) builds `staging`/`marts` into
`CI_${{ github.run_id }}` — a schema unique to that specific workflow run, on every PR and
every push to `main` — then tears it down in an `if: always()` step so cleanup runs even if
the build or a test failed. It reads real data: `RAW` isn't touched by this job at all (no
ingest happens in CI), only staging/marts land in the throwaway schema, which is exactly the
isolation the acceptance criterion asks for without needing a second Snowflake account or a
mocked data layer.

Runs `needs: lint-and-test` rather than in parallel — deliberately spends no Snowflake credits
building against real data when a lint or unit-test failure would have made the run pointless
anyway. Verified locally before ever touching CI: built into a real isolated schema
(`CI_TEST_LOCAL_SIM`), confirmed it existed via `SHOW SCHEMAS`, ran the exact
`dbt run-operation drop_ci_schema` command CI uses, confirmed the schema was gone afterward.

### Why `publish-docs` uses duckdb, not Snowflake

`dbt docs generate` needs a live connection to introspect column types for the catalog, but
it doesn't need to be `RAW`'s live 116K-row production data — the DuckDB seed fixture is
sufficient to produce complete, accurate documentation (same models, same columns, same
tests, just less history). Using `duckdb` here means the docs-publishing job needs zero
Snowflake credentials and never touches the shared warehouse, which also means a broken or
rotated Snowflake credential can never take down the published docs site — a real
"why give a job more access than its job requires" argument, not just a convenience.

### The lineage image: generated from `manifest.json`, not a screenshot

`dbt docs`' own interactive lineage view is a JS graph with no built-in static-image export,
and the accessible view rendered too cluttered/cramped for a recruiter skimming a README (see
`scripts/generate_lineage_graph.py`). Rendered `docs/lineage.png` directly from
`manifest.json`'s `depends_on` edges with Graphviz instead — full control over layout, color
by layer (source/seed, staging, dim/fct, mart, test), and one exclusion rule worth recording:
the DuckDB-only fixture seeds (`observations`, `series_metadata`) are dropped from the diagram
because they share a display name with the `raw_fred` source they stand in for and have no
downstream edges of their own (seeds aren't `ref()`'d by staging models) — included, they
rendered as disconnected-looking duplicate nodes with no explanation. `dim_series_category`
has no such collision and stays. Kept as a real, reusable script (not a one-off) since the
graph needs regenerating after any change to the model DAG.

### What's built versus what's live — verified, not assumed

Everything above was independently verified against real Snowflake and DuckDB before being
called done, including the CI wiring itself: the three `SNOWFLAKE_*` GitHub Actions secrets
were set, GitHub Pages was enabled (`build_type: workflow`, confirmed the resulting URL matches
what's in the README exactly), and the rebuild was pushed as a PR rather than straight to
`main` specifically so the new `dbt-build` job's isolated-schema-plus-teardown could be watched
running for real on a pull request before merging — not just trusted because it looked right
locally. It passed (`lint-and-test` and `dbt-build` both green, `publish-docs`/
`build-and-push`/`deploy` correctly skipped on a PR since they're gated to `main`). After
merging, all five jobs ran on the push to `main` and passed, including `deploy` (the legacy
Postgres/GCE path — a real SSH deploy to the live box, unaffected functionally by this rebuild
but real infrastructure nonetheless) and `publish-docs`, which was then checked by loading the
live URL and confirming it actually renders the dbt docs site, not assumed from the job's green
checkmark alone. This "verify by observing the real system, not by trusting a local run or a
green checkmark" habit shows up repeatedly across this document (the Phase 1 `AUTO_SUSPEND`
check, the Phase 2 row-count reconciliation, the Phase 4 and 5 incidents were both caught by
noticing real data looked wrong, not by a test) — it's as much a decision about *how to work* as
any individual technical choice above.

## Phase 8: orchestration

### Airflow, not Dagster — reversing the Phase 6 sketch

`INTERVIEW_NOTES.md`'s "what would you build next" answer (written during Phase 7) named
Dagster, modeling the FRED ingest and dbt build as one graph of assets. This phase built
Airflow instead, and that's worth being honest about rather than quietly rewriting history:
Dagster's asset-centric model is arguably a better conceptual fit for "ingest feeds a dbt
project," but Airflow is the far more common ask in the postings this project targets, and the
TaskFlow API (`@dag`/`@task`) demonstrates the same DAG-authoring, retry, and idempotency
concepts an interviewer would probe regardless of which tool answers the question. Given a
choice between the tool that fits the data model more elegantly and the tool more of the
target audience will actually recognize on a resume, this project picked the second — the same
"target the postings" logic Phase 1 used to pick Snowflake over BigQuery.

### LocalExecutor + local Docker Compose, not managed Airflow or Celery

Three alternatives considered and rejected, all for the same underlying reason — this is one
daily DAG per pipeline, not horizontal scale across many concurrent DAGs:

- **MWAA / Cloud Composer** bill hourly for a managed control plane. Running one for a resume
  bullet, then having to explain in an interview why a portfolio project pays for managed
  infrastructure it didn't need, is a worse outcome than not having it — the honest answer to
  "why not managed Airflow" (cost, and the workload doesn't need it) is a stronger interview
  moment than a screenshot of an idle MWAA environment.
- **CeleryExecutor / KubernetesExecutor** solve horizontal scaling across many concurrent
  workers. Reaching for them here — two DAGs, one run each per day — is architecture that
  doesn't match the actual workload, which reads as copied from a tutorial rather than
  understood. LocalExecutor runs both DAGs' tasks as subprocesses of the scheduler, which is
  the entire amount of concurrency this project needs.
- **The official docker-compose.yaml itself defaults to CeleryExecutor** (with Redis, a worker,
  and Flower) — see `orchestration/docker-compose.yaml`'s header comment for the specific
  services stripped out and why. Adapted rather than used verbatim, and adapted from the real
  file (fetched from `airflow.apache.org` while building this, not reconstructed from memory —
  Airflow 3 split the old 2.x webserver into a separate `airflow-apiserver` plus its own
  `airflow-dag-processor` service, a structural change worth getting right rather than guessing).

What would change the answer: genuinely needing to run many independent DAGs concurrently, or
specifically interviewing at a shop known to run MWAA/Composer (in which case spinning up the
smallest managed environment just long enough to screenshot it, then tearing it down before
next month's bill, is the one scenario where the managed cost is worth paying).

### Both pipelines get a DAG, not just the unscheduled one

Only the Snowflake pipeline was actually missing scheduling (`INTERVIEW_NOTES.md`'s "no
scheduled ingestion for the Snowflake path" — the legacy Postgres pipeline already runs daily
via the GCE cron entry). `legacy_postgres_pipeline` was built anyway, alongside
`snowflake_dbt_pipeline`, because the interesting orchestration concepts — TaskFlow wiring,
retries with backoff, a failure callback, idempotent reruns, a DAG-integrity test — are
identical either way, and demonstrating both means the DAGs read as a general orchestration
capability applied twice, not a one-off script for a single pipeline.

### Why the live GCE cron entry stays untouched

`deploy/bridge-pipeline.cron` keeps running the legacy pipeline on the production VM exactly as
it did before this phase. Local Airflow was never a candidate to replace it: this project's own
Phase 1 reasoning against managed Airflow (cost, scope) applies just as directly to *deploying*
a self-hosted Airflow instance to run production infrastructure — that's real ops work (uptime,
upgrades, secrets management for a persistent service) that doesn't serve this project's actual
goal, which is demonstrating orchestration skill, not operating a second production scheduler
next to the first one. The local Airflow instance runs the identical `extract -> quality_gate
-> load` sequence as a DAG so the capability is real and demonstrable (`make airflow-up`,
trigger a run, watch it succeed), without anything about the live box changing. Same pattern as
the DuckDB/Snowflake split in Phase 1: show the real thing locally, don't make a reviewer stand
up cloud infrastructure to see it work.

### Idempotent reruns and backfills — by construction, not by new logic

Neither DAG does incremental, partition-by-`execution_date` loading. `extract()` re-fetches
FRED's full current series state every run; `ingest_series()` re-fetches vintage history (or
current value) for all 17 series every run. Both land into loaders that already upsert on a
composite key (`db.py`'s `(series_id, date)`, `db_snowflake.py`'s vintage- or current-keyed
MERGE — see Phase 2's idempotency-bug writeup for why there are two different loaders in the
first place). The consequence: a scheduler-triggered rerun, a manually triggered rerun, or an
Airflow backfill of a past date all produce the exact same end state as a single run, because
every run reloads the same full state and MERGEs it in — there is no backfill-specific code
path to get wrong. The tradeoff is real and worth naming, not hiding: this only works because
the ingest volume stays small enough (116K rows) that a full pull every run is cheap. A
much larger source would need genuine incremental logic, and *then* Airflow's
`data_interval_start`/`data_interval_end` would need to actually drive the fetch window instead
of being ignored.

### A JSON-XCom gotcha, and why `dbt_build` gets a dict, not the mart data

`transform()` (in `transform/transform.py`) returns rows with a `datetime.date` field, and
Airflow's XCom backend serializes task outputs as JSON by default — `datetime.date` isn't
JSON-serializable, so `quality_gate()` converts `date` to an ISO string before returning, and
`load()` converts it back on the way in. Small, easy to miss, and exactly the kind of thing
that passes a first local test (Python doesn't complain until the value actually crosses the
XCom boundary) and then breaks on the real scheduler. `snowflake_dbt_pipeline` sidesteps the
question entirely for its own data: `ingest_series()` returns a small totals dict
(`{"series": int, "observations": int}`) for logging and to force the dependency edge, not the
17-series payload itself — that stays inside Snowflake RAW, which is the entire point of
landing it in a warehouse rather than passing it through the orchestrator.

`legacy_postgres_pipeline` originally didn't follow its own sibling's example here: `extract()`
returned the full raw FRED payload and `quality_gate()` the full clean/deduplicated dataset,
both crossing XCom (the metadata Postgres) in full, when `extract()` had already landed the raw
rows via `load_raw()`. Fixed the same way: `extract()` now returns just a row count, and
`quality_gate()` re-reads what was just landed via a new `db.read_raw()` (mirroring the existing
`read_clean()`) instead of receiving it as an argument. The `quality_gate` -> `load` hop still
passes the clean rows through XCom deliberately -- it's already the smaller, deduplicated,
validated payload, and `load()` remains a real, separate step (persist what passed the gate)
rather than folding into `quality_gate()` just to avoid one more XCom hop.

### The DAG-integrity test runs inside the Airflow container, not the project's own venv

`orchestration/tests/test_dag_integrity.py` uses `DagBag` to assert both DAGs import without
error and have the expected tasks, retries, and failure callback. It runs via
`make dag-test` / the CI job of the same shape, both of which exec into the already-built
Airflow image — not `pytest` in the root `.venv`. Considered and rejected: adding `apache-
airflow` to `requirements-dev.txt` so `make test` covers it directly. Rejected because Airflow
pins a large, particular set of transitive dependencies (via its own constraints file) that
risked real conflicts with dbt-core's equally large dependency tree in the same environment —
for a test that only needs to run somewhere Airflow is already installed correctly, which the
Airflow image already is.

### Real bugs hit standing this up (kept, not edited out)

- **`chown` failing inside `airflow-init`.** The official init script's last step
  `chown`s `/opt/airflow/{logs,dags,plugins}` to `AIRFLOW_UID`. On Colima (this project's local
  Docker runtime — see `SETUP.md`), the bind-mounted host directories are shared over SSHFS,
  which doesn't support real UID ownership changes from inside the VM. Fixed by pre-creating
  those directories on the host with open permissions and making the `chown` best-effort
  (`|| true`) rather than fighting the filesystem for a guarantee this local setup doesn't need.
- **`DagBag(include_examples=False)` no longer exists.** Airflow 3 dropped the kwarg — with
  `AIRFLOW__CORE__LOAD_EXAMPLES: 'false'` already set globally (in
  `orchestration/docker-compose.yaml`), it wasn't needed anyway; the test just calls
  `DagBag(dag_folder=...)` now.
- **The Airflow image's entrypoint intercepts plain commands.** `docker compose run --rm
  airflow-scheduler pytest ...` doesn't run pytest — the image's entrypoint script treats its
  first argument as a potential Airflow CLI subcommand, and falls through to printing `airflow
  --help` for anything it doesn't recognize. Both `make dag-test` and the CI job override the
  entrypoint directly (`--entrypoint /bin/bash ... -c "pytest ..."`) instead, the same
  workaround the official compose file's `airflow-cli` service uses for the same underlying
  issue (referenced there as apache/airflow#16252).
- **`callbacks.py` wasn't importable from a bare `DagBag()` call.** `from callbacks import
  log_failure` works when Airflow's real `airflow-dag-processor` service parses the DAG files
  (it puts the dags folder on `sys.path` itself first) but not when `DagBag` is instantiated
  directly from a plain pytest process — confirmed by running `airflow dags list-import-errors`
  (clean) right before the standalone test failed with `ModuleNotFoundError`, which is what
  pointed at the real cause. Fixed with an explicit `sys.path.insert(0, "/opt/airflow/dags")`
  at the top of the test file.
- **The Airflow apiserver's port was never actually reachable from the host.** `SETUP.md`
  already documents that Colima's host port-forward is broken on this dev host, which is why
  `make db-up` opens a manual SSH tunnel (`scripts/db-tunnel.sh`) for Postgres — that same
  problem applies to any host-published Docker port, including the apiserver's plain
  `"8080:8080"` mapping, and wasn't caught until a later code review pointed at `SETUP.md`'s own
  words. Fixed by reusing `db-tunnel.sh` unchanged (it already reads `HOST_PORT`/`GUEST_PORT`
  from the environment) for port 8080 too, wired into `make airflow-up`/`airflow-down`.
- **Compose's `${VAR}` substitution and its `env_file:` directive read from different places.**
  `FERNET_KEY`, `AIRFLOW_UID`, and the `_AIRFLOW_WWW_USER_*` vars are referenced as bare
  `${VAR}` in the compose YAML — Docker Compose resolves those from the shell environment or a
  `.env` in the compose project directory, not from `env_file: ../.env`, which only reaches the
  *containers'* runtime environment after the YAML is already resolved. Every other variable in
  the same file happens to come from `env_file`, making it a reasonable but wrong assumption
  that these four would too. Fixed by passing `--env-file ../.env` on every `docker compose`
  invocation (Makefile and CI), so root `.env` is genuinely the single place to set any of this.
- **`orchestration/config/` was created and gitignored but never mounted.** The Makefile and
  `.gitignore` treat it as real Airflow runtime state, mirroring the official compose file's
  `./config:/opt/airflow/config` mount — that mount line just never made it into the adapted
  file. Added it.

A few smaller cleanups from the same review, briefly: `legacy_postgres_pipeline.py`'s quality
bounds (`MIN_ROWS`/`MAX_ROWS`/`MAX_AGE_DAYS`) are now imported from `ingest/pipeline.py` instead
of re-declared as a second copy that could drift from the bounds it's supposed to match; the
dbt version pins duplicated across `requirements-dev.txt` and
`orchestration/requirements-airflow.txt` now live once in `dbt-versions.txt`, referenced by
both via `-r`; and `build-and-push` (and therefore `deploy`, which depends on it) now also
`needs: dag-integrity`, so a DAG that fails to import can no longer ride a green
`lint-and-test` to a live deploy.

### Verified, not assumed

Both DAGs were built with `docker compose build`, brought up with `docker compose up -d` against
this project's real Colima runtime, confirmed with zero entries in `airflow dags
list-import-errors`, unpaused, and triggered for a real run each — `legacy_postgres_pipeline`
against a real (local, containerized) Postgres, `snowflake_dbt_pipeline` against the same live
Snowflake account every other phase of this project uses, including a real `dbt build`. The
DAG-integrity suite (five tests: no import errors, both DAGs present, exact expected task sets,
every task has a failure callback, and retries land only on each DAG's flaky FRED-API task) was
run inside the actual Airflow container, not assumed to pass from reading the DAG files.

A later code review caught the first version of this: `default_args` had `retries` set at the
`@dag` level, which Airflow applies to every task, not just the one it was meant for -- so a
deterministic `DataQualityError` or a real `dbt build` failure was silently retried 3x (up to
~15-20 min) before failing, contradicting the design this section describes. Fixed by moving
retries onto the extract/`ingest_series` task's own `@task(...)` decorator specifically (both
DAGs now share `RETRY_ARGS`/`DEFAULT_ARGS`/`SCHEDULE` from `callbacks.py` rather than
copy-pasting them), and split the DAG-integrity test's single retries-and-callback assertion
into two, so a regression here fails loudly instead of passing on a technicality.
