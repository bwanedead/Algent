"""
``newsroom intel`` — the watch desk: what is heating up, and briefs on it.

    newsroom intel heat                          # heat board from the radar's history (1 cheap call)
    newsroom intel brief                         # briefs on the 3 hottest theaters
    newsroom intel brief --theater thr_x --research   # commission fresh research first (paid, capped)
    newsroom intel daily [--domain geopolitics] [--top 5] [--research] [--fresh-research]   # the daily rundown: heat -> sections -> publish -> backup
    newsroom intel publish                       # put the desk snapshot (pulses, theaters, briefs) on the site
    newsroom intel dossiers [--primers] [--domain geopolitics]   # rebuild + publish the theater dossiers; --primers writes the missing/stale (>7d) primers first
    newsroom intel cycle [--top 2] [--research] [--domain geopolitics,politics]  # heat -> settle forecasts -> briefs -> publish -> backup, unattended
    newsroom intel import-briefs                 # one-off: runs_data briefs -> durable intel store

Research is reused, never repeated: a theater's research already in the corpus for the same day (daily) or
the same brief (complete profile, built today) is fed to the writers as is; ``--fresh-research`` forces new.
`daily` and `cycle` first refresh the sensing layers (instruments fetch, statements collect + extract; best-effort,
never failing the run; the result is the report's `sensing_refresh`); `--no-refresh` skips it.
A daily that wrote no section, or a brief run that produced none, persists/publishes nothing and exits 1.

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
    b.add_argument("--fresh-research", action="store_true", help="redo research even if today's already exists")
    d = verbs.add_parser("daily", help="the daily report: per-theater rundown of what happened, with Pulses")
    d.add_argument("--domain", default="geopolitics")
    d.add_argument("--top", type=int, default=5)
    d.add_argument("--research", action="store_true", help="research each theater first (paid, capped)")
    d.add_argument("--fresh-research", action="store_true", help="redo research even if today's already exists")
    d.add_argument("--days", type=int, default=7)
    d.add_argument("--no-refresh", action="store_true", help="skip refreshing instruments and statements first")
    verbs.add_parser("import-briefs", help="one-off: copy runs_data briefs into the durable intel store")
    verbs.add_parser("publish", help="build the desk snapshot and put it on the site")
    t = verbs.add_parser("dossiers", help="rebuild the theater dossiers and publish them")
    t.add_argument("--primers", action="store_true", help="write primers that are missing or older than 7 days first")
    t.add_argument("--domain", default="", help="with --primers: only this domain's theaters (default: all)")
    c = verbs.add_parser("cycle", help="heat, brief the top theaters, publish, back up")
    c.add_argument("--top", type=int, default=2)
    c.add_argument("--research", action="store_true", help="commission fresh research first (paid)")
    c.add_argument("--fresh-research", action="store_true", help="redo research even if today's already exists")
    c.add_argument("--days", type=int, default=7)
    c.add_argument("--no-refresh", action="store_true", help="skip refreshing instruments and statements first")
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
            "publish": _publish, "cycle": _cycle, "daily": _daily,
            "dossiers": _dossiers}[args.intel_verb](args)


def _refresh_sensing(args: Any) -> dict[str, Any]:
    """Refresh the numbers and statements layers before the desk writes. Never raises; ``--no-refresh`` skips."""
    if getattr(args, "no_refresh", False):
        return {"skipped": "--no-refresh"}
    from algent_backend.agent_system.agents.intel import refresh
    from algent_backend.agent_system.foundation.models import house_spec

    try:
        return refresh.refresh(_ctx("intel-sensing"), house_spec(reasoning_effort="low", temperature=0.1, max_tokens=8192))
    except Exception as exc:  # noqa: BLE001 - e.g. the model resolver cannot be built; the day goes on
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _heat(args: Any, *, publish: bool = True) -> int:
    """Build the board. ``publish=False`` when a caller (cycle, daily) publishes once at its own end."""
    from algent_backend.agent_system.agents.intel import heat, render
    from algent_backend.agent_system.foundation.models import house_spec
    from algent_backend.publishing.intel_page import publish_intel
    from algent_backend.publishing.radar_page import read_editions

    board = heat.run(_ctx("intel-heat"), None, read_editions(), days=args.days,
                     model_spec=house_spec(reasoning_effort="low", temperature=0.1, max_tokens=16384))
    out = _out(board["as_of"])
    (out / "board.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "board.html").write_text(render.render_board(board), encoding="utf-8")
    report: dict[str, Any] = {"board": str(out / "board.html"), "theaters": [
        {"id": h["theater_id"], "name": h["name"], "recent": h["recent"], "trend": h["trend"], "heat": h["heat"]}
        for h in board["heat"]]}
    if publish:
        report["publish"] = publish_intel()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _brief(args: Any) -> int:
    from algent_backend.agent_system.agents.intel import desk

    board = desk.latest_board()
    if board is None:
        print(json.dumps({"error": "no heat board yet — run `newsroom intel heat` first"}))
        return 2
    from algent_backend.publishing.intel_page import publish_intel

    chosen = [args.theater] if args.theater else desk.pick_theaters(board, args.top)
    report = _produce_briefs(board, chosen, research=args.research, focus=args.focus,
                             fresh_research=args.fresh_research)
    if not any("slug" in r for r in report):        # nothing was written: nothing to publish
        print(json.dumps({"briefs": report, "error": "no brief was written; nothing published"}, indent=2,
                         ensure_ascii=False))
        return 1
    print(json.dumps({"briefs": report, "publish": publish_intel()}, indent=2, ensure_ascii=False))
    return 0


def _produce_briefs(board: dict, chosen: list[str], *, research: bool, focus: str = "",
                    fresh_research: bool = False) -> list[dict]:
    from algent_backend.agent_system.agents.intel import desk
    from algent_backend.agent_system.agents.intel.brief import describe_failure
    from algent_backend.agent_system.agents.intel.contracts import Theater
    from algent_backend.agent_system.foundation.models import house_spec

    theaters = {t["id"]: Theater.model_validate(t) for t in board["theaters"]}
    heat = {h["theater_id"]: h for h in board["heat"]}
    ctx, out, report = _ctx("intel-brief"), _out(board["as_of"]), []
    spec = house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384, streaming=True)
    for tid in chosen:
        if tid not in theaters:
            report.append({"theater": tid, "error": "not on the latest board"})
            continue
        try:
            report.append(desk.produce(ctx, theaters[tid], heat.get(tid, {}), as_of=board["as_of"], out=out,
                                       research=research, focus=focus, model_spec=spec,
                                       fresh_research=fresh_research))
        except Exception as exc:  # noqa: BLE001 - one theater's failure must not abort the others' briefs
            report.append({"theater": tid, "error": f"brief failed: {describe_failure(exc)}"})
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


def _prime(domain: str = "") -> list[dict]:
    """Primers for the dossier theaters (in ``domain`` when given) that have none or a stale one. Never raises:
    a primer is an extra, and the daily must not fail for it."""
    try:
        from algent_backend.agent_system.agents.intel import dossier_store, primers
        from algent_backend.agent_system.agents.intel.heat import store_dir
        from algent_backend.agent_system.foundation.models import house_spec

        intel = store_dir()
        built = dossier_store.build(intel, countries=None)           # only to list the theaters
        ids = [t["theater_id"] for t in built["index"]["theaters"] if not domain or t["domain"] == domain]
        return primers.ensure(_ctx("intel-primers"), intel, dossier_store.describe(intel, ids),
                              model_spec=house_spec(reasoning_effort="low", temperature=0.2, max_tokens=4096))
    except Exception as exc:  # noqa: BLE001
        return [{"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}]


def _dossiers(args: Any) -> int:
    """Rebuild the dossiers (optionally writing due primers first) and publish them with the desk snapshot."""
    from algent_backend.agent_system.agents.intel import dossier_store
    from algent_backend.agent_system.agents.intel.heat import store_dir
    from algent_backend.publishing.intel_page import publish_intel

    report: dict[str, Any] = {}
    if args.primers:
        report["primers"] = _prime(args.domain)
    built = dossier_store.build(store_dir(), countries=None)
    report["theaters"] = [{"id": t["theater_id"], "name": t["name"], "days": t["days_covered"],
                           "last_seen": t["last_seen"]} for t in built["index"]["theaters"]]
    report["publish"] = publish_intel()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cycle(args: Any) -> int:
    """Heat, briefs on the top theaters, publish the snapshot, back up the stores."""
    from algent_backend.agent_system.agents.intel import desk
    from algent_backend.data_backup import sync
    from algent_backend.publishing.intel_page import publish_intel

    sensing_refresh = _refresh_sensing(args)
    if _heat(args, publish=False) != 0:
        return 1
    board = desk.latest_board() or {"heat": [], "theaters": [], "as_of": ""}
    from algent_backend.agent_system.foundation.models import house_spec

    # Settle overdue forecasts first, so this cycle's analysts see how the desk's calls came out.
    settled = desk.settle_overdue(_ctx("intel-forecasts"), board, as_of=board.get("as_of", ""),
                                  model_spec=house_spec(reasoning_effort="low", temperature=0.1, max_tokens=8192))
    domains = [d for item in args.domain for d in item.split(",") if d.strip()]
    report: dict[str, Any] = {
        "sensing_refresh": sensing_refresh,
        "forecasts_settled": settled,
        "briefs": _produce_briefs(board, desk.pick_theaters(board, args.top, domains), research=args.research,
                                  fresh_research=args.fresh_research)}
    if report["briefs"] and not any("slug" in r for r in report["briefs"]):
        report["error"] = "no brief was written; nothing published"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
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

    from .pulse import promote_ready_quietly

    sensing_refresh = _refresh_sensing(args)
    if _heat(args, publish=False) != 0:
        return 1
    board = desk.latest_board()
    if board is None:
        print(json.dumps({"error": "no heat board"}))
        return 2
    result = daily.produce_daily(_ctx("intel-daily"), domain=args.domain, top=args.top, research=args.research,
                                 model_spec=house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384,
                                                       streaming=True),
                                 as_of=board["as_of"], board=board, out=_out(board["as_of"]),
                                 fresh_research=args.fresh_research)
    if result.get("error"):         # a failed run: nothing persisted, so nothing to promote, publish or back up
        print(json.dumps({"date": board["as_of"], "domain": args.domain, "error": result["error"],
                          "theaters": result["theaters"], "research_usd": result["research_usd"],
                          "sensing_refresh": sensing_refresh},
                         indent=2, ensure_ascii=False))
        return 1
    # Promote first (quietly: it does not publish) so the one publish below carries the new Pulses.
    proposals = promote_ready_quietly()
    primers_report = _prime(args.domain)        # only dossiers lacking a primer or with one over 7 days old
    report = {"date": board["as_of"], "domain": args.domain, "path": result["path"], "html": result.get("html"),
              "headline": result["report"]["summary"]["headline"], "theaters": result["theaters"],
              "research_usd": result["research_usd"], "pulse_proposals": proposals, "primers": primers_report,
              "sensing_refresh": sensing_refresh,
              "publish": publish_intel(),
              "backup": sync.backup(note="intel daily")}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0
