#!/usr/bin/env bash
# Deploy-on-push: fast-forward the server's checkout to origin and reinstall dependencies only when
# requirements.txt changed. Run by the ohmega-update timer every few minutes; safe to run by hand.
set -euo pipefail
cd "$HOME/Algent"
BRANCH="${ALGENT_BRANCH:-organic-dev}"
before="$(git rev-parse HEAD)"
git fetch -q origin "$BRANCH"
git merge -q --ff-only "origin/$BRANCH"
after="$(git rev-parse HEAD)"
[ "$before" = "$after" ] && exit 0
echo "updated $before -> $after"
if ! git diff --quiet "$before" "$after" -- backend/requirements.txt; then
    backend/.venv/bin/python -m pip install -q -r backend/requirements.txt
    echo "requirements reinstalled"
fi
