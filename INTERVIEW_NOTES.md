# INTERVIEW_NOTES.md

This is the spoken-register companion to `DECISIONS.md`. That file is the full written record;
this one is what you'd actually say out loud if someone asked about this project in an
interview. Shorter sentences, no hedging, on purpose.

---

## The grain of every fact table, in one sentence

- **`fct_observations`**: one row per series, per observation date, per vintage — every
  revision FRED ever published is its own row.
- **`fct_observations_latest`**: one row per series, per observation date — whatever the most
  recently known value is, today.
- **`fct_observations_point_in_time`**: one row per series, per observation date, as of
  whatever `as_of_date` you built it with — "what did we believe this number was on some past
  date."
- **`dim_series`**: one row per FRED series.
- **`dim_date`**: one row per calendar day.
- **`mart_cre_macro_conditions`**: one row per calendar month.

## SCD Type 2, explained the way I'd say it out loud

"Macro data gets revised. The unemployment rate for last month gets printed, then it gets
revised the month after, and it might get revised again a year later when annual benchmarks
come out. If I only ever store the current value, I've thrown away the fact that on the day I
made some decision, the number I actually had in front of me was different from what it says
today.

So instead of one row per (series, date), I made the grain one row per (series, date,
*vintage*) — vintage meaning 'this was the value as it was known between this date and that
date.' Every time FRED revises something, that's a new row, not an overwrite. That's the whole
trick. It's SCD Type 2, just applied to a fact table instead of the dimension table it's
usually taught on — because in this domain, the thing that changes over time isn't the
series' *metadata*, it's the *observation itself*.

Once you have that, 'what do we know now' and 'what did we know then' are just two different
filters over the same table, not two different data models. Latest is 'give me the newest
vintage per date.' Point-in-time is 'give me whichever vintage was active on this other date I
care about.' I proved that actually works with a real example, not a made-up one — there's a
commercial property price reading that genuinely got revised three times over about two years,
and I wrote a test that queries it as of two different historical dates and checks it gets the
two different values that were actually true at each point."

## The three hardest problems, and how they got solved

**1. FRED's vintage data doesn't mean what I assumed it meant.**
I built the vintage-preserving ingest logic assuming "pull full history for every series" would
just work. For daily market-rate series like the 10-year Treasury, it didn't — FRED's API
rejected the request with a 2000-vintage-date limit, and the series had over 5,000. Digging in,
I found out why: FRED periodically re-stamps a daily series' *entire* history with a new
publish timestamp, even when not a single value changed. It's a bulk republish, not a revision.
Chasing that "history" would've meant ~725,000 near-duplicate rows for one series. The fix was
a design decision, not a technical workaround: I split the 17 series into two groups —
genuinely-revised series get full vintage tracking, and daily market rates get current-value-
only, because full tracking there wasn't just infeasible, it wasn't meaningful.

**2. An idempotency bug that only shows up on the second day.**
My first version of the loader merged on (series, date, vintage-start-timestamp) for
everything. That's correct for genuinely revised series. But for the current-value-only series,
FRED stamps *every* row in a pull with today's date, uniformly. Run the pipeline twice on the
same day, looks perfectly idempotent. Run it tomorrow, and every single row gets a new
timestamp that doesn't match yesterday's — so under a strict revision-based key, the whole
batch would insert as brand-new duplicate rows instead of updating in place. I caught this by
actually checking the stored values instead of trusting a clean same-day test run, then fixed
it with a second loader that keys those series on (series, date) alone, and wrote a regression
test that simulates the day-change directly instead of waiting two real days to catch it again.

**3. Getting the CI isolation actually right, not just configured right.**
The brief wanted CI to build into an isolated schema per run and tear it down. It would have
been easy to write that YAML and call it done. Instead I built into a real Snowflake schema by
hand first, confirmed with `SHOW SCHEMAS` that it existed, ran the exact teardown command CI
would run, and confirmed the schema was actually gone — before that logic ever touched GitHub
Actions. Then I opened the work as a pull request instead of pushing straight to `main`,
specifically so I could watch the real CI job build into a real isolated schema and tear it
down on a real PR before merging, instead of assuming a green local run meant it would work in
CI. It's a theme across this whole project: verify against the real system, not against your
own confidence that the code looks right.

## Five questions an interviewer would probably ask

**"Why didn't you just keep the latest value and skip the vintage complexity?"**
Because the whole point of the project is showing I can model a revision problem correctly, and
because it's a real requirement in this domain — if you're underwriting a CRE loan and looking
back at what the macro backdrop looked like when a comp deal closed, you want the number as it
was known *then*, not the number as it reads today after two years of revisions.

**"Why Snowflake and not just Postgres, given you already had a working Postgres pipeline?"**
Two separate reasons. First, the brief: this project exists to demonstrate a cloud-warehouse
skill Postgres doesn't show. Second, practically: Snowflake's the more common ask in the roles
I'm targeting, and the DuckDB fallback means the choice doesn't cost the project portability —
anyone can clone it and run the same models with zero cloud account.

**"What was the biggest mistake you made building this, and how did you find it?"**
An unscoped `dbt build` against Snowflake also ran `dbt seed`, and `dbt seed` truncates and
reloads — it silently replaced 116,000 rows of real production data with a small four-year
DuckDB test fixture. No error, no warning. I found it because a mart column that should've had
values back to 2015 was null before mid-2022, and that didn't match what I expected to see. I
didn't just delete the bad seed and move on — I fixed it so that seed genuinely cannot run
against Snowflake anymore, at the config level, and then re-verified the fix by actually trying
to trigger the old bug again and confirming it couldn't happen.

