# deploy/ — Continuous delivery + schedule (M5)

On every merge to `main`, CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)):

1. **build-and-push** — builds the image and pushes it to GHCR
   (`ghcr.io/<owner>/bridge-pipeline:latest` + `:<sha>`).
2. **deploy** — over SSH to the VPS:
   - copies [`docker-compose.prod.yml`](docker-compose.prod.yml),
     [`remote-deploy.sh`](remote-deploy.sh), [`bridge-pipeline.cron`](bridge-pipeline.cron),
     and a rendered `.env` to the box,
   - runs [`remote-deploy.sh`](remote-deploy.sh): logs in to GHCR, brings up
     Postgres, pulls the new image, **runs the pipeline once**, and installs the
     daily **cron** at `/etc/cron.d/bridge-pipeline`.

The warehouse (Postgres) runs continuously with a named volume; the pipeline is
a batch job the cron runs daily (`--profile batch run --rm pipeline`).

## Required GitHub Actions secrets

Set these in **Settings → Secrets and variables → Actions**:

| Secret | What |
|---|---|
| `DEPLOY_HOST` | VPS public IP (from `terraform output instance_ip`) |
| `DEPLOY_USER` | login user, e.g. `deploy` |
| `DEPLOY_SSH_KEY` | **private** key whose public half is on the box (see below) |
| `FRED_API_KEY` | your FRED key |
| `POSTGRES_PASSWORD` | password for the warehouse |

`GITHUB_TOKEN` is provided automatically and is used to push to and pull from GHCR.

The `deploy` job is **opt-in**: it stays skipped (keeping `main` green) until you
enable it, after the box exists and the secrets above are set:

```bash
gh variable set DEPLOY_ENABLED --body true
```

## One-time: give CI its own SSH key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/bridge_deploy -N ""      # no passphrase
# Put the PUBLIC key on the box via Terraform:
cd infra
#   in terraform.tfvars:  deploy_pubkey = "ssh-ed25519 AAAA... "
terraform apply
# Put the PRIVATE key in the DEPLOY_SSH_KEY GitHub secret:
gh secret set DEPLOY_SSH_KEY < ~/.ssh/bridge_deploy
gh secret set DEPLOY_HOST --body "$(cd infra && terraform output -raw instance_ip)"
gh secret set DEPLOY_USER --body deploy
gh secret set FRED_API_KEY --body "$FRED_API_KEY"
gh secret set POSTGRES_PASSWORD --body "choose-a-strong-password"
```

## Verify (after a merge to main)

```bash
ssh deploy@<ip>
docker compose -f /opt/bridge/docker-compose.prod.yml exec db \
  psql -U bridge -d bridge -c "select count(*), max(obs_date) from clean_observations;"
cat /etc/cron.d/bridge-pipeline        # the daily schedule
tail -n 40 /opt/bridge/pipeline.log    # cron run output
```

> Note: the `deploy` job needs SSH reachability from GitHub's runners. Either
> widen `ssh_source_ranges` to allow GitHub Actions egress, or run deploys from a
> self-hosted runner / temporarily open SSH. For a private hobby box the simplest
> path is a broad SSH range guarded by key-only auth.

## Monitoring + backup (M6)

**Uptime Kuma** runs as a container in `docker-compose.prod.yml`, bound to
`127.0.0.1:3001` only — never exposed to the internet. Reach its dashboard via
an SSH tunnel:

```bash
ssh -L 3001:localhost:3001 deploy@<ip>
# then open http://localhost:3001 in a browser
```

One-time setup (Kuma has no config API, so this is done by hand in the UI):

1. First visit creates the admin account — choose your own username/password.
2. Add a **Postgres** monitor: hostname `db`, port `5432`, database `bridge`,
   user `bridge` (password from the `POSTGRES_PASSWORD` secret) — polls the
   warehouse directly.
3. Add a **Push** monitor (type "Push"), heartbeat interval ~26h (a bit more
   than the 24h cron cycle, so a single late run doesn't false-alarm). Copy the
   push URL it generates.
4. `gh secret set UPTIME_KUMA_PUSH_URL --body '<the push URL>'` — the next
   deploy (or the next `run-pipeline.sh` cron run) starts pinging it. Until
   this secret exists, `run-pipeline.sh` silently skips the ping.

**Backups**: `backup.sh` runs daily at 05:30 UTC (before the pipeline run),
`pg_dump`s the warehouse, gzips it to `/opt/bridge/backups/`, and prunes
anything older than 14 days.

**Restore** (documented and exercised once, not just written):

```bash
ssh deploy@<ip>
cd /opt/bridge
LATEST=$(ls -t backups/*.sql.gz | head -1)
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U bridge -c "CREATE DATABASE restore_test;"
gunzip -c "$LATEST" | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U bridge -d restore_test
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U bridge -d restore_test -c "select count(*) from clean_observations;"
# compare against the live count, then clean up:
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U bridge -c "DROP DATABASE restore_test;"
```
