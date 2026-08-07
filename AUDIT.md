# AUDIT.md

Phase 0 audit of `bridge-pipeline` as it stands before the dbt/Snowflake rebuild. Written
2026-08-05, against commit `edaef50` on `main`.

---

## 1. Current file structure

```
bridge-pipeline/
├── Dockerfile                     runtime image: pip install -> non-root user -> run pipeline
├── docker-compose.yml             local dev stack: postgres + pipeline, shared network
├── Makefile                       install/test/lint/fmt/run/up/down/db-up/db-down/deploy
├── pyproject.toml                 ruff config (py311 target, line-length 100), pytest config
├── requirements.txt               requests, psycopg[binary], SQLAlchemy, python-dotenv
├── requirements-dev.txt           pytest, ruff
├── config.py                      typed Settings dataclass, loaded from env/.env
├── db.py                          SQLAlchemy Core: DDL, idempotent upserts, one read helper
├── ingest/
│   ├── fred.py                    FRED HTTP client: fetch + parse one series' observations
│   └── pipeline.py                orchestrates ingest -> raw -> transform -> quality -> clean
├── transform/
│   ├── transform.py                pure function: clean/type/dedupe raw rows
│   └── quality.py                  5 data-quality checks + run_all_checks gate
├── tests/                          pytest suite (unit + 1 integration test), 15 tests total
├── scripts/db-tunnel.sh            SSH tunnel for local Postgres (Colima port-forward workaround)
├── infra/                          Terraform: GCE VM provisioning + hardening (M4)
├── deploy/                         prod compose, remote-deploy.sh, cron, backup.sh (M5/M6)
├── .github/workflows/ci.yml        lint-and-test -> build-and-push -> deploy (opt-in)
├── README.md, SETUP.md             project overview + local-dev walkthrough
└── .env / .env.example             FRED_API_KEY, FRED_SERIES_ID, POSTGRES_* (gitignored)
```

`infra/` and `deploy/` are artifacts of a prior project (the "Bridge Project" containerized-pipeline
brief, M0–M6, completed 2026-07-15): a hardened GCE `e2-micro` VM at a static IP runs this stack
today via a daily cron job, with Uptime Kuma monitoring and nightly `pg_dump` backups. That box is
still live and still pulling FRED data daily — it is out of scope for this audit but relevant
context: it currently depends on `deploy/docker-compose.prod.yml`, which points at the Postgres
path this rebuild will eventually retire.

## 2. How the FRED ingest works today

`ingest/fred.py` is a thin, single-series HTTP client:

- `fetch_observations(series_id, api_key, ...)` calls `GET /fred/series/observations` for exactly
  **one** `series_id`, with `file_type=json`. No pagination, no retry logic.
- `parse_observations(payload, series_id)` extracts only `series_id`, `date`, `value` from each
  observation and **discards `realtime_start`/`realtime_end`**, even though FRED's response
  includes them (visible in the test fixture `SAMPLE_PAYLOAD` in `tests/test_ingest.py`). There is
  no ALFRED usage — this is a current-value pull, not a vintage pull.
- Raw values are preserved verbatim, including FRED's `"."` missing-observation marker — cleaning
  is deliberately deferred to `transform/`.
- No explicit handling of HTTP failures beyond `resp.raise_for_status()` (which raises
  `requests.HTTPError`); nothing catches or wraps it, and there is no test exercising a failed
  request. `ingest/pipeline.py`'s `main()` only catches `DataQualityError`, so an API failure
  today propagates as an uncaught exception with a non-zero exit — correct behavior per this
  project's "never silently substitute data" rule, but currently untested.

`ingest/pipeline.py` (`python -m ingest.pipeline`, or `make run`) is the entry point:

```
fetch_observations -> load_raw (upsert into raw_observations)
                   -> transform (Python-side cleaning)
                   -> run_all_checks (quality gate; non-zero exit on failure)
                   -> load_clean (upsert into clean_observations)
```

The quality gate uses fixed bounds tuned for one series (`DGS10`): `MIN_ROWS=1_000`,
`MAX_ROWS=100_000`, `MAX_AGE_DAYS=7`. These bounds are hardcoded in `pipeline.py`, not
per-series — a second, lower-frequency series (e.g. a monthly CPI print) would need different
bounds, which the current design has no way to express.

## 3. What the PostgreSQL schema looks like

`db.py` defines two tables via raw DDL, created idempotently on every run:

```sql
raw_observations (series_id TEXT, obs_date DATE, value TEXT, fetched_at TIMESTAMPTZ DEFAULT now(),
                   PRIMARY KEY (series_id, obs_date))

clean_observations (series_id TEXT, obs_date DATE, value DOUBLE PRECISION,
                     loaded_at TIMESTAMPTZ DEFAULT now(),
                     PRIMARY KEY (series_id, obs_date))
```

Both tables upsert on `(series_id, obs_date)` via `ON CONFLICT ... DO UPDATE`, so re-running the
pipeline is safe (verified by `tests/test_pipeline_integration.py`). Note there is no vintage
dimension anywhere in this schema — `obs_date` is the only date column, so a revised value simply
overwrites the prior one. This is the exact gap Phase 4's SCD Type 2 work is meant to close: today
there is no `realtime_start`/`realtime_end`, so point-in-time queries are not possible against
this data at all, not even in a naive form.

`series_id` is part of the primary key on both tables even though only one series is ever loaded
in practice — the schema was evidently designed to be multi-series-ready but has never been
exercised that way.

## 4. What the pytest suite covers

15 tests across four files, all currently passing:

| File | Tests | Covers |
|---|---|---|
| `test_ingest.py` | 3 | payload parsing shape, empty payload, request building via a fake `requests.Session` (no network) |
| `test_transform.py` | 4 | drops FRED's `"."` and `None` markers, type coercion (str→float, str→date), primary-key dedup (last write wins), empty input |
| `test_quality.py` | 7 | each of the 5 quality checks individually, plus the happy-path combination via `run_all_checks` |
| `test_pipeline_integration.py` | 1 | full round trip (raw insert → transform → clean insert → read back) against a real Postgres; `pytest.mark.integration`, auto-skips via a `ping()` fixture when no Postgres is reachable |

Notably **not** covered: API failure handling (no test exercises `fetch_observations` raising on
a non-2xx response or malformed payload) — this is an explicit Phase 2 acceptance criterion
("API failures raise, and are tested") and is a real gap today, not just a formality.

`pyproject.toml` registers the `integration` marker and sets `testpaths = ["tests"]`. Ruff lint
config: `select = ["E", "F", "I", "UP", "B"]`, line length 100, target `py311`.

## 5. What the GitHub Actions workflow does

`.github/workflows/ci.yml`, three jobs:

1. **`lint-and-test`** (every PR and every push to `main`): spins up a real `postgres:16` service
   container, installs deps, runs `ruff check .` + `ruff format --check .`, then `pytest -q` — so
   the integration test actually executes in CI rather than skipping.
2. **`build-and-push`** (on push to `main`, gated on job 1 passing): builds the Docker image and
   pushes `:latest` and `:<sha>` to GHCR.
3. **`deploy`** (on push to `main`, gated on job 2 **and** the repo variable
   `DEPLOY_ENABLED == 'true'`): SCPs the compose/cron/backup files and a rendered `.env` to the
   live GCE box over SSH, then runs the remote deploy script.

The repo is private on GitHub Free, so a red check does not hard-block merges via branch
protection (documented as a known, accepted limitation in `SETUP.md`) — CI is advisory but still
flags failures.

## 6. FRED series currently ingested

**Exactly one, at a time**: whatever `FRED_SERIES_ID` is set to, defaulting to **`DGS10`**
(10-Year Treasury Constant Maturity Rate) per `.env.example` and `config.py`. There is no series
catalog, list, or loop anywhere in the code — multi-series ingestion does not exist today despite
the schema's `series_id` column suggesting it was anticipated. The live GCE box is currently
pulling only `DGS10` daily (per its `prod.env`, rendered by the CI deploy job).

## 7. Baseline confirmation

- **Docker build**: succeeds. `docker build .` completed cleanly (verified locally this session
  after starting Colima, which was not running).
- **Tests**: pass. Verified two ways — (a) the most recent CI run (`gh run view` on run
  `30736761241`, 2026-08-02) shows `15 passed in 0.78s` with a real Postgres service container,
  so the integration test genuinely ran and passed, not just skipped; (b) a clean-room local run
  this session (fresh `python:3.13-slim` container, source copied out to a plain path, deps
  installed from `requirements.txt`/`requirements-dev.txt`) shows `14 passed, 1 deselected` for
  the unit-only suite (`-m "not integration"`).
- **CI**: green. Last five runs on `main` all completed successfully; most recent is the
  2026-08-02 README docs commit.