**"Walk me through the star schema — why is it shaped the way it is?"**
Two dimensions, `dim_series` and `dim_date`, both flat, joining into one base fact at the
series/date/vintage grain, with two more views layered on top of that same fact for the latest
and point-in-time reads. I kept it a star, not a snowflake, because with 17 series there's no
real normalization win from splitting the category off into its own dimension — it'd just be
an extra join that makes the model look more complicated than the data actually is.

**"What would you build next if you kept going?"**
That used to be my answer to this question, until I actually built it: orchestration. Both
pipelines now run under a local Airflow instance (LocalExecutor, TaskFlow API,
`orchestration/`) instead of being triggered by hand or living only on a GCE cron entry. I'd
originally sketched this as Dagster, modeling the ingest and dbt project as one graph of
assets — Airflow's TaskFlow API ended up being the better call for a resume-facing project
specifically because it's the far more common ask in postings, even though Dagster's
asset-centric model arguably fits "ingest feeds a dbt build" more elegantly. Worth saying that
distinction out loud unprompted, the same way the other tradeoffs in this document are — see
`DECISIONS.md`'s Phase 8 for the full reasoning, including why local Compose over managed
Airflow, and why the live GCE cron entry stays untouched rather than being pointed at a local
Airflow instance. What's actually still missing: incremental/partitioned loading (both DAGs do
a full re-pull and MERGE every run, which only stays cheap at this data volume) and real
alerting (the failure callback logs a structured event; it doesn't page anyone yet).

## What this project honestly does not do

- **The Snowflake pipeline's schedule is local, not deployed.** `orchestration/`'s Airflow
  instance schedules both pipelines, but it only runs on demand on this machine — it isn't
  standing anywhere with an uptime guarantee the way the legacy Postgres pipeline's GCE cron
  entry is. The orchestration *capability* is real and demonstrable (`make airflow-up`); a
  genuinely production Snowflake pipeline would still need that DAG deployed somewhere
  persistent, which was deliberately out of scope — see `DECISIONS.md`'s Phase 8 for why.
- **Neither DAG does incremental loading.** Every run re-fetches full current state (all 17
  series) and MERGEs it in, rather than using Airflow's own `data_interval_start`/
  `data_interval_end` to pull just what changed. Cheap and safe at ~116K rows — including
  making backfills trivially idempotent, since a rerun and a fresh run produce the same
  result — but wouldn't stay cheap at real production volume.
- **The mart isn't point-in-time-safe by default.** `mart_cre_macro_conditions` is built from
  `fct_observations_latest` — today's best-known view of history. If you backtest against the
  mart itself, you're backtesting with revised numbers, not the numbers that were actually
  available at the time. `fct_observations_point_in_time` is the object that's actually safe
  for that, and it's a separate, deliberate object for exactly this reason — worth knowing
  which one you're querying.
- **No incremental materialization.** Every `dbt build` recomputes every model from scratch.
  Fine at ~116K raw rows; would need incremental strategies well before this got meaningfully
  bigger.
- **`real_10y_rate_pct` is a realized-inflation proxy, not a market-implied real yield.** It's
  nominal 10-year yield minus trailing CPI inflation, not a TIPS-based breakeven rate, because
  no TIPS series is in the 17-series catalog. Documented in the column description, but worth
  saying out loud unprompted rather than waiting to be caught.
- **The business-day flag doesn't know about federal holidays.** It's Monday-through-Friday
  only. A proper holiday calendar was out of scope for what this needed to prove.
- **No real alerting on either Airflow DAG.** Both have a structured on-failure callback
  (`orchestration/dags/callbacks.py`), but it logs a JSON event rather than paging anyone — no
  Slack/PagerDuty integration. The legacy Postgres path's Uptime Kuma heartbeats (from the
  original M0-M6 build) are the only real alerting in this project.
- **The DuckDB seed fixture is a point-in-time snapshot, not a live sync.** It was generated
  once from a real FRED pull and will read as increasingly "old" over time unless someone
  re-runs `scripts/generate_dbt_seeds.py`. That's an accepted tradeoff for keeping the fixture
  small and git-friendly, not an oversight, but it's a real staleness risk if this repo sits
  untouched for a long time.
- **Single warehouse, no dev/prod schema separation outside of CI.** CI gets its own throwaway
  schema per run; local development against Snowflake reads and writes the same `RAW`/
  `STAGING`/`MARTS` schemas a "production" run would. Acceptable for a single-owner portfolio
  project; would need real environment separation for anything with more than one contributor.
- **`dbt source freshness` in CI is informational, not a gate.** The `dbt-build` job runs it
  with `continue-on-error: true` — a stale source warns in the job output but doesn't fail the
  build. Deliberate, not an oversight (freshness failing usually means "nobody's run ingest
  today," not "the code is broken," and those shouldn't have the same severity) — but it's a
  real place where CI is softer than it looks at first glance, worth naming before a reviewer
  finds it and assumes it's a gap rather than a choice.
- **`fiscal_year`/`fiscal_quarter` on `dim_date` are plain aliases of the calendar year and
  quarter.** No fiscal-year convention (e.g. an October start) was specified for this domain,
  so they're not doing anything beyond what `year`/`quarter` already do. The columns exist
  because the naming convention calls for them, not because there's real fiscal logic behind
  them yet.
- **CI's `dbt-build` job reads live production `RAW` data, not a fixture.** It's the fastest,
  most realistic way to prove the transformation layer against real data without a second
  Snowflake account, but it does mean a CI run and a manually-triggered ingest run could in
  principle overlap — there's no locking between them. Not a problem in practice yet, since
  ingest isn't on a schedule (see "no scheduled ingestion" above), but it would need addressing
  before Phase 8 puts ingest on a cron.
