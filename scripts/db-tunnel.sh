#!/usr/bin/env bash
# Local-dev DB tunnel.
#
# Why this exists: on this Intel Mac running macOS 14, Colima's automatic
# port-forward to the host is broken (needs macOS 15.5+ for its vz backend, and
# the qemu backend's lima SSH forward hangs too). But SSH *into* the Colima VM
# works fine, so we forward host:15432 -> VM -> the Postgres container's 5432
# over a dedicated, keep-alive SSH connection.
#
# M2's docker-compose runs the app in a container on the same Docker network as
# Postgres, so it won't need this at all. This is purely for host-side dev
# (`make run`, pytest) on this machine.
#
# Usage:
#   scripts/db-tunnel.sh start   # start (idempotent)
#   scripts/db-tunnel.sh stop
#   scripts/db-tunnel.sh status
set -euo pipefail

HOST_PORT="${HOST_PORT:-15432}"
GUEST_PORT="${GUEST_PORT:-5432}"
MATCH="${HOST_PORT}:127.0.0.1:${GUEST_PORT}"
SSH_CONFIG="${TMPDIR:-/tmp}/colima_ssh_config"

start() {
  if pgrep -f "$MATCH" >/dev/null 2>&1; then
    echo "tunnel already running on ${HOST_PORT}"
    return 0
  fi
  colima ssh-config > "$SSH_CONFIG"
  local alias
  alias=$(awk '/^Host /{print $2; exit}' "$SSH_CONFIG")
  # Dedicated connection: disable control-master reuse (that socket gets torn
  # down), keep it alive, and bail if the forward can't bind.
  nohup ssh -F "$SSH_CONFIG" \
    -o ControlMaster=no -o ControlPath=none \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -N -L "${HOST_PORT}:127.0.0.1:${GUEST_PORT}" "$alias" \
    >/dev/null 2>&1 &
  disown || true
  sleep 2
  status
}

stop() {
  pkill -f "$MATCH" && echo "tunnel stopped" || echo "no tunnel running"
}

status() {
  if pgrep -f "$MATCH" >/dev/null 2>&1; then
    echo "tunnel up: localhost:${HOST_PORT} -> container:${GUEST_PORT}"
  else
    echo "tunnel down"
    return 1
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
