"""``site retract`` — pull a published article to an honest tombstone (never a silent 404)."""

from __future__ import annotations

import argparse

from algent_backend.publishing import publish as pb
from algent_backend.publishing import site_git

from ..runs._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("retract", help="retract a live article, leaving an honest tombstone")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--reason", required=True)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = site_git.repo_root()
    push = site_git.publish_enabled()

    worktree = None
    if push:
        worktree, note = site_git.ensure_worktree(root)
        if worktree is None:
            print_json({"action": "error", "note": note})
            return 1
        target = site_git.live_site_dir(root)
    else:
        target = site_git.site_dir(root)

    result = pb.retract(args.slug, args.reason, site_dir=target)

    pushed = None
    if push and worktree is not None and result.action == "retracted":
        _ok, pushed = site_git.commit_and_push(worktree, message=f"retract({args.slug}): {args.reason}")

    print_json({
        "action": result.action, "slug": result.slug, "reasons": result.reasons,
        "kill_switch": "on" if push else "off (staged, not pushed)", "pushed": pushed,
    })
    return 0 if result.action == "retracted" else 1
