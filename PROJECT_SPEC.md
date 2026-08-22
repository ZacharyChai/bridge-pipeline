# PROJECT_SPEC.md

Phased build spec for the `bridge-pipeline` analytics engineering rebuild.

Work phases in order. Do not start a phase until the previous one meets the definition of done
in `CLAUDE.md`. Report at each phase boundary and wait for confirmation before proceeding.

**Target outcome:** a repo that evidences dbt, a cloud data warehouse, and dimensional modeling,
serving a commercial real estate credit use case, with tests and CI, that a hiring manager can
clone and run.

**Estimated effort:** 6 to 8 weeks part-time. Phases 0 to 6 are the core. Phase 8 is a bonus that
closes a separate skills gap.

---

## Phase 0: Audit and baseline

Do not write any new code in this phase.

**Tasks**

1. Read the existing repo end to end. Produce `AUDIT.md` covering: current file structure, how
   the FRED ingest works, what the PostgreSQL schema looks like, what the pytest suite covers,
   and what the GitHub Actions workflow does.
2. List which FRED series are currently ingested.
3. Identify which existing code is reusable as-is, which needs refactoring, and which is
   superseded by the new architecture.
4. Confirm the repo runs today: Docker builds, tests pass, CI is green. If it does not, fix that
   first and note what was broken.

**Acceptance criteria**

- `AUDIT.md` exists and is specific to this repo, not generic.
- A reader who has never seen the repo could explain its current data flow from the audit alone.
- Baseline confirmed green, or the breakage documented and fixed.

---

## Phase 1: Snowflake, connection, and the DuckDB fallback

**Tasks**

1. Set up a Snowflake trial account. Create `BRIDGE_DB`, schemas `RAW`, `STAGING`, `MARTS`, an
   XS warehouse with `AUTO_SUSPEND = 60`, and a dedicated role and user for dbt.
2. Install `dbt-core` and `dbt-snowflake`. Initialize the dbt project inside the repo (do not
   create a separate repo).
3. Configure `profiles.yml` using `env_var()` for every credential. Add `.env.example`.
4. Add a second dbt target, `duckdb`, so the whole project runs locally with no cloud account.
   This is the fallback for when the trial expires and for anyone cloning the repo.
5. Verify `dbt debug` passes against both targets.

**Acceptance criteria**

- `dbt debug` green on Snowflake and on DuckDB.
- No credential anywhere in git history. Check history, not just the working tree.
- `AUTO_SUSPEND` verified at 60 seconds. Document the monthly cost estimate in `DECISIONS.md`.

**Decisions to record**

Why Snowflake over BigQuery or Redshift. Why a DuckDB fallback exists. Warehouse sizing rationale.

---

## Phase 2: Ingestion into the RAW layer

**Tasks**

1. Refactor the existing FRED ingest to land data in Snowflake `RAW` rather than PostgreSQL.
   Keep the PostgreSQL path working in parallel until Phase 2 is verified.
2. Curate the series list to serve the CRE credit use case. Target 15 to 25 series across these
   groups, and record the final list with FRED series IDs in `DECISIONS.md`:
   - Treasury yields across the curve (for spread and inversion analysis)
   - SOFR or an equivalent short rate
   - CPI and core CPI
   - Unemployment rate and nonfarm payrolls
   - Commercial property price indices
   - Bank lending standards (the SLOOS series on CRE loans is directly on point)
   - CRE delinquency rates on bank balance sheets
3. Ingest **vintage data via ALFRED**, not just the current values. Preserve
   `realtime_start` and `realtime_end` on every observation. This is deliberate: macro data gets
   revised, and handling revisions correctly is the Phase 4 SCD exercise.
4. Land raw responses with minimal transformation. Raw means raw. Casting and renaming belong in
   staging.
5. Extend the pytest suite to cover the new ingest paths, including API failure handling.

**Acceptance criteria**

