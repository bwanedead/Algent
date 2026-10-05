"""
``newsroom statements`` — the ledger of who said what, from primary transcripts (and, opt-in, news reports).

    newsroom statements collect [--no-extract] [--feed ID ...] [--days 14] [--max-new 15] [--reported | --no-reported]
    newsroom statements show [--about X] [--speaker Y] [--affiliation Z] [--topic T] [--days 14] [--limit 40]

``collect`` polls the feed catalog (free), then extracts every not-yet-extracted transcript with one
cheap model call each; ``--no-extract`` stops after collecting (no model, no spend). ``--reported`` also runs
the secondary lane (``reported.py``): news reports of what the live theaters' actors and the standing offices
said, read free and extracted as ``secondary`` statements; ``--feed`` limits the primary feeds only.
Each command prints one JSON document. Store: ``statements_store/`` (override: ``ALGENT_STATEMENTS_STORE``).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    from algent_backend.agent_system.agents.statements.reported import RUN_BY_DEFAULT

    p = sub.add_parser("statements", help="the statements ledger: who said what, from primary transcripts")
    verbs = p.add_subparsers(dest="statements_verb", required=True)
    c = verbs.add_parser("collect", help="poll the feeds, collect transcripts, extract statements")
    c.add_argument("--no-extract", action="store_true", help="collect transcripts only (free; no model call)")
    c.add_argument("--feed", action="append", default=[], help="only this feed id (repeatable)")
    c.add_argument("--days", type=int, default=14, help="ignore feed items older than this")
    c.add_argument("--max-new", type=int, default=15, help="most new items to collect per feed per run")
    c.add_argument("--reported", action=argparse.BooleanOptionalAction, default=RUN_BY_DEFAULT,
                   help="also run the reported lane: news reports of what leaders said (secondary statements)")
    s = verbs.add_parser("show", help="query the ledger")
    s.add_argument("--about", default="")
    s.add_argument("--speaker", default="")
    s.add_argument("--affiliation", default="")
    s.add_argument("--topic", default="")
    s.add_argument("--days", type=int, default=14)
    s.add_argument("--limit", type=int, default=40)
    p.set_defaults(handler=run_statements)


def run_statements(args: Any) -> int:
    return {"collect": _collect, "show": _show}[args.statements_verb](args)


def _ctx() -> Any:
    from algent_backend.agent_system.foundation.models import ModelResolver
    from algent_backend.agent_system.runs.context import AgentRunContext

    return AgentRunContext(run_id="statements-collect", model_resolver=ModelResolver())


def live_theaters() -> list[str]:
    """Name and description of each geopolitical theater the intel desk is following now (new or active), read from its
    registry file; [] when there is none. Read-only — the statements package never imports the desk."""
    path = Path(os.environ.get("ALGENT_INTEL_STORE") or "intel_store") / "theaters.json"
    try:
        reg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f"{t.get('name', '')}. {t.get('description', '')}" for t in reg.values()
            if isinstance(t, dict) and t.get("state") in ("new", "active") and t.get("domain") == "geopolitics"]


def _collect(args: Any) -> int:
    from algent_backend.agent_system.agents.statements import collect, extract, reported, store

    feeds = args.feed or None
    report: dict[str, Any] = {"store": str(store.store_dir()),
                              "feeds": collect.collect(feeds=feeds, days=args.days, max_new=args.max_new)}
    report["transcripts_collected"] = sum(f["collected"] for f in report["feeds"])
    if args.reported:
        report["reported"] = reported.collect_reported(theaters=live_theaters())
        report["transcripts_collected"] += report["reported"]["collected"]
    if not args.no_extract:
        from algent_backend.agent_system.foundation.models import house_spec

        wanted = feeds if not (feeds and args.reported) else [*feeds, "reported"]
        report["extraction"] = extract.extract_pending(
            _ctx(), None, house_spec(reasoning_effort="low", temperature=0.1, max_tokens=8192), feeds=wanted)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["transcripts_collected"] or any(f["entries"] for f in report["feeds"]) else 1


def _show(args: Any) -> int:
    from algent_backend.agent_system.agents.statements import store

    rows = store.query(about=args.about, speaker=args.speaker, affiliation=args.affiliation, topic=args.topic,
                       days=args.days, limit=args.limit)
    print(json.dumps({"count": len(rows), "statements": [r.model_dump() for r in rows]}, indent=2, ensure_ascii=False))
    return 0
