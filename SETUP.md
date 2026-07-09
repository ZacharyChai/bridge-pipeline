# Local development setup

The project brief is in [README.md](README.md). This file is the how-to-run for
local dev.

## Prerequisites

- **Docker via Colima** (qemu backend). On an Intel Mac running macOS < 15.5 the
  default `vz` backend has broken networking, so use qemu:

  ```bash
  brew install colima docker docker-compose qemu
  colima start --vm-type qemu
  ```
- **Python 3.11+** (this repo is developed on 3.13) — only needed for the
  local test/dev loop below, not to run the pipeline.

## Run the whole thing with Docker (preferred)

Reproducible from a clean clone; no local Python needed. The app reaches
Postgres over the compose network, so no port-forward/tunnel is involved.

```bash
cp .env.example .env         # paste your FRED_API_KEY (free: see link below)
docker compose up --build    # starts Postgres, waits for health, runs the pipeline
```

Inspect the warehouse (data persists in the `pgdata` volume):

```bash
docker compose up -d db
docker compose exec db psql -U bridge -d bridge \
  -c "select count(*), min(obs_date), max(obs_date) from clean_observations;"
docker compose down          # stops containers; keeps the volume
```

Get a free FRED API key at
https://fred.stlouisfed.org/docs/api/api_key.html

## Local dev loop (tests + iterating without a rebuild)

For fast TDD you can run against a local Postgres + the venv instead of rebuilding
the image each change.

## One-time setup

```bash
python3.13 -m venv .venv
make install                 # installs runtime + dev deps into the venv
cp .env.example .env         # then paste your FRED_API_KEY into .env
```

Get a free FRED API key at
https://fred.stlouisfed.org/docs/api/api_key.html

## Run

```bash
make db-up      # start the Postgres container + SSH tunnel (see note below)
make test       # pytest — unit tests always run; integration runs if the DB is up
make run        # ingest DGS10 from FRED -> raw table -> transform -> clean table
```

Inspect the result:

```bash
docker exec bridge-pg psql -U bridge -d bridge \
  -c "select count(*), min(obs_date), max(obs_date) from clean_observations;"
```

## Note on the DB tunnel (this machine only)

Colima's automatic host port-forward is broken on this Intel/macOS-14 host, so
`make db-up` also opens an SSH tunnel (`scripts/db-tunnel.sh`) mapping
`localhost:15432` -> the container's `5432`. That's why `.env` uses port `15432`.
`make db-down` closes the tunnel. None of this is needed once M2's compose runs
the app and Postgres on a shared Docker network.
