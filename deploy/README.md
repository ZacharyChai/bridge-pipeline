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
