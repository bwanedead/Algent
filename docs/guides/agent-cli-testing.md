# Agent CLI Testing Guide

The CLI mechanics reference for running and controlling an Algent agent — the
how-to behind the [run operator entry point](./run-operator-entrypoint.md).
Every command prints exactly one JSON document, so humans, scripts, and other
agents drive runs the same way.

Run commands from `backend/` using the project venv (e.g.
`./.venv/Scripts/python.exe ...` on Windows).

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
| `start <agent_id>` | Launch a run. Background by default; `--foreground` runs inline. `--goal "..."` targets a discovery run. Returns `{run_id}`. |
| `status --run-id <id>` | Current snapshot (status, pid, liveness, done marker). |
| `watch --run-id <id> [--timeout N]` | **Blocks** until the next event, returns one of `loop_done` / `timeout` / `error`, then exits. Loop it. |
| `stop --run-id <id> [--reason "..."]` | **Kill switch.** Hard-terminates a bad / spinning / runaway run and marks it `stopped`. |
| `list` | All runs from the ledger (status, duration, tokens). |
| `show --run-id <id>` | Full detail for one run. |

---

## 3. The run loop

Your role is **start → wait in `watch` → report when it ends** (and answer any
HITL prompt if one ever appears). You are not policing the run turn-by-turn, and
there is no run-time cap — `--timeout` is only a re-evaluation window. `stop` is
the exception, not the routine.

```
# see what agents exist (pick an agent_id)
python -m algent_backend.cli.runs agents
#    discovery_synthesis = THE discovery agent to test: reads the t0 hit list and
#    produces the t1 research-vector portfolio. (Also: general_discovery (older
#    tool-survey) · news_brief (stale) · hello_workflow (toy).)

# discovery_synthesis AUTO-PRODUCES its t0 on start (free GDELT, narrated in the
# timeline) — you do NOT run any ingest step first. Starting it is the whole job:
python -m algent_backend.cli.runs start discovery_synthesis --max-turns 20
#   t0 is reused if a pool <20 min old exists, else freshly built — all in-run.
#   t0 SOURCE CHANNELS are toggleable via ALGENT_T0_CHANNELS (default
#   gkg,beats,markets). X (Grok CLI) is OFF by default — slow (~2-3 min) + spends
#   sub quota — opt in only when wanted:
#     ALGENT_T0_CHANNELS=gkg,markets,x python -m algent_backend.cli.runs start discovery_synthesis
#   Build/inspect a t0 pool directly (per-channel testing, no agent run):
#     python -m algent_backend.cli ingest t0 --channels markets --force
#   (Optional per-pillar enrichment: pre-run `ingest sweep --kind pillar`, but the
#    DOC API throttles, so skip unless needed — GKG-only t0 is the default.)
#
# RUN A STAGE IN ISOLATION (no upstream, no spend): a run's --input IS the graph's
# initial state, so feed a saved artifact/fixture to skip producing it. Fixtures live
# in backend/fixtures/ (see its README):
#     # synthesis on a saved t0 pool — no GDELT fetch:
#     python -m algent_backend.cli.runs start discovery_synthesis \
#         --input-file fixtures/t0_pool_sample.json --input-key pool
#   --input-key mounts the file under that state key (pool / portfolio / vector / ...);
#   omit it to use the file as the whole input dict. Bank any run's artifacts/*.json
#   as a new fixture to iterate on a downstream stage without re-running the pipeline.

# BEFORE entering watch, surface the live timeline link so a human can click it in
# their IDE (it re-renders as the run progresses):
#   backend/runs_data/discovery_synthesis/<NNNN>__<run_id>/audit/timeline.md

# wait for it: watch in a loop until it ends. Each window reports estimated_usd.
python -m algent_backend.cli.runs watch --run-id <id> --timeout 120
#   loop_done -> ended; read timeline.md + research_portfolio.json; report recap + estimated_usd
#   timeout   -> still running; watch again (note estimated_usd; cost_limit_reached => it auto-stopped)
#   error     -> inspect status + child logs

# stop if it clearly warrants it (spinning, climbing cost, or told to abort)
python -m algent_backend.cli.runs stop --run-id <id>
```

For a quick manual first run you can also use `--foreground` and just `Ctrl+C`.

---

## 4. Where to look

`backend/runs_data/<agent>/<NNNN>__<run_id>/` — run dirs are grouped per agent
and counter-prefixed, so the **highest number is the most recent**:

- **`audit/timeline.md`** — the human view, re-rendered live; **give this path
  to the human as a clickable link right after `start`, before you watch.**
- `audit/events.jsonl` — the machine trace (the owned local trace).
- `audit/error.log` — **the full Python traceback for a failed run** (written on failure).
- `artifacts/research_portfolio.json` — `discovery_synthesis` output (the t1 vectors).
  (`discovery_result.json` for the older `general_discovery`.)
- `result.json`, `state.json`, `done.json` — outcome + current snapshot + terminal marker.
- `child_stdout.log` / `child_stderr.log` — raw child output for a background run.

Only the most recent runs per agent are kept on disk (rolling retention); the
cross-run ledger (`runs_data/runs_index.jsonl`) keeps the full history.

---

## 5. What to look for when reviewing a run (dev-side)

These are the signals a developer reviews after a run to decide what to tune —
not a checklist the operating agent must produce. The operating agent just
relays the factual outcome (section 7); quality judgment lives here.

- Did it actually **call the tools** (GDELT, then `news_feeds` → `rss_feed`) rather than invent feed URLs?
- Is the shortlist **selective and grounded** — a few real trending topics with sources, significance set honestly — not filler?
- A `discovery.no_structured_output` event means the model **failed to format** the result (not that it found nothing) — a tuning signal, not a real empty.
- **Spinning**: the same tool call repeated with no new info. The turn budget caps it; `stop` it early if needed.
- **Token cost** shows in `list` / the ledger.

---

## 5b. Cost safeguards & the emergency stop (read before any live agent run)

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

## 6. Known early caveats

- Confirm the exact `gpt-5.4-mini` model-id string on the first run; adjust in `agents/discovery/general/spec.py` if needed.
- Streaming × structured output can interact; if results come back empty with a `no_structured_output` event, that's the place to look.
- The `news_feeds` catalog is hand-curated — verify/extend entries with `probe_tool rss_feed <url>`.
- `stop` is a hard kill (no graceful pause/resume yet); a single-shot run has no safe mid-loop checkpoint.

---

## 7. What the operating agent reports when a run ends

Just the factual outcome: the agent and input, the terminal status, a short
recap of what it produced (from `timeline.md` / the result), and any error or
anomaly the run surfaced (e.g. a `no_structured_output` event). No quality
judgment or tuning recommendation — that's the dev-side review in section 5.
