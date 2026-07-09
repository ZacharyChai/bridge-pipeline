# Bridge Project — task runner.
# Targets fill in as milestones land; each target notes the milestone that implements it.

.PHONY: help install test lint fmt run up down deploy db-up db-down

# Prefer the project venv if it exists, so targets never fall back to system Python.
PYTHON := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

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

run:               ## Run the pipeline locally (M1: ingest -> raw -> transform -> clean)
	$(PYTHON) -m ingest.pipeline

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
