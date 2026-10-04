"""
``newsroom statements`` — the ledger of who said what, from primary transcripts.

    newsroom statements collect [--no-extract] [--feed ID ...] [--days 14] [--max-new 15]
    newsroom statements show [--about X] [--speaker Y] [--affiliation Z] [--topic T] [--days 14] [--limit 40]

``collect`` polls the feed catalog (free), then extracts every not-yet-extracted transcript with one
cheap model call each; ``--no-extract`` stops after collecting (no model, no spend). Each command
prints one JSON document. Store: ``statements_store/`` (override: ``ALGENT_STATEMENTS_STORE``).
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("statements", help="the statements ledger: who said what, from primary transcripts")
    verbs = p.add_subparsers(dest="statements_verb", required=True)
    c = verbs.add_parser("collect", help="poll the feeds, collect transcripts, extract statements")
    c.add_argument("--no-extract", action="store_true", help="collect transcripts only (free; no model call)")
    c.add_argument("--feed", action="append", default=[], help="only this feed id (repeatable)")
    c.add_argument("--days", type=int, default=14, help="ignore feed items older than this")
    c.add_argument("--max-new", type=int, default=15, help="most new items to collect per feed per run")
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


def _collect(args: Any) -> int:
    from algent_backend.agent_system.agents.statements import collect, extract, store

    feeds = args.feed or None
    report: dict[str, Any] = {"store": str(store.store_dir()),
                              "feeds": collect.collect(feeds=feeds, days=args.days, max_new=args.max_new)}
    report["transcripts_collected"] = sum(f["collected"] for f in report["feeds"])
    if not args.no_extract:
        from algent_backend.agent_system.foundation.models import house_spec

        report["extraction"] = extract.extract_pending(
            _ctx(), None, house_spec(reasoning_effort="low", temperature=0.1, max_tokens=8192), feeds=feeds)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["transcripts_collected"] or any(f["entries"] for f in report["feeds"]) else 1


def _show(args: Any) -> int:
    from algent_backend.agent_system.agents.statements import store

    rows = store.query(about=args.about, speaker=args.speaker, affiliation=args.affiliation, topic=args.topic,
                       days=args.days, limit=args.limit)
    print(json.dumps({"count": len(rows), "statements": [r.model_dump() for r in rows]}, indent=2, ensure_ascii=False))
    return 0
