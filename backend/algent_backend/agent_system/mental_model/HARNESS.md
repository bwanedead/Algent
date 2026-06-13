# Harness (Run Control Plane)

The harness is the universal layer every agent runs on: run lifecycle,
observability, artifacts, and the CLI control plane. It is Algent-owned and
rail-free.

## What It Is For

One run = one agent execution = one directory under `backend/runs_data/<run_id>/`
holding state, the event stream, the human timeline, the result, and artifacts —
plus one cross-run ledger index for "what ran, when, at what cost".

```text
RunService.run(request)
  -> RunRecorder.start()        state.json, ledger row, run.started event
  -> adapter streams the graph  node.completed / model.usage events
  -> agent writes artifacts     artifact.written events, refs collected
  -> RunRecorder.finish()       result.json, ledger row, done.json (last)
```

## What It Owns

- `runs/control_plane/` — layout, state, events log, ledger, timeline, recorder
- `runs/events.py` — the neutral RunEvent contract (open `type` string; new
  event kinds appear organically, consumers tolerate unknowns)
- `artifacts/` — ArtifactRef + run-scoped ArtifactWriter
- `cli/runs/` — start / exec / status / watch / list / show (one JSON document
  per command; equal surface for humans and agents)

## What It Must Not Own

- Agent semantics: the harness records facts; it never interprets them. The
  timeline renderer is constitutionally forbidden from authoring judgments.
- Rail specifics: LangGraph/LangSmith touches live in `runtime/langgraph.py`
  only. The control plane would serve a native rail unchanged.
- Tool or prompt behavior — those belong to `tools/` and the agents.

## Relation to LangSmith

Two trace layers joined by run id: events.jsonl/timeline/ledger are the owned
record (kept forever, vendor-independent); LangSmith holds the deep payload
tree (run-name = `<agent_id>:<run_id>`). Losing LangSmith loses depth, not
history.

## Deferred (deliberately)

HITL prompts/answers, mid-run message injection, pause/stop/resume via
LangGraph checkpoints — the watch event shape and run-dir layout already leave
room for them.