**One environment issue found and fixed, not a code defect:** running `pytest` directly against
the repo's own `.venv` (under `~/Desktop/bridge-pipeline`, inside iCloud Drive's Desktop sync)
hung indefinitely. Root cause: several files under `.venv/lib/.../sqlalchemy/` had been evicted
to iCloud to save local disk space (macOS APFS `dataless` placeholder flag) — importing
SQLAlchemy tried to read one of those files and blocked on an on-demand iCloud download that
never completed, rather than erroring. Confirmed via `faulthandler.dump_traceback_later`, which
caught the hang inside `importlib._bootstrap_external.get_data` reading
`sqlalchemy/engine/create.py`, and via `stat -f "%Sf"` showing `hidden,compressed,dataless` on
that file. Worked around by testing in a container against a copy of the source outside iCloud
sync; the underlying `.venv` is still affected. **Recommend before Phase 1**: delete and
recreate `.venv` (`rm -rf .venv && python3.13 -m venv .venv && make install`), since Phase 1
adds `dbt-core`/`dbt-snowflake`, which are large dependency trees that will make this worse if
left unaddressed. Longer term, keeping build directories like `.venv`, `dbt_packages/`, and
`target/` off an iCloud-synced path (or excluding them from iCloud) avoids this entirely.

## 8. Reusable vs. refactor vs. superseded

**Reusable as-is**

- `tests/` structure and conventions (fake-session pattern for `ingest`, pure-function testing
  for `transform`, real-Postgres integration test gated on reachability) — extend, don't replace,
  per the project rules.
- `.github/workflows/ci.yml` skeleton (job structure, Postgres service container pattern,
  GHCR build/push) — extend with dbt/sqlfluff steps rather than rewritten.
- `pyproject.toml` ruff config, `Makefile` target pattern, `Dockerfile` non-root-user pattern.
- `infra/` and `deploy/` (Terraform + GCE + cron + Uptime Kuma + backup) — unrelated to the
  warehouse choice; the live box can keep running the legacy Postgres path until it's
  deliberately retired, and could later host Dagster (Phase 8) if desired.
- `config.py`'s pattern (one typed `Settings` object, no bare `os.environ` reads elsewhere) —
  worth carrying into whatever config Snowflake/dbt credentials need, even though the concrete
  fields change.

**Needs refactoring**

- `ingest/fred.py` — currently single-series, current-value-only. Phase 2 needs it to (a) loop
  over a curated list of 15–25 series, (b) hit ALFRED instead of the plain FRED endpoint to
  capture `realtime_start`/`realtime_end`, and (c) land output aimed at Snowflake `RAW` rather
  than (or in addition to, during the parallel-run period) Postgres `raw_observations`.
- `ingest/pipeline.py`'s hardcoded `MIN_ROWS`/`MAX_ROWS`/`MAX_AGE_DAYS` — tuned for one daily
  series; needs to become per-series or per-frequency once multiple series with different
  cadences (daily yields vs. monthly CPI vs. quarterly delinquency rates) are ingested.
- `db.py` — the upsert/DDL pattern (idempotent load keyed on a natural/business key) is worth
  preserving conceptually, but the implementation is Postgres-specific SQL and will not carry
  over to a Snowflake `RAW` loader as-is.

**Superseded by the new architecture**

- `transform/transform.py` and `transform/quality.py`'s *production code path* — once ingest
  lands genuinely raw data in Snowflake `RAW` (per Phase 2/3's "raw means raw" rule) and dbt
  staging models do the casting/cleaning in SQL (per the `stg_` convention in `CLAUDE.md`), the
  Python-side cleaning step is redundant for the new pipeline. Per project rules the *tests*
  for this logic should not be deleted (they're evidence of prior TDD work); the equivalent
  logic should be reimplemented in dbt staging models and the FRED `"."`-marker handling
  decision re-documented in `DECISIONS.md` at that point, since it's the same "obvious to miss"
  detail the original brief called out.
- `db.py`'s Postgres schema/upsert functions — superseded by Snowflake `RAW` tables once Phase 2
  is verified end to end. Per `CLAUDE.md`, the Postgres path stays working in parallel until
  then, then gets removed in one single reviewable commit — it is not being removed in this
  phase.

## 9. Net assessment

The existing pipeline is small, well-tested for what it does, and honest about its own scope (the
README already states plainly that it ingests one series). It gives the rebuild a clean
foundation — good test conventions, good CI shape, good config discipline — but essentially none
of its data-shaping logic (single series, current-value-only, Postgres-specific, one-size-fits-all
quality bounds) survives Phase 2–4 unchanged. The rebuild is closer to "new ingest and new
warehouse, old scaffolding" than "extend the existing pipeline."
