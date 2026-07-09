# Local development setup

The project brief is in [README.md](README.md). This file is the how-to-run for
local dev. (M2 will make the DB reproducible via `docker compose`; until then the
steps below stand up a local Postgres.)

## Prerequisites

- **Python 3.11+** (this repo is developed on 3.13).
- **Docker via Colima** (qemu backend). On an Intel Mac running macOS < 15.5 the
  default `vz` backend has broken networking, so use qemu:

  ```bash
  brew install colima docker docker-compose qemu
  colima start --vm-type qemu
  ```

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
