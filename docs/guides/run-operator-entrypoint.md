# Operating Algent Runs — Start Here

Single entry point for any agent (or person) tasked with **starting, watching,
and controlling Algent agent runs**. Read this, then follow the links — from here
you can self-discover everything needed to drive a run.

## What you're operating

Algent runs agents through a CLI where **every command prints one JSON document**.
You: discover what agents exist → start one → watch it to completion (or stop it)
→ read its output. You don't need the internals to operate a run; pointers to
them are below if you want them.

## The 60-second flow

From `backend/`, using the project venv:

```
# what can I start?
python -m algent_backend.cli.runs agents

# start one (e.g. the discovery agent); --goal "..." to target it
python -m algent_backend.cli.runs start general_discovery        # → {run_id}

# watch until it finishes (loop; each call returns one event)
python -m algent_backend.cli.runs watch --run-id <id> --timeout 180

# stop it if it goes rogue / spins / looks wrong
python -m algent_backend.cli.runs stop --run-id <id>
```

Read the live human log at `backend/runs_data/<run_id>/timeline.md`; the agent's
output lands in `backend/runs_data/<run_id>/artifacts/`.

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
