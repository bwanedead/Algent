# Agent CLI Guide

**Canonical CLI reference** for running and controlling Algent agents — humans,
scripts, and other agents. The [run operator entry point](./run-operator-entrypoint.md)
is the short hub; **this file is the full command/flag source of truth.**

Every `runs` command prints exactly one JSON document.

Run from `backend/` with the project venv (e.g. `./.venv/Scripts/python.exe ...`
on Windows).

---

## 1. Prerequisites (dev setup — not the operating agent's concern)

These are configured on the dev side before a run; an operating agent does not
manage them. If they're missing, a run surfaces an error to relay, not something
to pre-check.

- **`backend/.env`** with the model key:
  ```
  OPENAI_API_KEY=sk-...
  LANGSMITH_TRACING=true        # optional, recommended for deep traces
  LANGSMITH_API_KEY=ls-...      # optional
  ```
- The discovery tools (`gdelt_events`, `rss_feed`, `news_feeds`) need **no key**.
- Sanity-check a tool in isolation any time:
  `python -m algent_backend.cli.probe_tool gdelt_events "ukraine"`

---

## 2. The control surface

`python -m algent_backend.cli.runs <command>`:

| Command | What it does |
|---|---|
| `agents` | List the agents you can start (id, description, runtime, tools, model). Run this first to see the catalog. |
| `start <agent_id>` | Launch a run. Background by default; `--foreground` runs inline. Returns `{run_id}` + path locators. See **§3** for flags. |
| `status --run-id <id>` | Current snapshot (status, pid, liveness, done marker). |
| `watch --run-id <id> [--timeout N]` | **Blocks** until the next event, returns one of `loop_done` / `timeout` / `error`, then exits. Loop it. |
| `stop --run-id <id> [--reason "..."]` | **Kill switch.** Hard-terminates a bad / spinning / runaway run and marks it `stopped`. |
| `list` | All runs from the ledger (status, duration, tokens). |
| `show --run-id <id>` | Full detail for one run. |

Related (not under `runs`, same package style):

| Command | What it does |
|---|---|
| `python -m algent_backend.cli ingest t0 ...` | Build/inspect a t0 pool without an agent run. |
| `python -m algent_backend.cli.probe_tool <tool> ...` | Probe one tool in isolation. |

---

## 3. `start` flags (full set)

```
python -m algent_backend.cli.runs start <agent_id>
    [--input '{...}'] | [--topic "..."] | [--goal "..."]
    [--input-file PATH] [--input-key KEY]
    [--from-run REF]
    [--fixture]
    [--runtime langgraph] [--max-turns N] [--foreground]
```

| Flag | Purpose |
|---|---|
| `--input` | JSON object merged into the graph initial state. |
| `--topic` / `--goal` | Shortcuts for `{"topic": ...}` / `{"goal": ...}`. |
| `--input-file` | Load a JSON artifact/fixture as state (or under `--input-key`). |
| `--input-key` | Mount the file under one state key (`pool`, `portfolio`, `vector`, …). |
| `--from-run` | **Post-t0 reuse:** load a prior run’s t1 portfolio (see **§5**). |
| `--fixture` | Use the agent’s registered test fixture (isolated stage test). |
| `--max-turns` | Cap model-loop iterations (spin leash). |
| `--foreground` | Run in this process (Ctrl+C stops); default is detached background. |

A run’s `--input` **is** the graph’s initial state. That is how isolation and
portfolio reuse work: supply upstream artifacts instead of re-producing them.

---

## 4. The run loop (default full discovery / full rail)

Your role is **start → wait in `watch` → report when it ends** (and answer any
HITL prompt if one ever appears). You are not policing the run turn-by-turn, and
there is no run-time cap — `--timeout` is only a re-evaluation window. `stop` is
the exception, not the routine.

```
# catalog
python -m algent_backend.cli.runs agents

# discovery only (t0 hit list → t1 research portfolio)
python -m algent_backend.cli.runs start discovery_synthesis --max-turns 20
#   t0 is reused if a pool <20 min old exists, else freshly built — all in-run.
#   ALGENT_T0_CHANNELS default: gkg,beats,markets,x. When X is on, pool is rebalanced
#   (GKG≤24, markets≤12 by default) so X novelty is not drowned. X legs:
#     News (hydrated) + novelty probes + spectrum from: + wires + AI pulse.
#   Default X ≤~36 posts (~$0.18). Tune: ALGENT_X_*, ALGENT_T0_GKG_CAP, ALGENT_T0_MARKETS_CAP.
#   Discovery-only tests (no full rail):
#     python -m algent_backend.cli ingest t0 --force
#     python -m algent_backend.cli ingest t0 --channels x --force
#     python -m algent_backend.cli ingest x --via api
#   Turn X off: ALGENT_T0_CHANNELS=gkg,beats,markets

# full newsroom rail (t0 → synthesis → routing → profile → gauntlet → editorial → publish)
python -m algent_backend.cli.runs start newsroom_rail

# BEFORE watch: surface the live timeline link
#   backend/runs_data/<agent>/<NNNN>__<run_id>/audit/timeline.md

python -m algent_backend.cli.runs watch --run-id <id> --timeout 120
#   loop_done | timeout | error  — see §8 for cost fields on these events

python -m algent_backend.cli.runs stop --run-id <id>   # only if warranted
```