- `RAW` contains series metadata and observations, including vintage columns.
- Ingest is idempotent. Running it twice does not duplicate rows.
- API failures raise, and are tested.
- Row counts reconcile against the FRED API for at least three spot-checked series.

**Decisions to record**

Why these series. Why vintages are preserved. Idempotency strategy (merge key choice).

---

## Phase 3: Staging layer

**Tasks**

1. Declare sources in `models/staging/_sources.yml` with `loaded_at_field` and freshness
   thresholds.
2. One `stg_` model per raw table. Rename to project conventions, cast types explicitly, trim
   and clean. No joins, no business logic, no aggregation.
3. Materialize staging as views.
4. Add `not_null` and `unique` tests on every staging primary key.
5. Document every model and every column in `_staging.yml`.

**Acceptance criteria**

- `dbt build --select staging` clean.
- `dbt source freshness` runs and reports.
- Every staging column has a description. No exceptions.

**Decisions to record**

Materialization choice for staging. Any type-casting decision that was not obvious (FRED returns
`.` for missing values, which needs deliberate handling: document what you chose and why).

---

## Phase 4: Dimensional marts, the core of the project

This is the phase that matters most. Spend disproportionate effort here.

**Tasks**

1. **Declare the grain before writing SQL.** Write the grain statement for each planned fact
   table into `DECISIONS.md` first, then build to it. The grain of the observation fact is the
   crux of this project: one row per series per observation date per vintage.
2. Build `dim_series`: one row per FRED series. Attributes include title, frequency, units,
   seasonal adjustment, and a CRE-relevant category you assign (rates, inflation, labor,
   property, credit conditions).
3. Build `dim_date`: a proper date spine covering the full observation range, with fiscal and
   calendar attributes, quarter and month ends, and business day flags.
4. Build `fct_observations`: the measurement fact at the declared grain, with surrogate keys to
   both dimensions.
5. **Handle revisions as a Type 2 slowly changing problem.** Provide both a
   point-in-time view (what was known as of date X) and a latest-value view. This is the single
   most interesting modeling problem in the project and the best interview story in it. Do not
   shortcut it by keeping only latest values.
6. Build `mart_cre_macro_conditions`: the headline consumption table. One row per month, wide,
   combining the curve, inflation, labor, property prices, and lending standards, with derived
   measures (10y-2y spread, real rates, year-over-year changes, z-scores against a trailing
   window).
7. Generate surrogate keys with `dbt_utils.generate_surrogate_key`. Do not use raw natural keys
   as joins into facts.
8. Materialize dimensions and facts as tables, marts as tables.

**Acceptance criteria**

- Grain of every fact table is stated in its `.yml` description and enforced by a uniqueness
  test on the grain columns.
- A point-in-time query for an arbitrary past date returns the values as they were published at
  that date, not the revised ones. Prove it with a singular test.
- `mart_cre_macro_conditions` has no nulls in its key measures for the period where source data
  exists, and nulls are explained where it does not.
- Referential integrity: `relationships` tests from fact to both dimensions.

**Decisions to record**

The grain statement and why. Star versus snowflake. SCD Type 2 implementation approach and the
alternatives rejected. Surrogate key strategy. Why the mart is monthly rather than daily.
Derived-measure definitions, especially the z-score window.

---

## Phase 5: Testing and data quality

**Tasks**

1. Install `dbt-expectations` and `dbt-utils` via `packages.yml`.
2. Generic tests across the project: `not_null`, `unique`, `accepted_values`, `relationships`.
3. Distributional tests via dbt-expectations: value ranges per series type (an unemployment rate
   above 100 is a bug, a Treasury yield of 400 is a bug).
4. At least three **singular tests** covering genuine business logic. Suggested: the
   point-in-time correctness test from Phase 4; a test that no series has observations before its
   documented start date; a test that the 10y-2y spread reconciles against independently
   calculated values.
