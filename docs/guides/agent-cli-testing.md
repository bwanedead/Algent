# Agent CLI Testing Guide

How to run, watch, and control an Algent agent from the command line for live
testing. Every command prints exactly one JSON document, so humans, scripts, and
other agents drive runs the same way.

Run commands from `backend/` using the project venv (e.g.
`./.venv/Scripts/python.exe ...` on Windows).

---

## 1. Prerequisites

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
| `start <agent_id>` | Launch a run. Background by default; `--foreground` runs inline. `--goal "..."` targets a discovery run. Returns `{run_id}`. |
| `status --run-id <id>` | Current snapshot (status, pid, liveness, done marker). |
| `watch --run-id <id> [--timeout N]` | **Blocks** until the next event, returns one of `loop_done` / `timeout` / `error`, then exits. Loop it. |
| `stop --run-id <id> [--reason "..."]` | **Kill switch.** Hard-terminates a bad / spinning / runaway run and marks it `stopped`. |
| `list` | All runs from the ledger (status, duration, tokens). |
| `show --run-id <id>` | Full detail for one run. |

---

## 3. The testing loop

```
# 1. start the discovery agent (background); note the run_id it returns
python -m algent_backend.cli.runs start general_discovery
#    or target it:  ... start general_discovery --goal "Russian economics"

# 2. watch until it finishes (loop; each call returns one event)
python -m algent_backend.cli.runs watch --run-id <id> --timeout 120

# 3. if it goes rogue / spins / looks wrong — stop it
python -m algent_backend.cli.runs stop --run-id <id> --reason "spinning on rss"
```

For a quick first run you can also use `--foreground` and just `Ctrl+C` to abort.

---

## 4. Where to look

`backend/runs_data/<run_id>/`:

- **`timeline.md`** — the human view, re-rendered live; read this first while watching.
- `events.jsonl` — the machine trace (what we own regardless of LangSmith).
- `artifacts/discovery_result.json` — the agent's output (the candidate list).
- `result.json`, `state.json`, `done.json` — outcome + current snapshot + terminal marker.
- `child_stdout.log` / `child_stderr.log` — raw child output for a background run.
- LangSmith (if enabled) — the deep per-call trace; `state.json` notes the project.

---

## 5. What to watch for (discovery)

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

## 7. What to report after a run

run id and input; terminal status; which tools were called and in what order;
candidate quality (selective? grounded? significance honest?); whether a
`no_structured_output` event appeared; token cost; and the one thing you'd tune
next (prompt, feed list, or model).
