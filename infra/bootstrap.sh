#!/usr/bin/env bash
# Startup script — runs as root on first boot (GCP metadata_startup_script).
# Hardens the box and installs Docker. Written to be idempotent so re-runs on
# reboot are safe. Logs to /var/log/bootstrap.log.
set -euxo pipefail
exec > >(tee -a /var/log/bootstrap.log) 2>&1

# Read the intended login user from instance metadata (set by Terraform),
# falling back to "deploy". Avoids templating the whole bash script.
DEPLOY_USER="$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/deploy-user || echo deploy)"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

echo "[bootstrap] starting at $(date -u)"

# --- Swap: e2-micro has only 1GB RAM and no swap by default -----------------
# A 2GB swapfile gives headroom for Postgres + Docker + the pipeline running
# concurrently, at the cost of some disk (20GB boot disk has plenty of room).
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# --- Non-root user with passwordless sudo -----------------------------------
# GCP creates the user from the ssh-keys metadata; make sure it can sudo.
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  usermod -aG sudo "$DEPLOY_USER"
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-"$DEPLOY_USER"
  chmod 440 /etc/sudoers.d/90-"$DEPLOY_USER"
fi

# --- SSH: key-only, no root login -------------------------------------------
install -d -m 0755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-hardening.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
EOF
systemctl reload ssh || systemctl reload sshd || true

# --- Firewall: deny inbound except SSH --------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable

# --- Docker engine ----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
usermod -aG docker "$DEPLOY_USER" || true

echo "[bootstrap] done at $(date -u)"
