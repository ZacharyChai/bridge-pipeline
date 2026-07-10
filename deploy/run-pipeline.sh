#!/usr/bin/env bash
# Runs the pipeline once and pings Uptime Kuma's push monitor with the result.
# Called by cron (daily) and once directly by remote-deploy.sh after each
# deploy. UPTIME_KUMA_PUSH_URL is optional: if unset (e.g. before the Kuma
# monitor has been created by hand), the ping is skipped and only the pipeline
# result matters.
set -uo pipefail

APP_DIR=/opt/bridge
cd "$APP_DIR"

# shellcheck disable=SC1091
[ -f "$APP_DIR/.env" ] && set -a && source "$APP_DIR/.env" && set +a

START=$(date +%s)
docker compose -f docker-compose.prod.yml --profile batch run --rm pipeline
STATUS=$?
DURATION=$(( $(date +%s) - START ))

if [ -n "${UPTIME_KUMA_PUSH_URL:-}" ]; then
  if [ "$STATUS" -eq 0 ]; then
    curl -fsS --retry 2 --max-time 10 \
      "${UPTIME_KUMA_PUSH_URL}?status=up&msg=OK&ping=${DURATION}" >/dev/null || true
  else
    curl -fsS --retry 2 --max-time 10 \
      "${UPTIME_KUMA_PUSH_URL}?status=down&msg=pipeline+exited+${STATUS}&ping=${DURATION}" >/dev/null || true
  fi
fi

exit "$STATUS"
