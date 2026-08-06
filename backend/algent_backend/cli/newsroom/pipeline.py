"""
``newsroom run`` — run a chosen SLICE of the newsroom pipeline, deliberately.

The pipeline is a ladder of stages. This command runs the contiguous range you ask
for and stops, so "just refresh discovery and show me the menu" and "take these two
menu items all the way to the site" are each one command instead of a remembered
sequence of three plus a throwaway script.

    newsroom run --to menu                # discovery + synthesis, print the vector menu
    newsroom run --from menu --pick 3,7   # those two vectors -> two published articles
    newsroom run                          # the whole ladder, top to bottom
    newsroom run --to editorial           # everything, but stage instead of publishing

Why a stage ladder rather than a flag per stage
-----------------------------------------------
Stages are strictly ordered and each consumes the one above it, so the only coherent
thing to run is a *contiguous range*. ``--from``/``--to`` makes that structural fact
the interface, which means new pipes (video, audio) extend ``STAGES`` by one entry
and inherit every combination for free — no new flags, no new commands.

What the menu is
----------------
The **t1 portfolio** — research vectors, each an angle with a thesis and the questions
it has to answer. Not the raw t0 pool, which is wire headlines: picking a headline
leaves synthesis free to turn it into a different story, and picking "Beyond tech
selloff: How China's homegrown DUV machine is challenging ASML" should not commit us
to writing about a selloff. Picking the angle means the operator chooses the piece
that actually gets written.

One pick produces one article. The rail is handed a portfolio narrowed to that single
vector, which takes its reuse path — no re-run of t0 or synthesis, and nothing else
the router could promote. A pick is an instruction, not a suggestion to a ranker.
"""

from __future__ import annotations

import argparse
import json
import os
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.cli.runs._shared import print_json

#: The pipeline, in order. Adding a downstream pipe (video, audio) is one entry here.
#: ``menu`` is a stop point rather than a compute step — it prints what t0 produced —
#: but it lives in the ladder because it is a place an operator genuinely stops.
STAGES: tuple[str, ...] = (
    "t0",         # build the discovery pool from its source channels
    "synthesis",  # pool -> t1 research portfolio (raw candidates -> angles)
    "menu",       # print that portfolio as a numbered menu (stop point)
    "route",      # portfolio -> the promoted vector
    "profile",    # vector -> t2 signal profile
    "gauntlet",   # profile review / enrichment
    "editorial",  # profile -> drafted, headlined, caveated article
    "publish",    # article -> the live site
)

#: The menu is the **t1 portfolio**, not the raw t0 pool. A pool item is a wire
#: headline; a vector is an angle with a thesis and the questions it has to answer.
#: Picking angles means the operator chooses the story that will actually be written,
#: rather than a candidate that synthesis may still turn into something else.

