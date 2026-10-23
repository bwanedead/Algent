"""
``newsroom publish`` - republish what the site reads from the server's local stores (docs/architecture/database-budget.md, runbook).

    newsroom publish rebuild-all [--dry-run] [--only STEP[,STEP]]

Builds every document the site reads (dailies and dossiers, articles and images, live / maritime / sanctions / calendar / geoledger products,
track record, benchmarks, satellite) from the local stores and sends the ones whose content hash is not already recorded. Idempotent: a re-run
sends only what is missing or changed. ``--dry-run`` builds everything and prints how many documents would be sent (an estimate of the Class A
operations the run costs); it sends and records nothing. Prints one JSON document; exit 1 when any step failed.

The staging channel (docs/guides/deploy.md): ``--target staging`` publishes the same documents under ``staging/`` in the bucket, for a preview deployment to read.

    newsroom publish rebuild-all --target staging [--dry-run] [--only ...]    the full rebuild into staging (under its own, lower allowance)
    newsroom publish stage-from-prod [--dry-run] [--only STEP,...,views]       a SAMPLE of the current production documents and views, from the local stores
    newsroom publish staging-prune [--dry-run] [--days N]                      delete staged objects not written for N days (default 14); the daily job
    newsroom publish staging-status                                            what staging holds and today's allowance
"""

from __future__ import annotations

import json
from typing import Any


def add_target_arg(parser: Any) -> None:
    """The shared ``--target production|staging`` option (default production)."""
    parser.add_argument("--target", choices=("production", "staging"), default="production",
                        help="where to publish: production (default) or the staging/ prefix a preview deployment reads")


def apply_target(args: Any) -> None:
    from algent_backend.publishing import staging

    staging.set_target(getattr(args, "target", None) if getattr(args, "target", None) != "production" else None)


def add_parser(sub: Any) -> None:
    p = sub.add_parser("publish", help="republish everything the site reads from the local stores (rebuild-all)")
    verbs = p.add_subparsers(dest="publish_cmd", required=True)
    r = verbs.add_parser("rebuild-all", help="rebuild and publish every document (idempotent, hash-skipping)")
    r.add_argument("--dry-run", action="store_true", help="build and count; send nothing")
    r.add_argument("--only", default="", help="comma-separated steps: site-documents, articles, images, live, maritime, sanctions, calendar, geoledger, markets, ai-benchmarks, satellite")
    add_target_arg(r)
    r.set_defaults(handler=run_rebuild_all)
    sf = verbs.add_parser("stage-from-prod", help="copy a sample of the current production documents and views into staging (from local stores)")
    sf.add_argument("--dry-run", action="store_true", help="build and count; send nothing")
    sf.add_argument("--only", default="", help="comma-separated steps: site-documents, articles, live, maritime, sanctions, calendar, geoledger, markets, ai-benchmarks, views; images and satellite on request")
    sf.set_defaults(handler=run_stage_from_prod)
    sp = verbs.add_parser("staging-prune", help="delete staged objects not written for N days")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--days", type=float, default=None, help="default: database/flags.STAGING_KEEP_DAYS")
    sp.set_defaults(handler=run_staging_prune)
    verbs.add_parser("staging-status", help="what staging holds and today's allowance").set_defaults(handler=run_staging_status)


def run_rebuild_all(args: Any) -> int:
    from algent_backend.publishing import rebuild

    apply_target(args)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    report = rebuild.run(dry_run=args.dry_run, only=only or None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def run_stage_from_prod(args: Any) -> int:
    from algent_backend.publishing import staging_docs

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    report = staging_docs.stage_from_prod(dry_run=args.dry_run, only=only or None)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report["ok"] else 1


def run_staging_prune(args: Any) -> int:
    from algent_backend.publishing import staging

    report = staging.prune(days=args.days, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok", True) else 1


def run_staging_status(_args: Any) -> int:
    from algent_backend.publishing import staging

    print(json.dumps(staging.ledger().status(), indent=2))
    return 0
