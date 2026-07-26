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

You're told which agent to run. Your job is simple: **confirm it in the registry,
start it, wait for it in `watch`, and report when it ends** — plus answer any
HITL prompt if one ever appears (discovery has none today). You are *not* policing
the run turn-by-turn. A run takes as long as it takes; there is no time cap (any
turn/budget limits will be specified separately).

You don't set up keys or judge in advance whether a run will work — that's the
dev side. If something is wrong, the run surfaces an error (a `watch` `error`
event, a failed terminal status) that you simply relay.

From `backend/`, using the project venv. Every command prints one JSON document:

```
# what can I start?
python -m algent_backend.cli.runs agents

# start one (discovery_synthesis is the discovery agent) → {run_id}
# It self-sources its t0 pool (no manual ingest first). The t0 source channels
# are toggleable via ALGENT_T0_CHANNELS (default: gkg,beats,markets). The X
# channel (Grok CLI) is OFF by default — it's slow (~2-3 min) and spends your
# subscription quota — so opt in only when you want it:
#   ALGENT_T0_CHANNELS=gkg,markets,x python -m algent_backend.cli.runs start discovery_synthesis
python -m algent_backend.cli.runs start discovery_synthesis --max-turns 20

# To build/inspect a t0 pool directly (per-channel testing), without an agent run:
#   python -m algent_backend.cli ingest t0 --channels markets --force

# full newsroom rail (discovery → article → publish)
#   python -m algent_backend.cli.runs start newsroom_rail

# TEST A STAGE IN ISOLATION ON ITS STORED INPUT (no upstream, no spend): each agent
# declares its own test fixture, so one uniform flag works for any of them — you do
# NOT need to know which file/key. When asked to "test <agent> with stored input":
#   python -m algent_backend.cli.runs start <agent_id> --fixture
# e.g. `... start discovery_synthesis --fixture` runs synthesis on a saved t0 pool
# (no GDELT). If an agent has no fixture, the command says so. (Under the hood this is
# --input-file/--input-key seeding the graph's initial state; see backend/fixtures/.)

# POST-t0 REUSE (skip discovery cost; cooldown still applies — same as a fresh run):
# After a full rail, try another article from that run's t1 portfolio without re-running t0:
#   python -m algent_backend.cli.runs start newsroom_rail --from-run 0013
# Cooldown is a ring of recent published headlines: story-families already on the site
# cannot promote until they fall off the ring. --from-run does NOT bypass that (and does
# not mean "always take rank #2"). Full detail: agent-cli-testing.md §5.

# THEN, before watching, give the human the run's live timeline as a clickable link:
#   backend/runs_data/<agent>/<NNNN>__<run_id>/audit/timeline.md

# wait for it: watch in a loop. --timeout is a re-evaluation window, NOT a run cap.
python -m algent_backend.cli.runs watch --run-id <id> --timeout 120
#   loop_done -> the run ended; read the recap + artifacts and report it
#   timeout   -> still running; watch again (each window reports estimated_usd)
#   error     -> inspect status + child logs
```

Before you enter the watch loop, surface the `timeline.md` path above as a
clickable link so the human can follow the run live in their IDE. When `watch`
returns `loop_done`, break out and report the recap — that report
is your natural "it's done" signal. Run dirs are grouped per agent and
counter-prefixed (newest = highest number): read the human log at
`backend/runs_data/<agent>/<NNNN>__<run_id>/audit/timeline.md` and the
output in that run dir's `artifacts/`. (A failed run's full traceback is in its
`audit/error.log`.)

`stop --run-id <id>` is the **exception**, not the routine — use it only if the
run clearly warrants intervention (visibly stuck/looping, or you're told to
abort).

## Docs to be familiar with

- **CLI operation → [`agent-cli-testing.md`](./agent-cli-testing.md) (canonical).**
  Full command set, all `start` flags, post-t0 `--from-run`, cooldown rules,
  watch/stop loop, cost rails, and where every run file lives. **Prefer this
  file whenever an agent needs reliable CLI docs.**
- **How runs are recorded → [`../architecture/run-control-plane.md`](../architecture/run-control-plane.md).**
  The run-directory contract, if you need to reason about run files.
- **What the agent system is → `backend/algent_backend/agent_system/mental_model/`**
  (start with `NORTH_STAR.md`). Optional background.
- **Per-agent notes and future responsibilities** are linked here as they are written.

## What to report when a run ends

Just relay the outcome — the agent and input, the terminal status, a short recap
of what it produced (from `timeline.md` / the result), and any error or anomaly
the run surfaced. You don't analyze or recommend fixes; that's the dev side.

---

This doc is the **hub**. When new operating knowledge or new agents arrive, link
them here so an operator can always start from one place.