def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "run", help="run a slice of the newsroom pipeline (--from/--to/--pick)",
    )
    parser.add_argument(
        "--from", dest="from_stage", choices=STAGES, default="t0",
        help="first stage to run (default: t0 — build discovery from scratch)",
    )
    parser.add_argument(
        "--to", dest="to_stage", choices=STAGES, default="publish",
        help="last stage to run (default: publish — the site is the review surface)",
    )
    parser.add_argument(
        "--pick", default=None,
        help="menu VECTOR numbers to carry forward. Comma separates articles, '+' joins "
             "vectors into ONE article: --pick 3+7,12 makes two articles, the first built "
             "from vectors 3 and 7 together. Pair with --menu to pin a frozen portfolio "
             "so numbers stay valid after a later synthesis rebuild.",
    )
    parser.add_argument(
        "--menu", default=None,
        help="portfolio JSON (or discovery_synthesis run dir) to resolve --pick against. "
             "Use when the menu you are numbering is not the latest — stale / prior menus "
             "stay pickable without rebuilding synthesis.",
    )
    parser.add_argument(
        "--brief", default=None,
        help="ad-hoc story with NO menu id: a title (and usually --angle as the thesis). "
             "Skips t0/synthesis entirely — invent a topic or revive a stale pick by "
             "content. Comma-separate for multiple articles.",
    )
    parser.add_argument(
        "--angle", default=None,
        help="operator steer / thesis. With --pick: prepended to the vector thesis. "
             "With --brief/--compose: becomes the thesis. Applies to every article in "
             "this run.",
    )
    parser.add_argument(
        "--compose", default=None,
        help="build the vector YOURSELF from the latest t0 POOL item numbers (does not "
             "rebuild discovery — numbers stay stable). Bypasses synthesis grouping: "
             "--compose 88+114. Pair with --angle. Pass --fresh only if you want a new pool.",
    )
    parser.add_argument(
        "--pool-menu", dest="pool_menu", action="store_true",
        help="show the raw t0 POOL menu (the numbers --compose takes) instead of the vectors",
    )
    parser.add_argument(
        "--channels", default=None,
        help="t0 source channels (default: all). Only meaningful when starting at t0.",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="rebuild t0 even if a recent pool exists",
    )
    parser.add_argument(
        "--analytics-harness", dest="analytics_harness", default=None,
        help="which coding CLI draws the figures (grok default; codex/Luna when grok quota is gone)",
    )
    parser.add_argument(
        "--analytics-model", dest="analytics_model", default=None,
        help="model for the analytics harness (codex default: gpt-5.6-luna)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the stages that would run, and the resolved picks, without running them",
    )
    parser.set_defaults(handler=run)


def _span(from_stage: str, to_stage: str) -> list[str]:
    lo, hi = STAGES.index(from_stage), STAGES.index(to_stage)
    if lo > hi:
        raise ValueError(f"--from {from_stage} is after --to {to_stage}")
    return list(STAGES[lo : hi + 1])