For a quick manual first run: `--foreground` and Ctrl+C.

### Stage isolation (fixture / input-file)

```
# agent-declared fixture (preferred when testing one stage offline)
python -m algent_backend.cli.runs start discovery_synthesis --fixture

# explicit artifact mount
python -m algent_backend.cli.runs start discovery_synthesis \
    --input-file fixtures/t0_pool_sample.json --input-key pool
# keys: pool (synthesis), portfolio (router), vector (profile), profile (editorial), …
```

Fixtures live under `backend/fixtures/`. Bank any run’s `artifacts/*.json` for
downstream isolation.

---

## 5. Post-t0 portfolio reuse (`--from-run`)

**Why:** a full rail re-pays discovery (t0 + synthesis) even when you only want
another article from vectors **already** sourced in a recent t1 portfolio. That
is redundant and expensive in short timeframes.

**What it does:** start `newsroom_rail` with a prior run’s
`artifacts/research_portfolio.json` (and `t0_pool.json` if present for
channel provenance). The rail **skips backfeed + t0 + synthesis**, then continues
**routing → profile → gauntlet → editorial → publish** as usual.

```
# after a completed newsroom_rail (e.g. counter 0013)
python -m algent_backend.cli.runs start newsroom_rail --from-run 0013
python -m algent_backend.cli.runs start newsroom_rail --from-run <run_uuid>
python -m algent_backend.cli.runs start newsroom_rail --from-run newsroom_rail/0013
python -m algent_backend.cli.runs start newsroom_rail --from-run path/to/run_dir
```

`--from-run REF` accepts:

| Form | Example |
|---|---|
| Run UUID | `4de0ba5a-074c-…` |
| Counter | `0013` or `13` (prefers the agent you are starting) |
| `agent/counter` | `newsroom_rail/0013` |
| Path to run dir | `backend/runs_data/newsroom_rail/0013__…` |

Requires `artifacts/research_portfolio.json` with a non-empty `vectors` list
(any completed synthesis or rail that wrote a portfolio). Report fields on the
new run: `portfolio_source: "reused"`, `source_run_id`.

Low-level equivalent (same rail skip path):

```
python -m algent_backend.cli.runs start newsroom_rail \
    --input-file path/to/research_portfolio.json --input-key portfolio
```

### Cooldown still applies (fresh and post-t0 are the same rule)

`--from-run` is **not** a bypass of variety control and **not** “always promote
portfolio rank #2.”

Promotion always reads a **cooldown ring of recently published headlines**
(site content: newest first, capped — currently **15 articles within ~10 days**;
see `publishing/history.py`). Soft doctrine + **mechanical demotion** keep any
story-family already in that ring from occupying #1 until it falls off the ring.

- Applies to a **fresh** full rail and to a **post-t0** reuse run identically.
- Goal: stop the newsroom latching onto the same attractive beat (e.g. Hormuz /
  Gulf oil) every launch. Without cooldown, variety collapses.
- A vector that is still “hot” in the ring stays demoted below free families.
  If the only free vectors are weak or empty, routing may promote nothing useful —
  that is correct behavior, not a bug in `--from-run`.
- Post-t0 reuse only saves **discovery cost**; it does **not** let you re-run a
  cooled family “because it was rank #2 in the old portfolio.”

When you reuse a portfolio right after publishing its #1, that #1 (and any other
cooled families already on the site) should stay demoted; a **non-cooled**
on-deck vector may promote. If Hormuz/oil (or any other family) is still in the
ring, it stays blocked just as on a fresh run.

---

## 6. Where to look

`backend/runs_data/<agent>/<NNNN>__<run_id>/` — run dirs are grouped per agent
and counter-prefixed, so the **highest number is the most recent**:

- **`audit/timeline.md`** — the human view, re-rendered live; **give this path
  to the human as a clickable link right after `start`, before you watch.**
