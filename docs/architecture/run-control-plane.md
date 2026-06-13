# Run Control Plane

How Algent runs are started, observed, and driven from outside the running
process. Adapted in part from Plattera's CLI constitution.

---

## 1. The Constitutional Rule

The CLI is a control plane **over** the harness. It is not the harness.

- The CLI may launch runs, watch status, surface files, and (later) submit
  human answers.
- The CLI must never define what run states mean, when a run resumes, or any
  agent semantics. If a behavior exists only in the CLI, it is a control-plane
  convenience, not harness law.

Every command prints exactly one JSON document, so humans, scripts, and other
agents — including headless CLI harnesses (Claude Code, Codex, Gemini) — are
equal callers. This surface is the mechanism by which agents communicate with
and steer each other's runs.

## 2. Run Directory Contract

Every run owns one directory:

```text
backend/runs_data/<run_id>/
  request.json       what was asked (written by start, read by exec)
  state.json         live snapshot: status, pid, timing (atomic writes)
  events.jsonl       append-only neutral RunEvent stream — the owned trace
  timeline.md        human projection of events (live, facts only)
  result.json        RunResult + artifact refs at terminal
  done.json          terminal marker (existence = run is over)
  artifacts/         durable outputs written by the agent
  child_stdout.log / child_stderr.log   background child process output
```

Plus the cross-run ledger index: `backend/runs_data/runs_index.jsonl`
(append-only; one row at start, one at finish; readers fold by run id).

Root override: `ALGENT_RUNS_DIR` (tests isolate under a temp dir).

## 3. Commands

```powershell
# from backend/ with the venv python
python -m algent_backend.cli.runs start <agent_id> --topic "..." [--input '{...}']
                                        [--max-turns N] [--foreground]
python -m algent_backend.cli.runs status --run-id <id>
python -m algent_backend.cli.runs watch  --run-id <id> --timeout 600
python -m algent_backend.cli.runs list   [--limit N]
python -m algent_backend.cli.runs show   --run-id <id>
```

`start` allocates the run id, writes `request.json` + a `queued` state, then
spawns a detached child (`exec`) — or runs inline with `--foreground`. Watchers
can attach the moment `start` returns.

`watch` is a blocking single-event poll. It returns exactly one JSON event,
then exits:

- `{"event": "loop_done", ...}` — terminal state reached; inspect the run
- `{"event": "timeout", ...}` — nothing happened in this window; watch again
- `{"event": "error", ...}` — unknown run, or the run's process died

The monitor loop (for an operator or a watching agent):

```text
watch -> timeout? watch again
      -> loop_done? read result.json / timeline.md
      -> error? inspect state.json and child_stderr.log
```

HITL events (`{"event": "hitl", ...}`) join this surface in a later slice,
along with `answer`, `message`, `pause`, `stop`, and `resume` — the event shape
is a tagged union so consumers must tolerate new kinds.

## 4. Observability Weave

- The LangGraph adapter attaches the Algent run id to every rail invocation as
  LangSmith run-name/metadata/tags, so a LangSmith trace maps 1:1 to a run
  directory. Enable with `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` (see
  `backend/.env.example`).
- Token usage rolls up into `model.usage` events and the ledger row.
- `timeline.md` re-renders after every event: the live human view of a run.

## 5. Budgets

`--max-turns` maps to the rail's recursion limit — the mechanical leash on
agent loops. Budgets are harness law; agents do not get to exceed them.
