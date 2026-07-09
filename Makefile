# Bridge Project — task runner.
# Targets fill in as milestones land; each target notes the milestone that implements it.

.PHONY: help install test lint fmt run up down deploy

help:              ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:           ## Install runtime + dev dependencies
	pip install -r requirements.txt -r requirements-dev.txt

test:              ## Run the test suite (M1)
	pytest -q

lint:              ## Lint with ruff (M3)
	ruff check .

fmt:               ## Auto-format with ruff (M3)
	ruff format .

run:               ## Run the pipeline locally (M1: ingest -> raw -> transform -> clean)
	python -m ingest.pipeline

up:                ## Bring up app + Postgres in Docker (M2)
	docker compose up --build

down:              ## Tear down the Docker stack (M2)
	docker compose down

deploy:            ## Deploy to the live VPS (M5)
	@echo "deploy is implemented in M5 (SSH deploy to the Terraform-provisioned box)."
	@exit 1
