# Operating Algent Runs — Start Here

Single entry point for any agent (or person) tasked with **starting, watching,
and controlling Algent agent runs**. Read this, then follow the links — from here
you can self-discover everything needed to drive a run.

## What you're operating

Algent runs agents through a CLI where **every command prints one JSON document**.
You: discover what agents exist → start one → watch it to completion (or stop it)
→ read its output. You don't need the internals to operate a run; pointers to
them are below if you want them.

## Your job, and the flow

Your job is simple: **start the run, wait for it in `watch`, and report when it
ends** — plus answer any HITL prompt if one ever appears (discovery has none
today). You are *not* policing the run turn-by-turn. A run takes as long as it
takes; there is no time cap (any turn/budget limits will be specified
separately).

From `backend/`, using the project venv. Every command prints one JSON document:

```
# what can I start?
python -m algent_backend.cli.runs agents

# start one (e.g. the discovery agent); --goal "..." to target it
python -m algent_backend.cli.runs start general_discovery        # → {run_id}

# wait for it: watch in a loop. --timeout is a re-evaluation window, NOT a run cap.
python -m algent_backend.cli.runs watch --run-id <id> --timeout 120
#   loop_done -> the run ended; read the recap + artifacts and report it
#   timeout   -> still running; just watch again
#   error     -> inspect status + child logs
#   hitl      -> (future) answer it, then keep watching
```

When `watch` returns `loop_done`, break out and report the recap — that report
is your natural "it's done" signal. Read the human log at
`backend/runs_data/<run_id>/timeline.md` and the output in
`backend/runs_data/<run_id>/artifacts/`.

`stop --run-id <id>` is the **exception**, not the routine — use it only if the
run clearly warrants intervention (visibly stuck/looping, or you're told to
abort).

## Read next

- **CLI mechanics & the testing loop → [`agent-cli-testing.md`](./agent-cli-testing.md).**
  Your main reference: the full command set, the watch/stop loop, where every run
  file lives, what to watch for, and what to report.
- **How runs are recorded → [`../architecture/run-control-plane.md`](../architecture/run-control-plane.md).**
  The run-directory contract and observability weave, if you need to reason about
  run files.
- **What the agent system is → `backend/algent_backend/agent_system/mental_model/`**
  (start with `NORTH_STAR.md`). Optional background on how the system is built.
- **Per-agent notes** — agent-specific guidance is linked here as it is written.

## Prerequisites

- `backend/.env` holds the model key (`OPENAI_API_KEY`). The discovery tools
  (GDELT, RSS) need no key.
- If a run fails immediately on the model call, the key is the first thing to check.

## What to report after a run

Run id + input; terminal status; which tools were called and in what order;
output quality; any anomalies (e.g. a `discovery.no_structured_output` event);
token cost; and the one thing you'd tune next. (Full checklist in the CLI guide.)

---

This doc is the **hub**. When new operating knowledge or new agents arrive, link
them here so an operator can always start from one place.
