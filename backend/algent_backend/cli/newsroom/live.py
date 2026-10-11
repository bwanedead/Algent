"""
``newsroom live`` — listen to free live data feeds (outages, quakes, aircraft, fires, ships).

    newsroom live run [--feed ioda ...] [--no-publish]   one timer run of the feeds (default: all timer feeds)
    newsroom live ais [--seconds N]                      the AIS ship counter service (needs ALGENT_AISSTREAM_KEY)
    newsroom live status                                 per feed: key situation, last success, error
    newsroom live schedule                               "<feed> <minutes>" lines the installer turns into timers
    newsroom live publish                                push the current events and stats to the site database

Free; no model. See ``live/`` and docs/guides/worker-server.md (Live feeds).
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("live", help="free live feeds: outages, quakes, military aircraft, fires, ship counts")
    verbs = p.add_subparsers(dest="live_cmd", required=True)
    r = verbs.add_parser("run", help="one run of the timer feeds")
    r.add_argument("--feed", action="append", help="feed name (repeatable); default all timer feeds")
    r.add_argument("--no-publish", action="store_true", help="skip the site database upload")
    r.set_defaults(handler=run_run)
    a = verbs.add_parser("ais", help="run the AIS chokepoint counter (a service; Ctrl-C to stop)")
    a.add_argument("--seconds", type=float, help="stop after this long (for a trial run)")
    a.set_defaults(handler=run_ais)
    verbs.add_parser("status", help="feeds, keys and last success").set_defaults(handler=run_status)
    verbs.add_parser("schedule", help="feed cadences in minutes").set_defaults(handler=run_schedule)
    verbs.add_parser("publish", help="push current events + stats to the site database").set_defaults(handler=run_publish)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def run_run(args: Any) -> int:
    from algent_backend.live import runner

    return _emit(runner.run(args.feed, publish=not args.no_publish))


def run_ais(args: Any) -> int:
    from algent_backend.live.feeds import ais

    return ais.run_service(args.seconds)


def run_status(_args: Any) -> int:
    from algent_backend.live import runner

    return _emit(runner.doctor_rows())


def run_schedule(_args: Any) -> int:
    from algent_backend.live import flags

    for feed, minutes in flags.CADENCE_MINUTES.items():
        print(feed, minutes)
    return 0


def run_publish(_args: Any) -> int:
    from algent_backend.live import publish, store

    feeds = {p.stem: store.read_events(p.stem) for p in sorted((store.root() / "events").glob("*.json"))}
    return _emit({"live": publish.publish(feeds), "world": publish.publish_world(force=True)})
