# Project conventions

Conventions and constraints for `bridge-pipeline`. Where these conflict with a general best
practice, these win, and the reason is written down in `DECISIONS.md`.

---

## What this project is

`bridge-pipeline` ingests Federal Reserve (FRED and ALFRED) macroeconomic time series with full
revision history and models them in dbt as a dimensional warehouse for commercial real estate
credit conditions: Snowflake as the warehouse, DuckDB as a no-account local build, dbt for
transformation and testing, Airflow for orchestration, a read-only FastAPI layer on top, all
documented and CI-verified. The original single-series Postgres path is kept running alongside
it (see the README's legacy section).

## What it is for

It is a portfolio project, built to demonstrate dbt, a cloud data warehouse and dimensional
modeling on a real underwriting question. Two consequences follow:

1. **The modeling decisions are the product.** A working pipeline that makes unexplained
   choices is worth less than a slightly simpler one whose grain, keys and SCD handling are
   deliberate and documented. Optimize for defensibility, not cleverness.
2. **Every line has to be explainable.** Where a choice is non-obvious, the alternative that was
   rejected, and why, goes in `DECISIONS.md`.

## Domain angle: this is not a generic macro warehouse

The marts layer serves a **CRE underwriting context**, not generic macro reporting. Concretely:
the headline mart answers "what were macro conditions for CRE credit at a given point in time,"
combining Treasury yields and the curve, CPI, unemployment, commercial property price indices
and bank lending standards. A generic FRED warehouse is a tutorial; one built around a specific
underwriting question is a usable tool. Do not flatten it into a generic example.

---

## Stack, fixed

| Layer | Tool | Notes |
|---|---|---|
| Source | FRED API (and ALFRED for vintages) | Existing ingest code, refactor rather than replace |
| Warehouse | Snowflake, with DuckDB as the local and CI target | The Snowflake account was a time-limited trial; DuckDB is what CI and the quickstart run. See cost constraints below |
| Transformation | dbt-core + dbt-snowflake | Not dbt Cloud |
| Orchestration | Airflow | Phase 8, optional. Originally scoped as Dagster; reversed in favor of Airflow (LocalExecutor, TaskFlow) -- see DECISIONS.md's Phase 8 section for why |
| Testing | dbt tests + dbt-expectations + existing pytest | Both layers stay |
| Linting | sqlfluff (Snowflake dialect) | Enforced in CI |
| CI | GitHub Actions | Extend the existing workflow, do not replace it |
| Containerization | Docker | Already present, keep it working |

Do not add tools without a `DECISIONS.md` entry saying why. Every extra dependency has to be
defensible.

## Cost constraints, non-negotiable

- Snowflake was a time-limited, credit-limited trial. Whenever it is on: an **XS warehouse**,
  `AUTO_SUSPEND = 60` seconds, and never leave a warehouse running.
- Do not ingest the full FRED catalog. A curated set of roughly 15 to 25 series is more than
  enough to demonstrate the modeling, and a bloated warehouse demonstrates nothing extra.
- The **DuckDB profile** is the one that has to keep working: it is what CI builds and what
  anyone cloning the repo runs. A portfolio repo a recruiter cannot run is a dead portfolio repo.

## Secrets

Never commit credentials. Snowflake connection details and the FRED API key come from
environment variables, referenced in `profiles.yml` via `env_var()`. `.env.example` carries
the variable names and no values. `.gitignore` covers `.env`, `profiles.yml` if it holds
anything real, and `target/`, `dbt_packages/`, `logs/`.

---

## Naming conventions

**Models**

| Prefix | Layer | Meaning |
|---|---|---|
| `stg_` | staging | One model per source table. Renaming, casting, light cleaning only. No joins, no business logic |
| `int_` | intermediate | Joins and reshaping. Not exposed to end users |
| `dim_` | marts | Dimension table, one row per entity |
| `fct_` | marts | Fact table, one row per event or measurement at a declared grain |
| `mart_` | marts | Wide, denormalized, use-case-specific table built for consumption |

**Columns**

- Surrogate keys: `<entity>_key` (e.g. `series_key`, `date_key`).
- Natural keys: `<entity>_id` (e.g. `series_id` is FRED's own identifier).
- Booleans: `is_` or `has_` prefix.
- Timestamps: `_at` suffix. Dates: `_date` suffix.
- Never `data`, `value1`, `temp`, `new_`, or any name that will be meaningless in six months.
  The one exception is `value` on the observation fact, where it is genuinely the measure.

**SQL style**

- Lowercase keywords. Trailing commas. One column per line in SELECT lists.
- CTEs over subqueries, always. Name every CTE for what it contains, not `cte1`.
- Every model opens with an `import` CTE block (`with source as (select * from {{ ref(...) }})`)
  so dependencies are visible in the first ten lines.
- `sqlfluff` config lives in `.sqlfluff` and is the arbiter. If style and sqlfluff disagree,
  fix sqlfluff's config rather than leaving violations.

---

## Definition of done, applies to every phase

A phase is not complete until all of the following are true.

1. `dbt build` runs clean: models materialize, all tests pass.
2. `sqlfluff lint models/` returns no violations.
3. The existing pytest suite still passes. If a refactor broke a test, fix the code or update
   the test deliberately, and record which in `DECISIONS.md`.
4. Every new model has a `.yml` entry with a description, and every column has a description.
   An undocumented column is an incomplete model.
5. The GitHub Actions workflow is green.
6. `DECISIONS.md` has an entry for any non-obvious choice made in that phase.

## Things not to do

- Do not fabricate data. If a FRED series is unavailable or an API call fails, surface the
  error. A pipeline that silently substitutes plausible numbers is worse than one that crashes.
- Do not disable or `--no-` flag a failing test to make a build pass. Fix the model or fix the
  test, then explain which in `DECISIONS.md`.
- Do not delete the existing PostgreSQL path in one pass. Keep it working until Snowflake is
  verified end to end, then remove it in a single reviewable commit.
- Do not rewrite the existing pytest suite wholesale. It is evidence of prior work. Extend it.
- Do not commit `target/`, `logs/`, or `dbt_packages/`.
- Do not add a README section claiming a capability the repo does not have.

## Commit style

- Small, single-purpose commits. Conventional-commit prefixes (`feat:`, `fix:`, `refactor:`,
  `docs:`, `test:`, `chore:`).
- One commit should not span two phases.
- Each phase closes with a `DECISIONS.md` entry: what changed, what was decided and why, what
  was deferred, and what is still uncertain. Uncertainty is flagged, not presented as settled.
