#!/usr/bin/env bash
# Install (or update) the Algent backend on the worker server. Run as the `ohmega` user, from anywhere:
#
#   ssh -i ~/.ssh/ohmega_ops ohmega@HOST 'bash ~/Algent/infra/server/app_setup.sh'
#
# Idempotent: pulls the branch, (re)creates the venv only if missing, installs requirements, installs the
# headless browser, and links the secrets file. The secrets file (~/algent.env, chmod 600, copied by scp from the
# laptop and never in git) is linked as backend/.env so the code reads it exactly as it does on the laptop.
set -euo pipefail

REPO="$HOME/Algent"
BRANCH="${ALGENT_BRANCH:-organic-dev}"

[ -d "$REPO/.git" ] || git clone -q --branch "$BRANCH" git@github-algent:bwanedead/Algent.git "$REPO"
cd "$REPO"
git fetch -q origin
git checkout -q "$BRANCH"
git merge -q --ff-only "origin/$BRANCH"

cd backend
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

# Headless browser for the read ladder: the shell build only (lighter), plus the system libraries it needs.
.venv/bin/python -m playwright install --only-shell chromium >/dev/null
sudo .venv/bin/python -m playwright install-deps chromium >/dev/null

if [ -f "$HOME/algent.env" ]; then
    ln -sf "$HOME/algent.env" .env
else
    echo "WARNING: ~/algent.env missing — copy backend/.env from the laptop with scp" >&2
fi

echo "== Algent at $(git log --oneline -1)"
.venv/bin/python -c "import algent_backend, playwright, psycopg, lxml; print('imports ok')"
