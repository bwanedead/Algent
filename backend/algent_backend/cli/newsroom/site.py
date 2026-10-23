"""
``newsroom site`` - checks of the deployed site (docs/guides/deploy.md).

    newsroom site smoke [--base URL] [--json] [--log]     request every registered route, a sample of dynamic pages and the agent API; exit 1 on any failure
    newsroom site deploy-check [--ref BRANCH | --sha SHA | --url URL] [--wait-min N] [--json]
                                                          wait for the Vercel preview of a commit (GitHub REST, no gh CLI) and smoke-test it

``--base`` defaults to production (ops/smoke/flags.PRODUCTION_BASE); pass a preview URL to check a deployment before promoting it. ``--log`` (what the hourly
``site-smoke`` job passes) keeps the report for the doctor row and writes ~/ops-log.md on failures and recoveries; a run against any other base never does.
Free; no model; about 60 paced requests.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("site", help="checks of the deployed site: smoke test of every route and the agent API")
    verbs = p.add_subparsers(dest="site_cmd", required=True)
    s = verbs.add_parser("smoke", help="request the site's routes and judge the answers")
    s.add_argument("--base", default="", help="site origin to check (default: production)")
    s.add_argument("--json", action="store_true", help="the full report as JSON")
    s.add_argument("--log", action="store_true", help="record the result for the doctor and write ~/ops-log.md on failure/recovery (production only)")
    s.set_defaults(handler=run_smoke)
    d = verbs.add_parser("deploy-check", help="wait for the Vercel preview of a commit and smoke-test it (exit 0 healthy, 1 smoke failed, 3 no ready preview)")
    d.add_argument("--ref", default="organic-dev", help="branch whose newest commit is checked (default organic-dev)")
    d.add_argument("--sha", default="", help="a commit instead of --ref")
    d.add_argument("--url", default="", help="the preview URL, skipping the GitHub lookup")
    d.add_argument("--wait-min", type=float, default=15.0, help="how long to wait for Vercel (default 15)")
    d.add_argument("--json", action="store_true")
    d.set_defaults(handler=run_deploy_check)


def run_smoke(args: Any) -> int:
    from algent_backend.ops.smoke import flags, run, state

    try:
        report = run.run(args.base or None)
    except ValueError as exc:
        print(str(exc))
        return 2
    if args.log and report.base == flags.PRODUCTION_BASE:
        state.record(report)
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False) if args.json else report.text())
    return 0 if report.ok else 1


def run_deploy_check(args: Any) -> int:
    from algent_backend.ops.smoke import deploy, run

    url = args.url
    if not url:
        try:
            slug = deploy.origin_slug()
            sha = args.sha or deploy.resolve_sha(slug, args.ref)
        except (ValueError, LookupError) as exc:
            print(str(exc))
            return 2
        state, url, note = deploy.wait_for_preview(slug, sha, wait_s=args.wait_min * 60)
        print(f"preview of {sha[:8]}: {state}" + (f" {url}" if url else "") + (f" ({note})" if note else ""))
        if state != "ready":
            return 3
    try:
        report = run.run(url)
    except ValueError as exc:
        print(str(exc))
        return 2
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False) if args.json else report.text())
    if report.ok:
        print("preview is healthy: promote with a merge into site-live (docs/guides/deploy.md)")
    return 0 if report.ok else 1
