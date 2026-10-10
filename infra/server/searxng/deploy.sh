#!/usr/bin/env bash
# Deploy (or update) SearXNG on the worker server from this repo. Run from the repo root on the laptop:
#
#   bash infra/server/searxng/deploy.sh ohmega@HOST
#
# Copies the compose file and settings to ~/searxng on the server, generates the instance secret once (kept in
# ~/searxng/.env on the server, never in git), pulls the images and (re)starts. Safe to re-run.
set -euo pipefail
TARGET="${1:?usage: deploy.sh ohmega@HOST}"
KEY="${OHMEGA_SSH_KEY:-$HOME/.ssh/ohmega_ops}"
HERE="$(cd "$(dirname "$0")" && pwd)"

ssh -i "$KEY" -o BatchMode=yes "$TARGET" 'mkdir -p ~/searxng'
scp -i "$KEY" -o BatchMode=yes "$HERE/docker-compose.yml" "$HERE/settings.yml" "$TARGET:searxng/"
ssh -i "$KEY" -o BatchMode=yes "$TARGET" bash -s <<'EOF'
set -euo pipefail
cd ~/searxng
sed -i 's/\r$//' docker-compose.yml settings.yml
[ -f .env ] || { echo "SEARXNG_SECRET=$(openssl rand -hex 32)" > .env; chmod 600 .env; }
docker compose pull --quiet
docker compose up -d --remove-orphans
docker compose ps --format '{{.Service}}: {{.State}}'
EOF
