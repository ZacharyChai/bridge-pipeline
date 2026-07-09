# Bridge Project: Containerized Data Pipeline on Linux

A minimal, production-shaped data pipeline that checks every infrastructure must-have from the SWE/DE-infra job descriptions and showcases data fluency in the same artifact. Built to be finished in a few focused weeks, not admired as a plan.

## The one rule: scope discipline

The goal is reps, not impressiveness. The smallest thing that honestly runs in production and touches every required line wins. The instinct to make it flashy is the failure mode.

**Definition of done:** a Dockerized pipeline that ingests real data on a schedule, transforms and loads it into a warehouse, runs on a real Linux server you provisioned with code, ships via CI/CD, and has tests, monitoring, and a backup/restore path. Running. Reachable. Reproducible from a clean clone.

**Do NOT add** (all scope creep, none check a new box on the target JDs):
- A frontend or dashboard. The output is a clean table in the warehouse. That's the deliverable.
- A real ML model. Predictive modeling is already covered by your churn project. Skip it here.
- Kubernetes, a message queue, streaming. Overkill for one pipeline; weeks of yak-shaving for zero incremental JD coverage.
- Multiple data sources or "just one more" feature. One source, done fully, beats three half-built.

## Architecture (minimal)

```
Public API  ->  Python ingest  ->  raw table (Postgres)
                                        |
                              SQL/Python transform (tested)
                                        |
                                  clean table (Postgres)
```

Everything runs in Docker. Postgres is the "warehouse" (free, self-hosted, and the setup teaches real Linux DB ops; swap to Snowflake later is a config change, not a redesign). A scheduler triggers the run. The whole thing lives on a small Linux VPS you own.

## Stack and why

- **Python** for ingest and transform. Your language. `requests` + `psycopg`/`sqlalchemy`, nothing exotic.
- **Postgres in Docker** as the warehouse. Real DB ops, free, production-shaped.
- **Docker + docker-compose** for containerization (app + Postgres). Checks the Docker must-have.
- **pytest** for TDD. Tests written before logic, including data-quality assertions (row counts, null checks, schema, freshness).
- **GitHub Actions** for CI/CD. Lint + test on PR; build image and deploy on merge to `main`.
- **Terraform** for IaC. Provisions the VPS and firewall rules. Checks the IaC must-have.
- **bash** for server setup and the deploy script. Checks Linux + bash.
- **cron** on the box for scheduling (upgrade to Airflow only if a specific JD demands it). More cron and less orchestration framework is the right v1 call.
- **Basic monitoring:** structured logging + a healthcheck + a single-container uptime monitor (e.g. Uptime Kuma). Enough to honestly say "monitoring," no Prometheus/Grafana rabbit hole in v1.
- **Host:** Hetzner or DigitalOcean droplet, roughly 5 to 6 USD a month. Real cost, real reps, trivial money. This spend is the point: it forces genuine deploy-and-maintain experience you cannot fake locally.

## Data domain

Pick a source you already understand so the transform logic is where your data fluency shows, not a distraction:
- **Default:** an economic/markets series from a free API (FRED for macro series, or a free FX/markets endpoint). Finance-relevant, clean, well-documented.
- **Alternative you already own:** Singapore property/HDB data. You know the domain cold, which means the transformation and data-quality rules will be genuinely thoughtful rather than toy.

Either works. The infra is identical; only the ingest URL and the transform SQL change.

## Milestones

Each milestone is one sitting or a few, produces something that runs, and earns a specific resume line. Do them in order; do not start the next until the current one is green.

### M0 - Repo scaffold
- Git repo, clear structure (`ingest/`, `transform/`, `tests/`, `infra/`, `.github/workflows/`), this brief as the README, a `Makefile` or `justfile` with `make test`, `make run`, `make deploy`.
- **Done when:** `git log` shows a clean initial commit and the structure is in place.

### M1 - Pipeline core, test-driven
- Write the pytest tests first: ingest returns expected shape, transform produces expected rows, data-quality checks (no nulls in keys, row count in expected range, no duplicate primary keys, data is fresh).
- Then implement ingest -> raw table -> transform -> clean table against those tests.
- **Done when:** `pytest` is green locally and the clean table populates from a real API pull.
- **Earns:** *"Built an ETL pipeline in Python and SQL using test-driven development, with automated data-quality checks (schema, null, freshness, uniqueness)."*
- **JD lines:** ETL/ELT and pipeline development; data quality and basic testing; commitment to TDD.

