"""
``newsroom intel`` — the watch desk: what is heating up, and briefs on it.

    newsroom intel heat                          # heat board from the radar's history (1 cheap call)
    newsroom intel brief                         # briefs on the 3 hottest theaters
    newsroom intel brief --theater thr_x --research   # commission fresh research first (paid, capped)

Output lands in ``runs_data/intel/<as_of>/`` as HTML + JSON. Research commissioned here goes into the
profile corpus and updates any Pulses it bears on, exactly as an article's research does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("intel", help="watch desk: heat board and intelligence briefs")
    verbs = p.add_subparsers(dest="intel_verb", required=True)
    h = verbs.add_parser("heat", help="find the active theaters and how hot they are")
    h.add_argument("--days", type=int, default=7)
    b = verbs.add_parser("brief", help="write briefs on hot theaters")
    b.add_argument("--theater", default="", help="a theater id (default: the hottest ones)")
    b.add_argument("--top", type=int, default=3)
    b.add_argument("--research", action="store_true", help="commission fresh research first (paid)")
    p.set_defaults(handler=run_intel)


def _ctx(run_id: str) -> Any:
    from algent_backend.agent_system.foundation.models import ModelResolver
    from algent_backend.agent_system.runs.context import AgentRunContext
    from algent_backend.agent_system.tools.registry import default_tool_registry
    from algent_backend.agent_system.tools.resolved import ResolvedTools

    # Briefs commission research, so the sourcing tools must be there (lazy: built only if used).
    return AgentRunContext(run_id=run_id, model_resolver=ModelResolver(),
                           tools=ResolvedTools(default_tool_registry().list()))


def _out(as_of: str) -> Path:
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    path = Path(runs_data_root()) / "intel" / as_of
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_intel(args: Any) -> int:
    return {"heat": _heat, "brief": _brief}[args.intel_verb](args)


def _heat(args: Any) -> int:
    from algent_backend.agent_system.agents.intel import heat, render
    from algent_backend.agent_system.foundation.models import house_spec
    from algent_backend.publishing.radar_page import read_editions

    board = heat.run(_ctx("intel-heat"), None, read_editions(), days=args.days,
                     model_spec=house_spec(reasoning_effort="low", temperature=0.1, max_tokens=16384))
    out = _out(board["as_of"])
    (out / "board.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "board.html").write_text(render.render_board(board), encoding="utf-8")
    print(json.dumps({"board": str(out / "board.html"), "theaters": [
        {"id": h["theater_id"], "name": h["name"], "recent": h["recent"], "trend": h["trend"], "heat": h["heat"]}
        for h in board["heat"]]}, indent=2, ensure_ascii=False))
    return 0


def _brief(args: Any) -> int:
    from algent_backend.agent_system.agents.intel import brief as br
    from algent_backend.agent_system.agents.intel import render
    from algent_backend.agent_system.agents.intel.contracts import Theater
    from algent_backend.agent_system.agents.intel.heat import store_dir
    from algent_backend.agent_system.agents.pulse.update import update_quietly
    from algent_backend.agent_system.foundation import cost
    from algent_backend.agent_system.foundation.models import house_spec

    boards = sorted((store_dir() / "boards").glob("*.json"))
    if not boards:
        print(json.dumps({"error": "no heat board yet — run `newsroom intel heat` first"}))
        return 2
    board = json.loads(boards[-1].read_text(encoding="utf-8"))
    theaters = {t["id"]: Theater.model_validate(t) for t in board["theaters"]}
    heat = {h["theater_id"]: h for h in board["heat"]}
    chosen = [args.theater] if args.theater else [h["theater_id"] for h in board["heat"][: args.top]]
    ctx, out, report = _ctx("intel-brief"), _out(board["as_of"]), []
    for tid in chosen:
        theater = theaters.get(tid)
        if theater is None:
            report.append({"theater": tid, "error": "not on the latest board"})
            continue
        profiles, spent = [], 0.0
        if args.research:
            # The research agent caps itself at $1; this scope makes the spend visible per theater.
            with cost.article_scoped(1.0):
                prof = br.commission_research(ctx, None, theater)
                spent = cost.article_spent_usd()
            if prof:
                profiles.append(prof)
                update_quietly(prof, run_id=f"intel_{tid}")   # the brief's research moves the Pulses
        brief = br.write_brief(ctx, None, theater, heat.get(tid, {}), profiles=profiles, pulse_lines=[],
                               model_spec=house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384))
        if brief is None:
            report.append({"theater": tid, "error": "analyst returned nothing"})
            continue
        name = br.safe_name(theater.name)
        (out / f"brief_{name}.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
        (out / f"brief_{name}.html").write_text(
            render.render_brief(brief, theater_name=theater.name, heat=heat.get(tid, {}), as_of=board["as_of"]),
            encoding="utf-8")
        report.append({"theater": tid, "brief": str(out / f"brief_{name}.html"),
                       "researched": bool(profiles), "research_usd": round(spent, 4)})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0
