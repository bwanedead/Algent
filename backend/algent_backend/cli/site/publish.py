"""``site publish`` — gate a finished run and push it live (default), or stage if publish is paused."""

from __future__ import annotations

import argparse

from algent_backend.agent_system.runs.control_plane.layout import find_run_root
from algent_backend.publishing import publish as pb
from algent_backend.publishing import site_git

from ..runs._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("publish", help="stage/publish a finished run's article to the site")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--correction", default="",
                        help="reason — required to re-publish a story already live (visible correction)")
    parser.add_argument("--hold-named-individuals", action="store_true",
                        help="opt-in: hold pieces naming a person alongside accusation-class language")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    run_root = find_run_root(args.run_id)
    if run_root is None:
        print_json({"error": f"unknown run '{args.run_id}'"})
        return 1

    root = site_git.repo_root(run_root)
    held_dir = root / "backend" / "publish_held"
    push = site_git.publish_enabled()
    drift = site_git.site_code_drift(root)

    worktree = None
    if push:
        worktree, note = site_git.ensure_worktree(root)
        if worktree is None:                              # can't reach site-live -> refuse to push, stage instead
            print_json({"action": "error", "push": True, "note": note})
            return 1
        target = site_git.live_site_dir(root)
    else:
        target = site_git.site_dir(root)

    result = pb.publish_run(
        run_root, site_dir=target, held_dir=held_dir,
        correction=args.correction, push=push,
        hold_named_individuals=args.hold_named_individuals,
    )

    pushed = None
    if push and worktree is not None and result.action in ("published", "corrected"):
        ok, pushed = site_git.commit_and_push(worktree, message=_commit_message(result))

    print_json({
        "action": result.action,
        "slug": result.slug,
        "status": result.status,
        "reasons": result.reasons,
        "content_path": result.content_path,
        "live_publish": "on" if push else "paused (staged only; ALGENT_SITE_PUBLISH=0)",
        "pushed": pushed,
        "drift_warning": drift,
        "digest": result.digest,
    })
    return 0 if result.action not in ("error", "refused") else 1


def _commit_message(result: pb.PublishResult) -> str:
    verb = "correct" if result.action == "corrected" else "publish"
    return f"{verb}({result.slug}): {result.status}\n\n{result.digest}"
