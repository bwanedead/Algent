"""
``newsroom intel`` — the watch desk: what is heating up, and briefs on it.

    newsroom intel heat                          # heat board from the radar's history (1 cheap call)
    newsroom intel brief                         # briefs on the 3 hottest theaters
    newsroom intel brief --theater thr_x --research   # commission fresh research first (paid, capped)
    newsroom intel daily [--domain geopolitics] [--top 5] [--research]   # the daily rundown: heat -> sections -> publish -> backup
    newsroom intel publish                       # put the desk snapshot (pulses, theaters, briefs) on the site
    newsroom intel cycle [--top 2] [--research] [--domain geopolitics,politics]  # heat -> settle forecasts -> briefs -> publish -> backup, unattended
    newsroom intel import-briefs                 # one-off: runs_data briefs -> durable intel store

Output lands in ``runs_data/intel/<as_of>/`` as HTML + JSON; briefs are
also persisted durably to ``intel_store/briefs/``. Research commissioned here goes into the
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
    b.add_argument("--focus", default="", help="a question the desk wants answered; leads the research and brief")
    d = verbs.add_parser("daily", help="the daily report: per-theater rundown of what happened, with Pulses")
    d.add_argument("--domain", default="geopolitics")
    d.add_argument("--top", type=int, default=5)
    d.add_argument("--research", action="store_true", help="research each theater first (paid, capped)")
    d.add_argument("--days", type=int, default=7)
    verbs.add_parser("import-briefs", help="one-off: copy runs_data briefs into the durable intel store")
    verbs.add_parser("publish", help="build the desk snapshot and put it on the site")
    c = verbs.add_parser("cycle", help="heat, brief the top theaters, publish, back up")
    c.add_argument("--top", type=int, default=2)
    c.add_argument("--research", action="store_true", help="commission fresh research first (paid)")
    c.add_argument("--days", type=int, default=7)
    c.add_argument("--domain", action="append", default=[],
                   help="only brief theaters in these domains (repeatable or comma list, e.g. "
                        "geopolitics,politics); the heat board still covers everything")
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
    return {"heat": _heat, "brief": _brief, "import-briefs": _import_briefs,
            "publish": _publish, "cycle": _cycle, "daily": _daily}[args.intel_verb](args)


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
    from algent_backend.agent_system.agents.intel import desk

    board = desk.latest_board()
    if board is None:
        print(json.dumps({"error": "no heat board yet — run `newsroom intel heat` first"}))
        return 2
    chosen = [args.theater] if args.theater else desk.pick_theaters(board, args.top)
    print(json.dumps(_produce_briefs(board, chosen, research=args.research, focus=args.focus),
                     indent=2, ensure_ascii=False))
    return 0


def _produce_briefs(board: dict, chosen: list[str], *, research: bool, focus: str = "") -> list[dict]:
    from algent_backend.agent_system.agents.intel import desk
    from algent_backend.agent_system.agents.intel.contracts import Theater
    from algent_backend.agent_system.foundation.models import house_spec

    theaters = {t["id"]: Theater.model_validate(t) for t in board["theaters"]}
    heat = {h["theater_id"]: h for h in board["heat"]}
    ctx, out, report = _ctx("intel-brief"), _out(board["as_of"]), []
    spec = house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384)
    for tid in chosen:
        if tid not in theaters:
            report.append({"theater": tid, "error": "not on the latest board"})
            continue
        report.append(desk.produce(ctx, theaters[tid], heat.get(tid, {}), as_of=board["as_of"], out=out,
                                   research=research, focus=focus, model_spec=spec))
    return report


def _import_briefs(_args: Any) -> int:
    from algent_backend.agent_system.agents.intel import desk
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    print(json.dumps(desk.import_briefs(Path(runs_data_root()) / "intel"), indent=2))
    return 0


def _publish(_args: Any) -> int:
    from algent_backend.publishing.intel_page import publish_intel

    print(json.dumps(publish_intel(), indent=2, ensure_ascii=False))
    return 0


def _cycle(args: Any) -> int:
    """Heat, briefs on the top theaters, publish the snapshot, back up the stores."""
    from algent_backend.agent_system.agents.intel import desk
    from algent_backend.data_backup import sync
    from algent_backend.publishing.intel_page import publish_intel

    if _heat(args) != 0:
        return 1
    board = desk.latest_board() or {"heat": [], "theaters": [], "as_of": ""}
    from algent_backend.agent_system.foundation.models import house_spec

    # Settle overdue forecasts first, so this cycle's analysts see how the desk's calls came out.
    settled = desk.settle_overdue(_ctx("intel-forecasts"), board, as_of=board.get("as_of", ""),
                                  model_spec=house_spec(reasoning_effort="low", temperature=0.1, max_tokens=8192))
    domains = [d for item in args.domain for d in item.split(",") if d.strip()]
    report: dict[str, Any] = {
        "forecasts_settled": settled,
        "briefs": _produce_briefs(board, desk.pick_theaters(board, args.top, domains), research=args.research)}
    report["publish"] = publish_intel()
    report["backup"] = sync.backup(note="intel cycle")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _daily(args: Any) -> int:
    """Fresh heat board, the daily report for the domain, publish, back up. Prints a JSON report."""
    from algent_backend.agent_system.agents.intel import daily, desk
    from algent_backend.agent_system.foundation.models import house_spec
    from algent_backend.data_backup import sync
    from algent_backend.publishing.intel_page import publish_intel

    if _heat(args) != 0:
        return 1
    board = desk.latest_board()
    if board is None:
        print(json.dumps({"error": "no heat board"}))
        return 2
    result = daily.produce_daily(_ctx("intel-daily"), domain=args.domain, top=args.top, research=args.research,
                                 model_spec=house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384),
                                 as_of=board["as_of"], board=board, out=_out(board["as_of"]))
    report = {"date": board["as_of"], "domain": args.domain, "path": result["path"], "html": result.get("html"),
              "headline": result["report"]["summary"]["headline"], "theaters": result["theaters"],
              "research_usd": result["research_usd"], "publish": publish_intel(),
              "backup": sync.backup(note="intel daily")}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0
