"""
``start`` — launch a run (background child by default, ``--foreground`` inline).

The parent allocates the run id, writes ``request.json`` and a ``queued``
state snapshot, then either spawns a detached ``exec`` child or executes
inline. Watchers can attach to the run id the moment this command returns.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from algent_backend.agent_system.runs.control_plane.fsio import write_json_file
from algent_backend.agent_system.runs.control_plane.layout import (
    RunPaths,
    allocate_run_root,
    find_run_root,
    prune_runs,
    resolve_run_ref,
)
from algent_backend.agent_system.runs.control_plane.state import RunState, write_state
from algent_backend.agent_system.runs.models import RunRequest

from algent_backend.agent_system.agents.editorial.analytics_harness import HARNESSES

from ._shared import parse_input_arg, print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("start", help="start a run")
    parser.add_argument("agent_id")
    parser.add_argument("--input", help='run input as a JSON object, e.g. \'{"topic": "..."}\'')
    parser.add_argument("--topic", help="shortcut for --input '{\"topic\": ...}'")
    parser.add_argument("--goal", help="shortcut for --input '{\"goal\": ...}' (discovery agents)")
    parser.add_argument(
        "--input-file",
        help="seed the run's initial state from a JSON file (a saved artifact/fixture), "
        "so a stage runs in isolation on supplied input — pair with --input-key",
    )
    parser.add_argument(
        "--input-key",
        help="mount --input-file under this state key, e.g. 'pool' (synthesis) or "
        "'portfolio' (router); omit to use the file as the whole input dict",
    )
    parser.add_argument(
        "--from-run",
        help="reuse a prior run's t1 research_portfolio.json (and t0_pool.json if present) "
        "as this run's starting state — skip t0+synthesis on newsroom_rail. Routing still "
        "applies the same published-headline cooldown as a fresh run (cooled families stay "
        "blocked). Accepts run UUID, NNNN counter, agent/NNNN, or a path to a run directory",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="run the agent on ITS OWN registered test fixture (isolated test input) — "
        "no need to know which file/key; the agent declares it",
    )
    parser.add_argument("--runtime", default="langgraph")
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument(
        "--analytics-harness", dest="analytics_harness", choices=HARNESSES, default=None,
        help="which coding CLI draws the figures (default: codex). Use grok when its quota "
             "is worth spending; codex otherwise. Sets ALGENT_ANALYTICS_HARNESS for the run.",
    )
    parser.add_argument(
        "--analytics-model", dest="analytics_model", default=None,
        help="model for the analytics harness (codex default: gpt-5.6-luna; gpt-5.6-terra is "
             "the heavier sibling). Sets ALGENT_CODEX_MODEL for the run.",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="execute in this process instead of spawning a background child",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    run_id = str(uuid4())

    # Harness choice is per-run and travels by environment, so it reaches the analytics
    # worker whether the graph runs here or in a spawned child — the worker resolves it
    # at the moment it shells out, not at import.
    for flag, env in (
        (getattr(args, "analytics_harness", None), "ALGENT_ANALYTICS_HARNESS"),
        (getattr(args, "analytics_model", None), "ALGENT_CODEX_MODEL"),
    ):
        if flag:
            os.environ[env] = flag

    input_file, input_key = args.input_file, args.input_key
    if args.fixture:  # the agent declares its own isolated-test input
        resolved = _resolve_fixture(args.agent_id)
        if resolved is None:
            print_json({"error": f"agent '{args.agent_id}' has no registered test fixture"})
            return 1
        input_file, input_key = resolved

    try:
        run_input = parse_input_arg(args.input, args.topic, args.goal, input_file, input_key)
        if args.from_run:
            run_input = _merge_from_run(run_input, args.from_run, prefer_agent=args.agent_id)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print_json({"error": str(exc)})
        return 1

    request = RunRequest(
        agent_id=args.agent_id,
        input=run_input,
        runtime=args.runtime,
        run_id=run_id,
        max_turns=args.max_turns,
    )

    paths = RunPaths(allocate_run_root(request.agent_id, run_id))
    write_json_file(paths.request_file, request.model_dump())
    now = datetime.now(UTC).isoformat()
    write_state(
        paths,
        RunState(
            run_id=run_id,
            agent_id=request.agent_id,
            runtime=request.runtime,
            status="queued",
            created_at=now,
            updated_at=now,
            input=request.input,
            max_turns=request.max_turns,
        ),
    )
    # Rolling retention (per agent), after allocating this run so it is kept and
    # an older one drops. The cross-run ledger still records full history.
    prune_runs(keep=5)

    # Paths in the output so the run is immediately findable — the operator can
    # hand the timeline link to a human before watching (see the testing guide).
    locators = {
        "run_dir": str(paths.root),
        "timeline": str(paths.timeline_file),
        "events": str(paths.events_file),
    }

    if args.foreground:
        from . import exec_run

        exit_code = exec_run.execute(run_id)
        print_json({"run_id": run_id, "mode": "foreground", "exit_code": exit_code, **locators})
        return exit_code

    _spawn_detached(run_id)
    print_json({"run_id": run_id, "mode": "background", **locators})
    return 0


def _resolve_fixture(agent_id: str) -> tuple[str, str | None] | None:
    """An agent's registered test fixture as (input_file, input_key), or None if it
    has none / the agent is unknown (the run itself reports an unknown agent cleanly).
    """
    # Lazy import: the registry pulls agent modules, kept off the light start path.
    from algent_backend.agent_system.agents.registry import default_agent_registry

    try:
        spec = default_agent_registry().get(agent_id)
    except ValueError:
        return None
    fixture = spec.test_fixture
    return (fixture.input_file, fixture.input_key) if fixture is not None else None


def _merge_from_run(payload: dict, ref: str, *, prefer_agent: str) -> dict:
    """Load a prior run's portfolio (+ optional pool) into the new run's initial state.

    The rail skips t0+synthesis when ``portfolio`` is present; routing still applies cooldown
    so a just-published #1 demotes and an on-deck vector can promote without re-discovery.
    """
    import json

    run_dir = resolve_run_ref(ref, prefer_agent=prefer_agent)
    if run_dir is None:
        raise FileNotFoundError(
            f"--from-run could not resolve '{ref}' "
            f"(try a run UUID, NNNN counter, agent/NNNN, or path to a run dir)"
        )
    artifacts = run_dir / "artifacts"
    portfolio_path = artifacts / "research_portfolio.json"
    if not portfolio_path.is_file():
        raise FileNotFoundError(
            f"--from-run {run_dir.name}: no artifacts/research_portfolio.json "
            f"(need a completed synthesis/rail run with a t1 portfolio)"
        )
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    if not isinstance(portfolio, dict) or not portfolio.get("vectors"):
        raise ValueError(f"--from-run {run_dir.name}: research_portfolio.json has no vectors")

    # Best-effort source run id from the directory name (NNNN__uuid) or state.json.
    source_run_id = ""
    name = run_dir.name
    if "__" in name:
        source_run_id = name.split("__", 1)[1]
    state_file = run_dir / "state.json"
    if state_file.is_file():
        try:
            source_run_id = str(json.loads(state_file.read_text(encoding="utf-8")).get("run_id")
                                or source_run_id)
        except (OSError, ValueError):
            pass

    merged = {**payload, "portfolio": portfolio, "source_run_id": source_run_id}
    pool_path = artifacts / "t0_pool.json"
    if pool_path.is_file() and "pool" not in merged:
        try:
            pool = json.loads(pool_path.read_text(encoding="utf-8"))
            if isinstance(pool, dict):
                merged["pool"] = pool
        except (OSError, ValueError):
            pass
    return merged


def _spawn_detached(run_id: str) -> None:
    paths = RunPaths(find_run_root(run_id))
    command = [sys.executable, "-m", "algent_backend.cli.runs", "exec", "--run-id", run_id]

    stdout = paths.child_stdout_file.open("ab")
    stderr = paths.child_stderr_file.open("ab")
    kwargs: dict = {"stdout": stdout, "stderr": stderr, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)
    stdout.close()
    stderr.close()
