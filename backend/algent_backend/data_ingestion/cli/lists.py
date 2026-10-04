"""
``lists`` — scout and vet X lists, so the roster is an editorial choice, not a default.

A list is a roster somebody else curates and keeps current, which makes it the cheapest way
to widen X discovery. But which lists to trust is a judgment with our name on the output, so
this command exists to inform that judgment rather than to bake one in.

    python -m algent_backend.cli ingest lists --scout          # candidates, ranked
    python -m algent_backend.cli ingest lists --vet <id> <id>  # are they alive and any good?

``--scout`` asks which community-built lists our trusted voices have been PUT ON (X has no
list-search endpoint, and ``followed_lists`` needs OAuth user context we do not have), then
ranks by how many of those voices a list carries — a list holding several is a real signal.

``--vet`` is the part that matters. Live checking found every candidate perfectly fresh and
most of them unusable: a 4,061-member list running to supplement spam, a geopolitics list
carrying unverified strike claims. Freshness is not quality, so read the sample before
adopting anything. Then set the ones you want:

    ALGENT_X_LISTS="<id>:ai_osint:ai,<id>:space:science"
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from ._shared import print_json, progress


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("lists", help="scout/vet X lists for the discovery band")
    parser.add_argument("--scout", action="store_true",
                        help="find community lists our trusted voices appear on")
    parser.add_argument("--vet", nargs="*", metavar="LIST_ID",
                        help="check these list ids for recency, retweet share and content")
    parser.add_argument("--handles", default=None,
                        help="comma list of handles to scout from (default: spectrum + AI roster)")
    parser.add_argument("--samples", type=int, default=6, help="posts to show per vetted list")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from algent_backend.config.env_file import load_env_file

    load_env_file(Path(__file__).resolve().parents[3] / ".env")

    if not args.scout and not args.vet:
        print_json({"error": "give --scout or --vet <list_id> ..."})
        return 1

    out: dict = {}
    if args.scout:
        out["candidates"] = _scout(args)
    if args.vet:
        out["vetted"] = [_vet(lid, args.samples) for lid in args.vet]
    print_json(out)
    return 0


def _scout(args: argparse.Namespace) -> list[dict]:
    from ..newsroom.sources.x_native import scout_community_lists

    handles = tuple(h.strip() for h in args.handles.split(",") if h.strip()) if args.handles else None
    progress("[lists] scouting community lists via list_memberships (429s are expected)…")
    found = scout_community_lists(handles)
    progress(f"[lists] {len(found)} candidates")
    for entry in found[:25]:
        progress(f"  {entry['id']:22} x{len(entry['via'])} members={entry['members']} "
                 f"{entry['name'][:40]}  via={','.join(entry['via'][:3])}")
    return found[:40]


def _vet(list_id: str, samples: int) -> dict:
    """Recency, retweet share, and a readable sample — the three things that decide it."""
    from ..newsroom.sources.x_native import _list_tweets

    try:
        posts = _list_tweets(list_id, limit=max(5, samples), client=None)
    except Exception as exc:  # noqa: BLE001
        return {"id": list_id, "error": str(exc)[:160]}
    if not posts:
        return {"id": list_id, "status": "empty"}

    newest = str(posts[0].get("created_at") or "")
    age_h = None
    try:
        age_h = round(
            (datetime.now(UTC) - datetime.fromisoformat(newest.replace("Z", "+00:00")))
            .total_seconds() / 3600, 1)
    except ValueError:
        pass
    retweets = sum(1 for p in posts if str(p.get("text") or "").startswith("RT @"))
    return {
        "id": list_id,
        "newest_age_hours": age_h,
        # A high retweet share means the list amplifies rather than reports, and the
        # originals are usually reachable anyway — a reason to pass on it.
        "retweet_share": f"{retweets}/{len(posts)}",
        "sample": [str(p.get("text") or "")[:140] for p in posts[:samples]],
    }
