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
#    today: general_discovery (the trending-news scout) · news_brief (stale) ·
#    hello_workflow (toy). To test discovery, use general_discovery.

# start it (background); note the run_id. --goal "..." targets a discovery run.
python -m algent_backend.cli.runs start general_discovery

# wait for it: watch in a loop until it ends
python -m algent_backend.cli.runs watch --run-id <id> --timeout 120
#   loop_done -> the run ended; read timeline.md + artifacts, report the recap
#   timeout   -> still running; just watch again (a run takes as long as it takes)
#   error     -> inspect status + child logs
#   hitl      -> (future) answer it, then keep watching; discovery has none today

# stop ONLY if the run clearly warrants it (visibly stuck/looping, or told to abort)
python -m algent_backend.cli.runs stop --run-id <id>
```

For a quick manual first run you can also use `--foreground` and just `Ctrl+C`.

---

## 4. Where to look

`backend/runs_data/<run_id>/`:

- **`audit/human/timeline.md`** — the human view, re-rendered live; read this first while watching.
- `audit/events.jsonl` — the machine trace (the owned local trace).
- `artifacts/discovery_result.json` — the agent's output (the candidate list).
- `result.json`, `state.json`, `done.json` — outcome + current snapshot + terminal marker.
- `child_stdout.log` / `child_stderr.log` — raw child output for a background run; **the full Python traceback for a failed run lives in `child_stderr.log`**.

Only the most recent runs are kept on disk (rolling retention); the cross-run
ledger (`runs_data/runs_index.jsonl`) keeps the full history.

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
