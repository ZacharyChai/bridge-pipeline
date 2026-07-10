# bridge-pipeline

![CI](https://github.com/ZacharyChai/bridge-pipeline/actions/workflows/ci.yml/badge.svg)

A small, production-shaped data pipeline: it ingests a macro-economic series from
the [FRED API](https://fred.stlouisfed.org/), loads the raw data into Postgres,
transforms it into a clean, typed table, and gates the result behind automated
data-quality checks. Everything runs in Docker and ships through CI.

The default series is **DGS10** (10-Year Treasury Constant Maturity Rate); the
source is a single config value, so pointing it at another FRED series changes
only the ingest URL and the quality thresholds.

## Architecture

```
FRED API  ->  Python ingest  ->  raw_observations (Postgres)
                                        |
                          transform + data-quality gate
                                        |
                                clean_observations (Postgres)
```

- **ingest** ([`ingest/`](ingest/)) — thin HTTP client; raw string rows in, out.
- **transform** ([`transform/transform.py`](transform/transform.py)) — pure
  function: drops FRED's `"."` missing markers, coerces types, de-duplicates on
  the `(series_id, date)` primary key, sorts chronologically.
- **quality gate** ([`transform/quality.py`](transform/quality.py)) — asserts no
  null keys, row count in range, unique primary key, numeric values, and
  freshness before the clean table is written. A failure aborts the run.
- **warehouse** ([`db.py`](db.py)) — SQLAlchemy Core; idempotent upserts so
  re-running the pipeline is safe.

## Stack

Python 3.13 · Postgres 16 · Docker + docker-compose · pytest · ruff ·
GitHub Actions. Terraform + cron + monitoring are planned (see status below).

## Quickstart

Runs from a clean clone with no local Python — the app talks to Postgres over the
compose network.

```bash
cp .env.example .env          # paste a free FRED API key
docker compose up --build     # starts Postgres, waits for health, runs the pipeline
```

Then inspect the warehouse:

```bash
docker compose up -d db
docker compose exec db psql -U bridge -d bridge \
  -c "select count(*), min(obs_date), max(obs_date) from clean_observations;"
```

Free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
Full local-dev instructions (including the venv test loop): [SETUP.md](SETUP.md).

## Testing & CI

```bash
make test        # pytest; unit tests need no DB, integration runs if one is up
make lint        # ruff check + format
```

Test-driven throughout: the suite covers ingest shape, transform behaviour, and
each data-quality check. On every pull request, GitHub Actions runs ruff and the
full pytest suite against a Postgres service container; on merge to `main` it
builds the Docker image. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Project status

Built milestone by milestone:

| Milestone | Status |
|---|---|
| M0 — repo scaffold | ✅ |
| M1 — pipeline core (TDD) | ✅ |
| M2 — containerize (Docker + compose) | ✅ |
| M3 — CI (GitHub Actions) | ✅ |
| M4 — provision a Linux VPS with Terraform | ✅ |
| M5 — continuous delivery + cron schedule | ✅ |
| M6 — monitoring + backup/restore | planned |

## Repository layout

```
ingest/        FRED ingest + pipeline entry point (python -m ingest.pipeline)
transform/     pure transform + data-quality checks
db.py          warehouse schema, upserts, reads
config.py      typed settings from env / .env
tests/         pytest suite (unit + integration)
infra/         Terraform (M4)
scripts/       local-dev helpers
.github/       CI workflow
```
