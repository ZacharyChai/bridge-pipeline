# Bridge Project — task runner.
# Targets fill in as milestones land; each target notes the milestone that implements it.

.PHONY: help install test lint fmt run run-snowflake up down deploy db-up db-down dbt-debug dbt-seed dbt-build dbt-docs sqlfluff-lint sqlfluff-fix airflow-up airflow-down airflow-logs dag-test

# Prefer the project venv if it exists, so targets never fall back to system Python.
PYTHON := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
DBT := $(shell [ -x .venv/bin/dbt ] && echo .venv/bin/dbt || echo dbt)
SQLFLUFF := $(shell [ -x .venv/bin/sqlfluff ] && echo .venv/bin/sqlfluff || echo sqlfluff)
# TARGET=snowflake on the command line (e.g. `make dbt-debug TARGET=snowflake`) overrides
# .env's DBT_TARGET default -- a plain shell env override wouldn't win, since sourcing .env
# below unconditionally reassigns DBT_TARGET from the file. dbt's own --target flag always
# wins over profiles.yml's env_var() default, so that's the one override path that's reliable.
TARGET ?=
DBT_FLAGS := --project-dir dbt --profiles-dir dbt $(if $(TARGET),--target $(TARGET),)

# dbt and sqlfluff (via its dbt templater) read connection info from real shell env vars via
# profiles.yml's env_var() -- unlike the Python pipeline, dbt does NOT load .env itself. Every
# dbt-invoking target below sources .env first so SNOWFLAKE_* etc. are actually present.
LOAD_ENV := set -a; [ -f .env ] && . ./.env; set +a;

help:              ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:           ## Install runtime + dev dependencies
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

test:              ## Run the test suite (M1)
	$(PYTHON) -m pytest -q

lint:              ## Lint with ruff (M3)
	$(PYTHON) -m ruff check .

fmt:               ## Auto-format with ruff (M3)
	$(PYTHON) -m ruff format .

run:               ## Run the legacy single-series pipeline (M1: ingest -> raw -> transform -> clean, Postgres)
	$(PYTHON) -m ingest.pipeline

run-snowflake:     ## Run the Phase 2 pipeline (multi-series ALFRED ingest -> Snowflake RAW)
	$(PYTHON) -m ingest.pipeline_snowflake

db-up:             ## Local dev DB: start the Postgres container + SSH tunnel (this machine)
	docker start bridge-pg 2>/dev/null || docker run -d --name bridge-pg --restart unless-stopped \
	  -e POSTGRES_DB=bridge -e POSTGRES_USER=bridge -e POSTGRES_PASSWORD=change_me \
	  -p 5432:5432 postgres:16
	./scripts/db-tunnel.sh start

db-down:           ## Local dev DB: stop the SSH tunnel (leaves the container running)
	./scripts/db-tunnel.sh stop

up:                ## Bring up app + Postgres in Docker (M2)
	docker compose up --build

down:              ## Tear down the Docker stack (M2)
	docker compose down

deploy:            ## Deploy to the live VPS (M5)
	@echo "deploy is implemented in M5 (SSH deploy to the Terraform-provisioned box)."
	@exit 1

dbt-debug:         ## Check dbt can connect (duckdb by default; TARGET=snowflake to override)
	$(LOAD_ENV) $(DBT) debug $(DBT_FLAGS)

dbt-seed:          ## Load dbt/seeds/*.csv into RAW (duckdb only -- Snowflake RAW is populated by ingest.pipeline_snowflake, not seeded)
	$(LOAD_ENV) $(DBT) seed $(DBT_FLAGS)

dbt-build: dbt-seed ## Run + test every dbt model (duckdb by default; TARGET=snowflake to override)
	$(LOAD_ENV) $(DBT) build $(DBT_FLAGS)

dbt-docs:          ## Generate and serve dbt docs locally
	$(LOAD_ENV) $(DBT) docs generate $(DBT_FLAGS)
	$(LOAD_ENV) $(DBT) docs serve $(DBT_FLAGS)

sqlfluff-lint:     ## Lint dbt models + singular tests (Snowflake dialect, see dbt/.sqlfluff)
	$(LOAD_ENV) cd dbt && ../$(SQLFLUFF) lint models/ tests/

sqlfluff-fix:      ## Auto-fix what sqlfluff can
	$(LOAD_ENV) cd dbt && ../$(SQLFLUFF) fix models/ tests/

airflow-up:        ## Start local Airflow (LocalExecutor) orchestrating both pipelines -- http://localhost:8080
	mkdir -p orchestration/logs orchestration/plugins orchestration/config
	chmod -R 777 orchestration/logs orchestration/plugins orchestration/config
	cd orchestration && docker compose up --build -d

airflow-down:      ## Stop local Airflow and remove its containers
	cd orchestration && docker compose down

airflow-logs:      ## Tail the Airflow scheduler's logs
	cd orchestration && docker compose logs -f airflow-scheduler

dag-test:          ## Run the DAG-integrity test suite inside the Airflow container
	cd orchestration && docker compose run --rm --entrypoint /bin/bash airflow-scheduler \
	  -c "pytest -q /opt/airflow/bridge-pipeline/orchestration/tests"