- `audit/events.jsonl` — the machine trace (the owned local trace).
- `audit/error.log` — **the full Python traceback for a failed run** (written on failure).
- `artifacts/research_portfolio.json` — t1 vectors (`discovery_synthesis` / rail).
- `artifacts/ranking.json` / `selected_vector.json` — promotion outcome.
- `artifacts/newsroom_rail_report.json` — full-rail summary (`portfolio_source`, costs, publish).
- `result.json`, `state.json`, `done.json` — outcome + current snapshot + terminal marker.
- `child_stdout.log` / `child_stderr.log` — raw child output for a background run.

Only the most recent runs per agent are kept on disk (rolling retention); the
cross-run ledger (`runs_data/runs_index.jsonl`) keeps the full history.

---

## 7. What to look for when reviewing a run (dev-side)

These are the signals a developer reviews after a run to decide what to tune —
not a checklist the operating agent must produce. The operating agent just
relays the factual outcome (§10); quality judgment lives here.

- Did it actually **call the tools** (GDELT, then `news_feeds` → `rss_feed`) rather than invent feed URLs?
- Is the shortlist **selective and grounded** — a few real trending topics with sources, significance set honestly — not filler?
- A `discovery.no_structured_output` event means the model **failed to format** the result (not that it found nothing) — a tuning signal, not a real empty.
- **Spinning**: the same tool call repeated with no new info. The turn budget caps it; `stop` it early if needed.
- **Token cost** shows in `list` / the ledger.
- **Cooldown / variety:** did promotion avoid story-families already in the recent-headline ring? A live failure mode is over-attracting to one beat (e.g. Hormuz) on every launch — check `ranking.json` and cooldown demote events.
- **Post-t0 reuse:** if `portfolio_source` is `reused`, discovery should have been skipped; cooldown still should have applied.

---

## 8. Cost safeguards & the emergency stop (read before any live agent run)

Agent runs spend real money (model tokens + paid search). Four hard rails bound a
run so it can't run away, plus the kill switch:

1. **Emergency stop (kill switch):** `python -m algent_backend.cli.runs stop --run-id <id>`
   hard-terminates the process tree immediately. Always-available abort.
2. **Turn limit (spin leash):** `start ... --max-turns N` caps model-loop iterations
   (maps to the rail's recursion limit), so a model can't loop forever.
3. **Paid-call budget:** the `web_search` facade allows at most a fixed number of
   *paid* calls per run (Firecrawl/X); past that they're refused.
4. **USD cost cap (auto-stop):** the run accumulates an *estimated* spend (model
   tokens + paid calls) and **auto-halts** the moment it crosses the cap
   (`discovery_synthesis` default **$1.00**). A `cost.limit_reached` event is
   emitted and the loop stops itself — no need to catch it.

Paid search is **off by default** and per-call deliberate: the agent only touches
Firecrawl/X by explicitly asking, and only on channels its `search_channels` grant
permits. Free channels (keyword/semantic search, local read) cost nothing.

**Watching for cost:** `watch` itself surfaces cost — every `loop_done` and
`timeout` event carries `estimated_usd` (live spend so far) and
`cost_limit_reached: true` if the cap tripped. So a watching agent sees spend
climb each window and is alerted the moment cost becomes an issue (the cap also
auto-stops the run). The numbers come from each provider's published pricing
(sourced in `foundation/cost.py`, ~mid-2026), but they remain a **guardrail
estimate, not a billing figure** (free tiers, plan tiers, and token accounting
vary) — reconcile real spend in each provider's console.

If anything looks wrong mid-run — repeated identical paid calls, climbing cost,
visible spinning — `stop` it. That's the routine when a run misbehaves.

Post-t0 `--from-run` is a **cost** control (skip discovery), not a cooldown
bypass. Use it when you want another article soon after a full rail without
re-paying t0/synthesis.

---

## 9. Known early caveats

- Confirm the exact `gpt-5.4-mini` model-id string on the first run; adjust in `agents/discovery/general/spec.py` if needed.
- Streaming × structured output can interact; if results come back empty with a `no_structured_output` event, that's the place to look.
- The `news_feeds` catalog is hand-curated — verify/extend entries with `probe_tool rss_feed <url>`.
- `stop` is a hard kill (no graceful pause/resume yet); a single-shot run has no safe mid-loop checkpoint.
- Cooldown ring size/days are code defaults in `publishing/history.py` (not CLI flags).

---

## 10. What the operating agent reports when a run ends

Just the factual outcome: the agent and input (including `--from-run` if used),
the terminal status, a short recap of what it produced (from `timeline.md` /
the result / rail report), and any error or anomaly the run surfaced (e.g. a
`no_structured_output` event). No quality judgment or tuning recommendation —
that's the dev-side review in §7.
