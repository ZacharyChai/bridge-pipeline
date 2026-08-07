# CLAUDE.md

Project conventions and constraints for `bridge-pipeline`. Read this before doing anything. If
an instruction here conflicts with a general best practice you would otherwise apply, this file
wins.

---

## What this project is

`bridge-pipeline` currently ingests Federal Reserve (FRED) macroeconomic time series into a
PostgreSQL warehouse, containerized with Docker, covered by pytest and run in GitHub Actions CI.

We are rebuilding its transformation layer into a modern analytics engineering stack:
Snowflake as the warehouse, dbt for transformation and testing, dimensional models in the
marts layer, orchestrated by Dagster, documented and CI-verified.

## Why we are doing it

This is a portfolio artifact for a job search targeting US analytics engineering and data
analyst roles. It exists to demonstrate three specific competencies that recruiters screen for
and that the current repo does not evidence: dbt, a cloud data warehouse, and dimensional
modeling.

Two consequences follow from that, and they matter more than they might seem:

1. **The modeling decisions are the product.** A working pipeline that makes unexplained
   choices is worth less here than a slightly simpler one whose grain, keys, and SCD handling
   are deliberate and documented. Optimize for defensibility, not cleverness.
2. **The owner must be able to explain every line in an interview.** Where you make a
   non-obvious choice, write down the alternative you rejected and why. Phase 7 depends on this.

## Domain angle: this is not a generic macro warehouse

The owner's background is commercial real estate and CMBS credit. The marts layer must serve a
**CRE underwriting context**, not generic macro reporting. Concretely: the headline mart answers
"what were macro conditions for CRE credit at a given point in time," combining Treasury yields
and the curve, CPI, unemployment, and commercial property price indices.

This is a deliberate differentiator. A generic FRED warehouse is a tutorial. One that serves a
domain the owner can speak to fluently is an interview asset. Do not flatten it into a generic
example.

---

## Stack, fixed

| Layer | Tool | Notes |
|---|---|---|
| Source | FRED API (and ALFRED for vintages) | Existing ingest code, refactor rather than replace |
| Warehouse | Snowflake | Trial account. See cost constraints below |
| Transformation | dbt-core + dbt-snowflake | Not dbt Cloud |
| Orchestration | Dagster | Phase 8, optional but preferred over Airflow here |
| Testing | dbt tests + dbt-expectations + existing pytest | Both layers stay |
| Linting | sqlfluff (Snowflake dialect) | Enforced in CI |
| CI | GitHub Actions | Extend the existing workflow, do not replace it |
| Containerization | Docker | Already present, keep it working |

Do not introduce additional tools without flagging it first. Every extra dependency is another
thing the owner has to defend in an interview.

## Cost constraints, non-negotiable

- Snowflake trial is time-limited and credit-limited. Use an **XS warehouse**, set
  `AUTO_SUSPEND = 60` seconds, and never leave a warehouse running.
- Do not ingest the full FRED catalog. A curated set of roughly 15 to 25 series is more than
  enough to demonstrate the modeling, and a bloated warehouse demonstrates nothing extra.
- Build a **DuckDB fallback profile** in Phase 1 so the project still runs after the trial
  expires. A portfolio repo a recruiter cannot run is a dead portfolio repo.

## Secrets

Never commit credentials. Snowflake connection details and the FRED API key come from
environment variables, referenced in `profiles.yml` via `env_var()`. Add a
`.env.example` with the variable names and no values. Verify `.gitignore` covers `.env`,
`profiles.yml` if it holds anything real, and `target/`, `dbt_packages/`, `logs/`.

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

A phase is not complete until all of the following are true. Do not report a phase as finished
otherwise, and do not proceed to the next one.

1. `dbt build` runs clean: models materialize, all tests pass.
2. `sqlfluff lint models/` returns no violations.
3. The existing pytest suite still passes. If a refactor broke a test, fix the code or update
   the test deliberately and say which you did.
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

## Commit and communication style

- Small, single-purpose commits. Conventional-commit prefixes (`feat:`, `fix:`, `refactor:`,
  `docs:`, `test:`, `chore:`).
- One commit should not span two phases.
- When you finish a phase, report: what changed, what you decided and why, what you deferred,
  and anything you are uncertain about. Flag uncertainty explicitly rather than presenting a
  guess as settled.
