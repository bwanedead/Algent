"""
``newsroom views`` - the server-built views the site and the agent API read (docs/architecture/views.md).

    newsroom views build [--only a,b] [--dry-run] [--json]   build every view (or the named families), store them in views_store/, send the changed ones to R2
    newsroom views stats [--json]                            per family: count, bytes, the largest view; the R2 guard's month so far
    newsroom views show <key>                                print one stored view (country/FR, situation/<id>, entity/org/<id>, home, hud, ...)

Free; no model. Families: graph, country, situation (+ the situations index), event, entity, home, hud, daily-hub, search-index.
"""

from __future__ import annotations

from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("views", help="build, publish and inspect the server-built views (country, situation, entity, home, hud, search index ...)")
    verbs = p.add_subparsers(dest="views_cmd", required=True)
    b = verbs.add_parser("build", help="build views, store them locally and publish what changed")
    b.add_argument("--only", default="", help="comma-separated families (graph,country,situation,event,entity,home,hud,daily-hub,search-index)")
    b.add_argument("--dry-run", action="store_true", help="build and report what would be sent (Class A operations, gzipped bytes); store and send nothing")
    b.add_argument("--json", action="store_true")
    b.set_defaults(handler=run_build)
    s = verbs.add_parser("stats", help="what the local store holds, and the R2 guard")
    s.add_argument("--json", action="store_true")
    s.set_defaults(handler=run_stats)
    w = verbs.add_parser("show", help="print one stored view")
    w.add_argument("key")
    w.set_defaults(handler=run_show)


def run_build(args: Any) -> int:
    from algent_backend.views import cli

    return cli.run_build(only=args.only, dry_run=args.dry_run, as_json=args.json)


def run_stats(args: Any) -> int:
    from algent_backend.views import cli

    return cli.run_stats(as_json=args.json)


def run_show(args: Any) -> int:
    from algent_backend.views import cli

    return cli.run_show(args.key)