### M2 - Containerize
- Dockerfile for the pipeline; docker-compose brings up app + Postgres together.
- **Done when:** `docker compose up` runs the full pipeline against a containerized Postgres from a clean clone, no local Python setup needed.
- **Earns:** *"Containerized the pipeline and its warehouse with Docker and docker-compose for reproducible, environment-independent runs."*
- **JD line:** practical experience with Docker and containerization.

### M3 - Continuous integration
- GitHub Actions workflow: on every PR, lint (ruff/flake8) and run pytest; on merge to `main`, build the image.
- **Done when:** a PR shows green checks and a broken test blocks the merge.
- **Earns:** *"Set up a CI pipeline (GitHub Actions) running lint and test gates on every change, blocking merges on failure."*
- **JD line:** continuous integration.

### M4 - Provision the server with code
- Terraform provisions the VPS and a firewall (SSH + only what's needed). A bash bootstrap script hardens the box: non-root user, SSH key only, `ufw`, installs Docker.
- **Done when:** `terraform apply` from zero gives you a reachable, hardened Linux box, and `terraform destroy` tears it down cleanly.
- **Earns:** *"Provisioned and hardened Linux infrastructure as code using Terraform, with bash bootstrap scripts for user setup, firewall, and Docker install."*
- **JD lines:** infrastructure as code; Linux and bash scripting; deploying/maintaining Linux systems.

### M5 - Continuous delivery + schedule
- Extend the Actions workflow: on merge to `main`, deploy the new image to the VPS (SSH deploy script) and restart the service. Schedule the pipeline with cron on the box.
- **Done when:** merging a change auto-deploys to the live server, and the pipeline runs on schedule without you touching it.
- **Earns:** *"Implemented continuous delivery: merges auto-deploy to a live Linux host via SSH; scheduled orchestration with cron."*
- **JD lines:** continuous delivery; deploying and maintaining Linux systems.

### M6 - Monitoring + reliability
- Structured logging to a file/stdout. A healthcheck the uptime monitor pings. A documented, tested Postgres backup-and-restore path (`pg_dump` on a cron, and prove you can restore it).
- **Done when:** the uptime monitor shows the service, logs are inspectable via SSH, and you have successfully restored the DB from a backup at least once.
- **Earns:** *"Added monitoring (uptime checks, structured logging) and a tested backup/restore procedure for disaster recovery."*
- **JD lines:** monitoring and maintaining Linux systems; recommend ways to improve data reliability and quality; disaster recovery.

## What this unlocks on the resume

After M6, you can honestly write, and defend in an interview, every one of these:

- Docker and containerization: practical, hands-on.
- TDD, CI/CD, IaC: demonstrated, not claimed.
- Linux and bash: you provisioned, hardened, deployed to, and maintained a real box.
- Deploy/troubleshoot/monitor/maintain Linux systems: the whole M4-M6 arc.
- Plus the data-fluency layer (pipeline design, data-quality testing, warehouse modeling) that a generic infra candidate won't have, which is the differentiator above the bar.

One project, every must-have, and the data angle that separates you from the pure-infra applicants.

## Working it in Claude Code

Run the build in Claude Code (terminal or desktop), not a chat window. It works inside the repo, runs the commands, writes and debugs alongside you across the weeks. Suggested flow:

1. Create the repo, drop this file in as `README.md`.
2. Open the repo in Claude Code.
3. Tackle one milestone per session: "Let's do M1. Write the failing tests first, then implement." Keep it to the milestone; resist jumping ahead.
4. Commit at every green milestone. The git history becomes proof of the reps.

## Guardrails

- If a milestone isn't green, do not start the next. Half-built milestones are how projects die at 60%.
- When tempted to add something, ask: does this check a JD line I don't already have? If no, cut it.
- The VPS costs real money and that's intentional. Keeping it running and healthy IS the Linux-ops rep. Don't tear it down until you've stopped using it as a talking point.
- Timebox to a few focused weeks. Shipped and modest beats elaborate and abandoned.
