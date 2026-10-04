"""
``newsroom steer`` — clarify the framing of a run that is already going.

    newsroom steer "read it as strategy: who gains leverage, how each power responds"
    newsroom steer --show        # what is queued, and what the live run has already taken
    newsroom steer --clear       # drop anything queued that has not landed yet

The live rail picks the note up at its next stage boundary and keeps it with that run, so every
later stage writes to it and a resumed run still has it. Research already finished is kept, not
redone — see ``agents/newsroom/steer.py`` for why. With nothing running, the note waits for the
next run that starts.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.agent_system.agents.newsroom import steer

from .pause import _live_holder


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "steer", help="add a framing note to the running rail (lands at the next stage)")
    p.add_argument("text", nargs="?", default="", help="the framing clarification")
    p.add_argument("--show", action="store_true", help="list queued steers")
    p.add_argument("--clear", action="store_true", help="drop queued steers that have not landed")
    p.set_defaults(handler=run_steer)


def run_steer(args: Any) -> int:
    if args.clear:
        steer.clear_pending()
        print(json.dumps({"queued": [], "note": "queued steers cleared"}, indent=2))
        return 0
    if args.show or not args.text:
        print(json.dumps({"queued": steer.pending()}, indent=2, ensure_ascii=False))
        return 0

    try:
        entry = steer.add(args.text)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    holder = _live_holder()
    print(json.dumps({
        "queued": entry,
        "running": bool(holder),
        "note": (
            "lands at the running rail's next stage boundary; that stage and every one after it "
            "writes to it, and finished research is kept"
            if holder else
            "nothing is running; it will apply to the next run that starts"
        ),
    }, indent=2, ensure_ascii=False))
    return 0