5. Configure test severity deliberately. Not everything is an error; some things are warnings.
   Document which and why.
6. Add `dbt source freshness` to the CI run.

**Acceptance criteria**

- Test coverage on every model. `dbt build` runs at least 40 tests.
- Three or more singular tests, each testing logic rather than schema.
- Severity levels set deliberately, not left at default across the board.

**Decisions to record**

Which tests are warnings rather than errors and why. What the distributional bounds are based on.

---

## Phase 6: CI and documentation

**Tasks**

1. Extend the existing GitHub Actions workflow. Do not replace it. It should now run: pytest,
   `sqlfluff lint`, `dbt build` against a CI schema, and `dbt source freshness`.
2. CI builds into an isolated schema named per pull request, and tears it down afterward.
3. `dbt docs generate` in CI, published to GitHub Pages.
4. Rewrite `README.md`: what the project does, the architecture diagram, how to run it locally
   against DuckDB in under five minutes, and a link to the hosted docs.
5. Include a lineage graph image in the README. It is the single most legible artifact for a
   recruiter skimming the repo in thirty seconds.

**Acceptance criteria**

- CI green on a pull request, including teardown.
- Docs live and reachable at a URL.
- A stranger can clone the repo and get a working DuckDB build in under five minutes, following
  the README alone. Test this by following your own instructions literally.

---

## Phase 7: The decisions record, mandatory

This phase exists because the repo owner needs to defend this work in live technical interviews,
including take-home exercises and modeling discussions. A repo he cannot explain is a liability
rather than an asset.

**Tasks**

1. Consolidate `DECISIONS.md` into a coherent document, not a running log. Structure it as: the
   decision, the alternatives considered, why this one, and what would change the answer.
2. Write `INTERVIEW_NOTES.md` containing:
   - The grain of every fact table, stated in one sentence each.
   - A plain-language explanation of the SCD Type 2 revision handling, as it would be said out
     loud in an interview, not as documentation prose.
   - The three hardest problems in the build and how they were solved.
   - Five questions an interviewer would most likely ask about this repo, with answers.
   - An honest list of what this project does not do and what you would build next with more
     time. Being able to name your own project's limitations is a strong signal.
3. Flag anywhere the implementation took a shortcut a reviewer might catch, so the owner is not
   surprised by it in an interview.

**Acceptance criteria**

- `INTERVIEW_NOTES.md` is written in spoken register, not documentation register.
- Every non-obvious choice in the repo is traceable to an entry in `DECISIONS.md`.
- The limitations section is specific and honest rather than falsely modest.

---

## Phase 8: Orchestration with Dagster, optional

> **Superseded**: this phase shipped with Airflow (LocalExecutor, TaskFlow API), not Dagster --
> see `DECISIONS.md`'s Phase 8 section for why the reversal. The tasks/acceptance criteria below
> are the original plan, kept for the record rather than rewritten.

Closes a separate gap (orchestration appears in three of eighteen target postings) and is worth
doing if the earlier phases land comfortably.

**Tasks**

1. Add Dagster. Model the FRED ingest as assets, and the dbt project as a set of Dagster assets
   via `dagster-dbt`.
2. Schedule the ingest to run daily. Add a sensor for source freshness failures.
3. Add asset checks mirroring the critical dbt tests.
4. Run Dagster in the existing Docker Compose setup.

**Acceptance criteria**

- The full graph, ingest through marts, materializes from one Dagster run.
- The asset lineage view renders correctly, and a screenshot of it is in the README.

**Decisions to record**

Dagster versus Airflow, and why Dagster was chosen here.

---

## Sequencing note

Phases 3, 4, and 5 are where the actual skill demonstration lives. Phases 0, 1, 2 are setup and
Phases 6, 7 are packaging. If time compresses, protect Phase 4 above everything else. A project
with an excellent dimensional model and a mediocre README beats the reverse in every interview
that matters.
