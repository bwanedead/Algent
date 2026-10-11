#!/usr/bin/env bash
# Deploy-on-push: fast-forward the server's checkout to origin and reinstall dependencies only when
# requirements.txt changed. Run by the ohmega-update timer every few minutes; safe to run by hand.
set -euo pipefail
cd "$HOME/Algent"
BRANCH="${ALGENT_BRANCH:-organic-dev}"
before="$(git rev-parse HEAD)"
git fetch -q origin "$BRANCH"
# Never force anything: if the server holds unpushed commits or edits that block a fast-forward, say so
# loudly (journal + the shared ops log every session reads) and leave the tree alone for a human/agent to resolve.
if ! git merge -q --ff-only "origin/$BRANCH" 2>/tmp/ohmega-update.err; then
    ahead="$(git rev-list --count "origin/$BRANCH..HEAD")"
    msg="deploy-on-push BLOCKED: $ahead unpushed local commit(s), dirty: $(git status --porcelain | wc -l) file(s). $(head -c 200 /tmp/ohmega-update.err | tr '
' ' ')"
    echo "$msg" >&2
    if ! tail -n 5 "$HOME/ops-log.md" 2>/dev/null | grep -q "deploy-on-push BLOCKED"; then
        printf '
## %s · update-timer
- %s Commit+push (or stash) on the server, then it resumes.
' "$(date -u +%FT%H:%MZ)" "$msg" >> "$HOME/ops-log.md"
    fi
    exit 1
fi
after="$(git rev-parse HEAD)"
[ "$before" = "$after" ] && exit 0
echo "updated $before -> $after"
if ! git diff --quiet "$before" "$after" -- backend/requirements.txt; then
    backend/.venv/bin/python -m pip install -q -r backend/requirements.txt
    echo "requirements reinstalled"
fi
