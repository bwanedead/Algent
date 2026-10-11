# Brief for a cloud Claude session (paste as the first message)

You're joining an ongoing project as a cloud session. Read this, then run the checks at the bottom and report back.

## What this is
- **Algent** (this repo) is the engine behind **Ohmega Monster** (www.ohmega.monster), an automated, AI-run publication.
  It has two main products:
  - **Newsroom:** a pipeline that finds stories, researches them, checks claims, and writes and publishes articles.
    Stages: t0 discovery → synthesis → menu → route → profile → gauntlet → editorial → publish.
  - **Intel desk:** a geopolitics desk. It produces a daily report per theater, with actor models (economy, energy,
    trade), on-the-record leader statements from all sides, maps, and "Pulses", which are tracked questions about
    where a situation is heading.
- **The value is the accumulated corpus** (claim/story profiles, the Pulse ledger, statements, instruments), not
  the code. The repo is public; the corpus is not. Never overwrite or delete corpus data.
- **Operator:** the human you're talking to. Style: blunt, casual, push back when you disagree. Budget is tight:
  free sources first, paid APIs last, and **no paid run (research, daily, articles) without the operator's explicit
  go-ahead.**

## Read first
- `AGENTS.md` (repo rules: branch `organic-dev` only, never `main`; never read or print `.env`/secrets; commit and
  push finished chunks).
- `docs/ethos/` (architecture, structural, modularity), `docs/guides/worker-server.md`,
  `docs/guides/runner-handover.md`, `docs/architecture/published-content.md`, `docs/credentials.md`
  (key names only).

## Infrastructure (built 2026-10-09/10)
- **Worker server:** DigitalOcean droplet, `ohmega@146.190.243.152` (Ubuntu 24.04, 2 vCPU / 4 GB). This is where
  everything runs.
  - Repo at `~/Algent`, venv at `~/Algent/backend/.venv`. Secrets at `~/algent.env`, linked as `backend/.env`.
    Don't read it.
  - SearXNG (our own metasearch) runs in Docker on 127.0.0.1:8080.
  - Free jobs on systemd timers: deploy-on-push from `organic-dev` every 5 min, library crawl 4 h,
    instruments 6 h, statements 6 h, backup 06:15 UTC. Check them with `systemctl list-timers 'ohmega-*'`.
  - The server holds the **runner claim**: it's the one machine that runs paid work and publishes.
    See `newsroom runner status`.
- **Supabase** project `ohmega` is the database (corpus, Pulse ledger, published content). Images are in Storage
  bucket `published-assets`.
- **Site:** Next.js on Vercel (`sites/ohmega-monster/`). It reads live from Supabase, so publishing is a database
  write with no redeploy (`SITE_PUBLISH_VIA = "db"` in `backend/algent_backend/agent_system/agents/newsroom/flags.py`).
  The `site-live` branch deploys production and takes only merges from `organic-dev`.
- **Search:** SearXNG first, then the free engines, then paid ones with monthly caps (`quota.py`).
  Page reads go trafilatura → Jina → Wayback → Playwright → Firecrawl (capped).

## How you reach the server
Your environment decodes an SSH key to `~/.ssh/ohmega`. Run commands like this:
```
ssh -i ~/.ssh/ohmega ohmega@146.190.243.152 'cd ~/Algent/backend && .venv/bin/python -m algent_backend.cli newsroom doctor'
```
Code changes: commit to `organic-dev` and push. The server pulls within 5 minutes. Run logs on the server are at
`~/Algent/backend/runs_data/<run_id>/audit/` (start with `human/timeline.md`), and the ad-hoc logs in `~/runlogs/`.

## Checks to run now (all free; spend nothing)
1. `ls ~/.ssh/ohmega` exists, then `ssh -i ~/.ssh/ohmega -o ConnectTimeout=15 ohmega@146.190.243.152 'echo hello from the server'`.
   If it hangs or is refused, stop and report: the network setting probably blocks port 22.
2. `newsroom doctor` over SSH (the command above). Expect 0 fails. The one warning, Brave/Anthropic keys not set,
   is known.
3. `newsroom runner status`: it should say the server holds the claim.
4. `systemctl list-timers 'ohmega-*'` and `pgrep -fa algent_backend`: what's scheduled and what's running now.
5. `tail -n 20 ~/runlogs/daily.log`: the state of the latest geopolitics daily.
6. Locally in your clone: `git log --oneline -5 origin/organic-dev`. Confirm you can see the branch, and say
   whether you could push. Don't push anything just to test.
7. `curl -s -o /dev/null -w '%{http_code}' https://www.ohmega.monster/intel`: expect 200.

Report a short pass/fail list. Don't change anything, don't start any runs, and don't print anything that looks
like a key or connection string.