def _latest_pool() -> tuple[dict[str, Any], Path]:
    from algent_backend.data_ingestion.newsroom.discovery.pipeline import pool_dir

    files = sorted(Path(pool_dir()).glob("pool_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError("no t0 pool exists yet — run with --from t0 first")
    return json.loads(files[-1].read_text(encoding="utf-8")), files[-1]


def _latest_portfolio() -> tuple[dict[str, Any], Path]:
    """The most recent t1 portfolio — the menu the operator was last shown."""
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    files = sorted(
        Path(runs_data_root()).glob("discovery_synthesis/*/artifacts/research_portfolio.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        raise FileNotFoundError(
            "no research portfolio exists yet — run with --from t0 (or --from synthesis) first"
        )
    return json.loads(files[-1].read_text(encoding="utf-8")), files[-1]


def load_portfolio(spec: str | None = None) -> tuple[dict[str, Any], Path]:
    """Load a t1 portfolio — explicit ``--menu`` path/run, else the latest.

    ``spec`` may be a ``research_portfolio.json`` path, any file that is the portfolio
    JSON, or a ``discovery_synthesis/<run>`` directory (artifacts resolved inside).
    """
    if not spec or not str(spec).strip():
        return _latest_portfolio()
    path = Path(spec).expanduser()
    if path.is_dir():
        candidate = path / "artifacts" / "research_portfolio.json"
        if not candidate.is_file():
            candidate = path / "research_portfolio.json"
        path = candidate
    if not path.is_file():
        raise FileNotFoundError(f"--menu {spec!r}: portfolio file not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not (data.get("vectors") or []):
        raise ValueError(f"--menu {spec!r}: no vectors in portfolio")
    return data, path


def _resolve_picks(
    portfolio: dict[str, Any], spec: str,
) -> list[tuple[list[int], list[dict[str, Any]]]]:
    """Turn ``"3+7,12"`` into pick GROUPS of VECTORS, failing loudly on a bad number.

    Comma separates articles; ``+`` joins vectors into one article. Synthesis usually
    groups a story already, but not always — a telescope's hardware failing and that
    same telescope's latest observation can arrive as two vectors when they are one
    piece — so joining stays available.

    A silently-dropped pick is the worst outcome here: the run would look successful
    and quietly publish something nobody chose. So every number is validated, and a
    bad one raises rather than being skipped.
    """
    items = portfolio.get("vectors") or []
    groups: list[tuple[list[int], list[dict[str, Any]]]] = []
    for token in (s.strip() for s in spec.split(",")):
        if not token:
            continue
        numbers: list[int] = []
        for raw in (part.strip() for part in token.split("+")):
            if not raw.isdigit():
                raise ValueError(f"pick {raw!r} is not a menu number")
            n = int(raw)
            if not 1 <= n <= len(items):
                raise ValueError(f"pick {n} is out of range (menu has {len(items)} vectors)")
            numbers.append(n)
        groups.append((numbers, [items[n - 1] for n in numbers]))
    if not groups:
        raise ValueError("--pick was given but resolved to no items")
    return groups


def _merge_vectors(picked: list[dict[str, Any]], *, angle: str | None) -> dict[str, Any]:
    """Fold joined vectors into the single vector the rail will research.

    Union the evidence (supporting hits, seed sources, questions) so nothing the
    operator picked is dropped, and keep every thesis — the research agent needs to
    know it is covering both, not one with the other as a footnote.
    """
    head = dict(picked[0])
    if len(picked) > 1:
        seen_q: list[str] = []
        for v in picked:
            for q in v.get("key_questions") or []:
                if q not in seen_q:
                    seen_q.append(q)
        head["key_questions"] = seen_q
        head["supporting_hits"] = list(dict.fromkeys(
            h for v in picked for h in (v.get("supporting_hits") or [])
        ))
        head["sources"] = list(dict.fromkeys(
            s for v in picked for s in (v.get("sources") or [])
        ))
        head["title"] = " + ".join(str(v.get("title") or "") for v in picked)
        head["thesis"] = (
            "These are ONE story, joined deliberately. Cover them together as a single "
            "piece rather than treating either as background to the other. "
            + " ".join(str(v.get("thesis") or "") for v in picked)
        )
    if angle:
        head["thesis"] = (
            f"OPERATOR STEER — the angle this was picked for: {angle} "
            "Build the piece around THIS; where the thesis below disagrees, the steer wins. "
            + str(head.get("thesis") or "")
        )
    return head


def _seed_portfolio(
    portfolio: dict[str, Any],
    picked: list[dict[str, Any]],
    numbers: list[int],
    *,
    angle: str | None = None,
) -> Path:
    """Write a one-vector portfolio for the rail, and keep it as the record of the pick.

    One vector, so routing has nothing else it could promote: a pick is an instruction,
    not a suggestion to a ranker.
    """
    from algent_backend.data_ingestion.newsroom.discovery.pipeline import pool_dir

    seeded = dict(portfolio)
    seeded["vectors"] = [_merge_vectors(picked, angle=angle)]
    seeded["picked_from_menu"] = numbers
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    tag = "-".join(str(n) for n in numbers)
    path = Path(pool_dir()) / f"pick_{stamp}_{tag}.json"
    path.write_text(json.dumps(seeded, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def compose_vector(
    picked: list[dict[str, Any]], numbers: list[int], *, angle: str | None,
) -> dict[str, Any]:
    """Build a research vector directly from t0 pool items the operator chose.

    Synthesis decides for itself which candidates belong together, and it is sometimes
    wrong — it split a telescope's hardware failure from that same telescope's landmark
    observation into two vectors, then promoted one and dropped the other. This is the
    escape hatch: the operator says which raw items are one story, and that grouping is
    final. ``angle`` becomes the thesis, because a human who is hand-assembling a vector
    is telling us what the story is; without one we fall back to the item labels.
    """
    labels = [str(v.get("label") or "") for v in picked]
    joined = " + ".join(label for label in labels if label)
    thesis = angle.strip() if angle and angle.strip() else joined
    if len(picked) > 1 and (not angle or not angle.strip()):
        thesis = (
            "These are ONE story, joined deliberately by the editor. Cover them together "
            f"as a single piece rather than either as background to the other. {joined}"
        )
    return {
        "id": "",  # filled by ensure_vector_ids downstream
        "title": joined[:180] or "operator-composed vector",
        "thesis": thesis,
        "vector_type": "story",
        "rationale": (
            "Hand-composed by the editor from t0 items "
            + ", ".join(str(n) for n in numbers)
            + ". The grouping is deliberate and is not to be re-litigated."
        ),
        "supporting_hits": [str(v.get("id") or "") for v in picked if v.get("id")],
        "pillars": list(dict.fromkeys(p for v in picked for p in (v.get("pillars") or []))),
        "scope": list(dict.fromkeys(s for v in picked for s in (v.get("scope") or []))),
        "research_effort": "deep",
        "key_questions": [],
        "sources": list(dict.fromkeys(
            str(e.get("url") or "")
            for v in picked for e in (v.get("evidence") or []) if e.get("url")
        )),
    }


def ad_hoc_vector(title: str, *, angle: str | None = None) -> dict[str, Any]:
    """Build a research vector from thin air — no menu id, no t0 hits required.

    Use when the operator invents a topic, or when a prior menu pick is revived by
    title/thesis after the numbered menu has been replaced. Research still has to
    ground the piece; this only makes promotion not depend on a live menu index.
    """
    cleaned = (title or "").strip()
    if not cleaned:
        raise ValueError("--brief needs a non-empty title")
    thesis = (angle or "").strip() or cleaned
    return {
        "id": "",
        "title": cleaned[:180],
        "thesis": thesis,
        "vector_type": "story",
        "rationale": (
            "Ad-hoc operator brief — not derived from a live synthesis menu id. "
            "Treat the title/thesis as the assigned story; research must still ground it."
        ),
        "supporting_hits": [],
        "pillars": [],
        "scope": [],
        "research_effort": "deep",
        "key_questions": [],
        "sources": [],
    }


def _parse_briefs(spec: str) -> list[str]:
    titles = [t.strip() for t in spec.split(",") if t.strip()]
    if not titles:
        raise ValueError("--brief was given but resolved to no titles")
    return titles


def print_vector_menu(portfolio: dict[str, Any], *, out) -> None:
    """Print the portfolio as the numbered menu an operator picks from.

    Titles and theses are never truncated — the operator menu must be paste-complete.
    """
    vectors = portfolio.get("vectors") or []
    print(f"\n=== SYNTHESIS MENU — {len(vectors)} research vectors ===", file=out)
    for n, v in enumerate(vectors, 1):
        pillars = ", ".join(v.get("pillars") or []) or "-"
        print(f"\n{n:3}. ({pillars})  {v.get('title') or ''}", file=out)
        thesis = str(v.get("thesis") or "").strip()
        if thesis:
            print(f"     {thesis}", file=out)
        hits = v.get("supporting_hits") or []
        print(f"     [{v.get('vector_type', '?')} | effort {v.get('research_effort', '?')} "
              f"| {len(hits)} hits]", file=out)
    print(file=out)


def _start(args: Namespace, agent_id: str, *, file: Path | None, key: str | None) -> int:
    """Launch a registered agent in-process, reusing ``runs start`` for identical bookkeeping."""
    from algent_backend.cli.runs import start

    return start.run(Namespace(
        agent_id=agent_id,
        input=None, topic=None, goal=None,
        input_file=str(file) if file else None,
        input_key=key if file else None,
        fixture=False, from_run=None,
        runtime="langgraph", max_turns=None,
        analytics_harness=args.analytics_harness,
        analytics_model=args.analytics_model,
        foreground=True,
    ))


def _synthesis(args: Namespace, *, pool_file: Path | None) -> int:
    return _start(args, "discovery_synthesis", file=pool_file, key="pool")


def _rail(args: Namespace, *, portfolio_file: Path | None, publish: bool) -> int:
    """Run the newsroom rail on a chosen portfolio, skipping the discovery it already has.

    Feeding ``portfolio`` takes the rail's reuse path: it does not re-run t0 or synthesis,
    so the vector the operator picked is the vector that gets researched.
    """
    # The rail's publish step reads this at the moment it ships, so setting it here
    # reaches it whether the graph runs in this process or a spawned child.
    os.environ["ALGENT_SITE_PUBLISH"] = "1" if publish else "0"
    return _start(args, "newsroom_rail", file=portfolio_file, key="portfolio")


def run(args: argparse.Namespace) -> int:
    from algent_backend.data_ingestion.cli._shared import progress

    import sys

    # --compose / --brief skip discovery rebuild: the operator already named the story.
    if (args.compose or args.brief) and args.from_stage == "t0" and not args.fresh:
        args.from_stage = "synthesis"

    try:
        stages = _span(args.from_stage, args.to_stage)
    except ValueError as exc:
        print_json({"error": str(exc)})
        return 1

    result: dict[str, Any] = {"stages": stages}

    # -- brief: ad-hoc vectors (no menu id, no pool required) ------------------
    if args.brief:
        try:
            titles = _parse_briefs(args.brief)
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
        briefs = [(i + 1, ad_hoc_vector(title, angle=args.angle)) for i, title in enumerate(titles)]
        result["briefs"] = [{"n": n, "title": v["title"]} for n, v in briefs]
        if args.dry_run:
            result["dry_run"] = True
            print_json(result)
            return 0
        publish = "publish" in stages
        runs = []
        empty = {"generated_at": "", "vectors": [], "origin": "ad_hoc"}
        for n, vector in briefs:
            seed = _seed_portfolio(empty, [vector], [n], angle=None)
            progress(f"[rail] brief {n}: {vector['title'][:80]}")
            runs.append({"brief": n, "seed_portfolio": str(seed),
                         "exit_code": _rail(args, portfolio_file=seed, publish=publish)})
        result["runs"] = runs
        result["exit_code"] = max(r["exit_code"] for r in runs)
        print_json(result)
        return int(result["exit_code"])

    # -- t0 -------------------------------------------------------------------
    if "t0" in stages:
        from algent_backend.data_ingestion.newsroom.discovery.pipeline import (
            DEFAULT_FRESH_MINUTES,
            ensure_t0,
            resolve_channels,
        )

        chans = resolve_channels(set(args.channels.split(",")) if args.channels else None)
        if args.dry_run:
            result["would_build_t0_with"] = sorted(chans)
            pool, pool_path = _latest_pool()[0], None
        else:
            progress(f"[t0] building with channels: {', '.join(sorted(chans))}")
            pool, path = ensure_t0(
                channels=chans,
                fresh_minutes=0 if args.fresh else DEFAULT_FRESH_MINUTES,
                on_progress=progress,
            )
            pool_path = Path(path)
            result["pool"] = {
                "path": str(path),
                "item_count": pool.get("item_count"),
                "by_channel": pool.get("by_channel"),
            }
    else:
        pool, pool_path = _latest_pool()
        result["pool"] = {"path": str(pool_path), "item_count": pool.get("item_count"),
                          "reused": True}
        if args.compose:
            progress(f"[t0] reusing pool ({pool_path.name}) for --compose")

    # -- compose: the operator builds the vector from raw t0 items --------------
    # Handled before synthesis because it REPLACES synthesis: the grouping is the
    # editor's, so there is nothing for synthesis to decide and no reason to pay for it.
    if args.compose:
        try:
            groups = _resolve_picks({"vectors": pool.get("items") or []}, args.compose)
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
        composed = [
            (numbers, compose_vector(items, numbers, angle=args.angle))
            for numbers, items in groups
        ]
        result["composed"] = [
            {"from_pool_items": numbers, "title": v["title"]} for numbers, v in composed
        ]
        if args.dry_run:
            result["dry_run"] = True
            print_json(result)
            return 0

        publish = "publish" in stages
        runs = []
        for numbers, vector in composed:
            seed = _seed_portfolio(
                {"generated_at": pool.get("generated_at", ""), "vectors": []},
                [vector], numbers,
            )
            progress(f"[rail] composed {'+'.join(map(str, numbers))}: {vector['title'][:80]}")
            runs.append({"from_pool_items": numbers, "seed_portfolio": str(seed),
                         "exit_code": _rail(args, portfolio_file=seed, publish=publish)})
        result["runs"] = runs
        result["exit_code"] = max(r["exit_code"] for r in runs)
        print_json(result)
        return int(result["exit_code"])

    # -- synthesis (pool -> t1 portfolio) --------------------------------------
    portfolio: dict[str, Any] = {}
    portfolio_path: Path | None = None
    # Durable pause: flags.SYNTHESIS_ENABLED (env is one-shot only). When off, do not
    # *run* synthesis — but --pick must still reuse the last vector portfolio. Forcing
    # pool_menu on pick would mis-number the operator's synthesis menu choices.
    from algent_backend.agent_system.agents.newsroom.flags import synthesis_enabled
    synthesis_off = not synthesis_enabled()
    pool_menu_only = bool(args.pool_menu and args.to_stage == "menu")
    if synthesis_off and "synthesis" in stages and not args.pick:
        progress("[synthesis] off (flags.SYNTHESIS_ENABLED) — using t0 pool menu")
        args.pool_menu = True
        pool_menu_only = True
    run_synthesis = (
        "synthesis" in stages
        and not args.dry_run
        and not synthesis_off
        and not pool_menu_only
    )
    if run_synthesis:
        progress("[synthesis] turning the pool into research vectors…")
        code = _synthesis(args, pool_file=pool_path)
        if code != 0:
            print_json({**result, "error": "synthesis failed", "exit_code": code})
            return code
        portfolio, portfolio_path = _latest_portfolio()
        result["portfolio"] = {"path": str(portfolio_path),
                               "vectors": len(portfolio.get("vectors") or [])}
    elif args.pick or (args.to_stage == "menu" and not args.pool_menu):
        # Picks are synthesis-menu numbers; --menu pins a frozen portfolio so a later
        # rebuild cannot renumber the operator's choices. Vector menu reprint needs
        # the same file.
        try:
            portfolio, portfolio_path = load_portfolio(args.menu)
        except (FileNotFoundError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
        result["portfolio"] = {"path": str(portfolio_path),
                               "vectors": len(portfolio.get("vectors") or []),
                               "reused": True,
                               "pinned": bool(args.menu)}

    # -- menu -----------------------------------------------------------------
    # Operator contract: t0-only → pool menu. Synthesis stop → BOTH full menus
    # (pool numbers ≠ vector numbers). See cli/newsroom/AGENTS.md.
    if "menu" in stages and not args.dry_run:
        from algent_backend.data_ingestion.cli.t0 import print_menu
        if args.pool_menu:
            print_menu(pool, out=sys.stderr)
        else:
            print_menu(pool, out=sys.stderr)
            print_vector_menu(portfolio, out=sys.stderr)

    if args.to_stage == "menu":
        result["stopped_at"] = "menu"
        print_json(result)
        return 0

    # -- picks ----------------------------------------------------------------
    picks: list[tuple[list[int], list[dict[str, Any]]]] = []
    if args.pick:
        try:
            picks = _resolve_picks(portfolio, args.pick)
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
        result["picked"] = [
            {"picks": numbers, "titles": [v.get("title") for v in group]}
            for numbers, group in picks
        ]

    if args.dry_run:
        result["dry_run"] = True
        print_json(result)
        return 0

    # -- route .. publish, via the rail ---------------------------------------
    publish = "publish" in stages
    if not publish:
        progress("[rail] publish stage excluded — the article will be staged, not shipped")

    if picks:
        runs = []
        for numbers, group in picks:
            seed = _seed_portfolio(portfolio, group, numbers, angle=args.angle)
            tag = "+".join(str(n) for n in numbers)
            progress(f"[rail] pick {tag}: {str(group[0].get('title'))[:80]}")
            runs.append({"picks": numbers, "seed_portfolio": str(seed),
                         "exit_code": _rail(args, portfolio_file=seed, publish=publish)})
        result["runs"] = runs
        result["exit_code"] = max(r["exit_code"] for r in runs)
    else:
        result["exit_code"] = _rail(args, portfolio_file=portfolio_path, publish=publish)

    print_json(result)
    return int(result["exit_code"])
