# Runner handover — Ohmega on the server OR the laptop, never both

The server is a resource, not a dependency. Either machine can run paid work and publish; exactly one is the
**runner** at a time. The claim is advisory (a handover record, not a lock) and lives in `runner.json` at the
root of the private `algent-data` archive — the repo the nightly backup already pushes to — so it needs no
migration and works with `DATABASE_URL` unset. Design and failure modes: `data_backup/runner.py`.

```
python -m algent_backend.cli newsroom runner status
python -m algent_backend.cli newsroom runner claim [--force] [--note "why"]
python -m algent_backend.cli newsroom runner release [--force]
python -m algent_backend.cli newsroom doctor            # is THIS machine ready? spends nothing
python -m algent_backend.cli newsroom search-usage --days 7
```

**What the claim guards.** `publishing.publish_run` (every article publish), `newsroom run` when it would spend
(synthesis / rail stages), and `newsroom intel daily|cycle|publish` refuse on a machine that is not the runner,
with a message naming the holder. Free scheduled jobs (library crawl, instruments, statements, backup) are not
guarded. **The guard fails open**: if the archive is unreachable, or nobody holds the claim, work is allowed — a
GitHub blip must never lock you out of your own pipeline. `ALGENT_RUNNER_GUARD=0` disables it for a one-off;
`ALGENT_RUNNER_NAME` overrides the hostname used as the machine's identity.

## What lives where

| Thing | Where | Moves how |
|---|---|---|
| Code | GitHub `organic-dev` | `git pull` (server auto-pulls every 5 min) |
| Corpus stores (profiles, pulse, intel, instruments, statements, actors) | each machine's `backend/*_store/` | `algent-data` archive: `sync.backup()` / `sync.restore()` |
| Published articles, dailies, record | Supabase | already shared |
| Secrets (`.env`) | per machine: laptop `backend/.env` (+ keyring), server `~/algent.env` | copy by hand (`scp`); names in `docs/credentials.md` |
| Chart-harness logins (`codex`, `grok`) | per machine | log in once on each |
| Runner claim | `runner.json` in the archive | `newsroom runner ...` |
| `runs_data/` (ledgers, quota, run logs) | per machine, gitignored | does NOT move — paid-quota counters and search/read ledgers are per machine |

Gotcha: `runs_data/paid_quota.json` is per machine, so the monthly caps are counted per machine. Moving runner
mid-month doubles the effective cap unless you copy that file across; copy it if the free tiers are tight.

## Server -> laptop (also: server budget lost)

1. **On the server** (if it still answers): finish or stop the active run, then
   `newsroom runner release`, then take a final backup:
   `python -c "from algent_backend.data_backup import sync; print(sync.backup(note='handover'))"`.
   Server gone? Skip this; the nightly backup (06:15 UTC) is the last copy, so you may lose up to a day of
   stores. Take over with `--force` in step 4.
2. **On the laptop**: `git pull` on `organic-dev`; `cd backend; .venv\Scripts\Activate.ps1`.
3. Restore stores: `python -c "from algent_backend.data_backup import sync; print(sync.restore())"`.
   It only fills in files that are missing; it never overwrites newer local files. For a laptop that has been
   running stale stores, move the old `*_store` folders aside first.
4. `newsroom runner claim` (add `--force` if the server could not release).
5. `backend/.env` must hold `DATABASE_URL` (Supabase session-pooler URI) and the keys in `docs/credentials.md`.
   Without `DATABASE_URL` publishing falls back to the `.site-live` git path, which is not the live path.
6. `newsroom doctor` — fix every `fail`; read the `warn`s.
7. Chart harness logins are already on the laptop (`codex login status` should say logged in; grok is checked
   for presence only).
8. Stop the server's timers if it is still alive: `sudo systemctl stop 'ohmega-*.timer'`
   (the free jobs would otherwise keep writing a store nobody reads). Destroying the droplet makes this moot.

### Search without the server

SearXNG is the first rung of the search chain and lives on the server. Locally there are three states, all
working:

- **Nothing running**: the chain falls through at the cost of one refused local connection to DDG, then Bing,
  then (news) Google News, then the capped paid engines (Tavily/Brave/Exa; `search/quota.py`). Expect more
  failures and a higher paid share than on the server; `newsroom search-usage` measures exactly that.
- **SSH tunnel to the server's SearXNG** while it lives: `ssh -N -L 8080:127.0.0.1:8080 -i ~/.ssh/ohmega_ops ohmega@146.190.243.152`.
- **Local SearXNG** (Docker Desktop, same compose file as the server): `powershell -File infra/local/searxng-up.ps1`
  (stop with `-Down`). It binds 127.0.0.1:8080, the default `ALGENT_SEARXNG_URL`, so nothing else changes.
  Close any tunnel first (same port). Residential IPs are usually blocked less than datacentre IPs, so it may
  do better than the server did.

## Laptop -> server

1. **Laptop**: finish the run, `newsroom runner release`, then
   `python -c "from algent_backend.data_backup import sync; print(sync.backup(note='handover'))"`.
2. **Server** (`ssh -i ~/.ssh/ohmega_ops ohmega@146.190.243.152`): `cd ~/Algent/backend`; the updater has already
   pulled code. Restore stores: `.venv/bin/python -c "from algent_backend.data_backup import sync; print(sync.restore())"`
   (fills in only; if the server has older copies of files the laptop updated, move the server's `*_store`
   folders aside first so the restore brings the laptop's versions).
3. `.venv/bin/python -m algent_backend.cli newsroom runner claim` (the laptop's release makes this clean).
4. `.venv/bin/python -m algent_backend.cli newsroom doctor`; SearXNG should answer at 127.0.0.1:8080 and
   `harness:codex` / `harness:grok` need interactive logins on the server if never done.
5. Close any local SearXNG container on the laptop (`-Down`) and re-enable timers if they were stopped:
   `sudo systemctl start 'ohmega-*.timer'`.

## Failure modes

| Situation | What happens | Fix |
|---|---|---|
| Server died holding the claim | laptop refuses paid work with "server is the runner" | `newsroom runner claim --force` on the laptop |
| Both machines ran anyway (guard off / archive down) | two corpora diverge | pick the winner, restore it onto the other, `claim` |
| Archive unreachable | claim/release refuse (never claim blind); the guard allows work | fix network, retry; `ALGENT_RUNNER_GUARD=0` is not needed |
| Two machines claim at once | second push is rejected, rebased once; if it still fails the claim says "push failed" | re-run `status`, then `claim` / `--force` |
| `doctor` says `database: fail` | message never includes the URL | check `DATABASE_URL` in `.env`, pooler URI, network |

## Measuring what the new search stack buys (`search-usage`)

Every web search appends one line to `runs_data/search_ledger.jsonl` (kind, answering provider or `none`,
providers tried, cached flag, result count, ms, query *length* only). `newsroom search-usage --days N` reports
answers by provider, free vs paid share, failure rate, empty-result rate, share that fell through past the
first provider, average latency per provider, and paid use against the monthly caps. Read it after the first
run on each machine: a high `paid_share_pct` or `failure_rate_pct` is the new stack limiting or failing where
the old one did not. The ledger is per machine; compare server and laptop by running the report on each.
