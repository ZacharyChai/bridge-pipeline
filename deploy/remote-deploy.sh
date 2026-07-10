#!/usr/bin/env bash
# Runs ON THE VPS, invoked over SSH by the deploy job. Expects these env vars:
#   GHCR_USER, GHCR_TOKEN  -- to pull the private image from GHCR
# and these files already scp'd to /tmp:
#   docker-compose.prod.yml, prod.env, bridge-pipeline.cron
set -euo pipefail

APP_DIR=/opt/bridge

# App dir owned by the deploy user.
sudo mkdir -p "$APP_DIR"
sudo chown "$(id -un)":"$(id -gn)" "$APP_DIR"

mv /tmp/docker-compose.prod.yml "$APP_DIR/docker-compose.prod.yml"
mv /tmp/prod.env "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

cd "$APP_DIR"

# Authenticate to GHCR just long enough to pull the new image.
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

# Bring up the warehouse, pull the latest pipeline image, and run once now so a
# merge produces a fresh load immediately (subsequent runs are on cron).
docker compose -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.prod.yml pull pipeline
docker compose -f docker-compose.prod.yml --profile batch run --rm pipeline

docker logout ghcr.io || true

# Install/refresh the daily schedule.
sudo cp /tmp/bridge-pipeline.cron /etc/cron.d/bridge-pipeline
sudo chown root:root /etc/cron.d/bridge-pipeline
sudo chmod 644 /etc/cron.d/bridge-pipeline

echo "[deploy] done at $(date -u)"
