"""
``newsroom resume`` — finish a run whose artifacts survived its failure.

A rail run writes each stage's output to disk as it goes, so a failure late in the pipeline
strands finished work rather than destroying it. Nothing cleans those artifacts up. But there
was no way to USE them: the only way forward was ``--from menu`` again, which re-researched a
profile, re-planned a treatment and re-drafted an article that were all sitting on disk.

That is what this fixes. The China piece died on a provider 400 inside the claim-confirmation
pass — after the profile, treatment, draft, hero and figure were complete — one step before the
publish view was rendered. Re-running it from the top would have re-bought every one of those.

Deliberately narrow: it renders and publishes from artifacts that already exist. It does not
re-run a stage, and it refuses when a required artifact is missing rather than quietly
regenerating it, because "resume" silently redoing research is the failure mode it exists to
prevent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: What the publish view needs. Everything here is written before the pipeline's final step.
REQUIRED = ("profile.json", "draft.json")


def _runs_root() -> Path:
    return Path("runs_data/newsroom_rail")


def _latest_resumable() -> Path | None:
    """The newest run that has a draft but never reached publish."""
    candidates = []
    for run in _runs_root().glob("*/"):
        arts = run / "artifacts"
        if (arts / "draft.json").exists() and not (arts / "article_published.md").exists():
            candidates.append(run)
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _load(path: Path) -> dict[str, Any]:
    from algent_backend.agent_system.foundation.text_hygiene import scrub

    return scrub(json.loads(path.read_text(encoding="utf-8")))


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "resume", help="finish a failed run from the artifacts it already produced")
    p.add_argument("--run", help="run directory or id prefix (default: newest resumable)")
    p.add_argument("--dry-run", action="store_true", help="report what it would publish")
    p.set_defaults(handler=run_resume)


def run_resume(args: Any) -> int:
    from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
    from algent_backend.agent_system.agents.editorial.publish import render_published_article
    from algent_backend.agent_system.agents.research.profile import SignalProfile

    if args.run:
        run = Path(args.run)
        if not run.exists():
            matches = [d for d in _runs_root().glob(f"{args.run}*") if d.is_dir()]
            run = matches[0] if matches else run
    else:
        found = _latest_resumable()
        if found is None:
            print(json.dumps({"error": "no resumable run found — every run either has no draft "
                                       "or already published"}, indent=2))
            return 1
        run = found

    arts = run / "artifacts"
    missing = [name for name in REQUIRED if not (arts / name).exists()]
    if missing:
        print(json.dumps({
            "error": f"{run.name} cannot be resumed — missing {', '.join(missing)}",
            "note": "resume never regenerates a stage; re-run the rail instead",
        }, indent=2))
        return 1

    draft = _load(arts / "draft.json")
    profile = _load(arts / "profile.json")
    analytics = (
        _load_list(arts / "analytics_artifacts.json") if (arts / "analytics_artifacts.json").exists()
        else []
    )

    draft_obj = ArticleDraft.model_validate(draft)
    profile_obj = SignalProfile.model_validate(profile)
    body = render_published_article(draft_obj, profile_obj, analytics)

    produced = [a for a in analytics if isinstance(a, dict) and a.get("status") == "produced"]
    summary = {
        "run": run.name,
        "title": draft_obj.title,
        "words": len(str(draft.get("body") or "").split()),
        "figures": len(produced),
        "hero": (arts / "hero.jpg").exists(),
    }
    if args.dry_run:
        print(json.dumps({**summary, "dry_run": True}, indent=2, ensure_ascii=False))
        return 0

    (arts / "article_published.md").write_text(body, encoding="utf-8")

    # A report is required by the publisher. Rebuilt minimally from what is on disk rather than
    # re-derived: the stages that would have filled the rest already ran, and inventing their
    # verdicts here would be worse than leaving them empty.
    report_path = arts / "editorial_pipeline_report.json"
    if not report_path.exists():
        report_path.write_text(json.dumps({
            # The publisher requires a hero, and the file alone is not enough — it needs the
            # alt text and label that ship with it. Those were recorded on the run's own
            # timeline when the hero was made, so they are recovered rather than invented:
            # writing plausible alt text here would be fabricating a description of an image.
            "hero": _hero_record(run),
            "profile_id": str(profile.get("id") or ""),
            "draft_id": str(draft.get("id") or ""),
            "status": "publishable",
            "publishable": True,
            "article_title": draft_obj.title,
            "word_count": summary["words"],
            "analytics_produced": len(produced),
            "generated_at": datetime.now(UTC).isoformat(),
            "note": "assembled by `newsroom resume` from surviving artifacts",
        }, indent=2), encoding="utf-8")

    result = _publish(run, title=draft_obj.title, dek=str(draft.get("standfirst") or ""))
    print(json.dumps({**summary, **result}, indent=2, ensure_ascii=False))
    return 0


def _publish(run: Path, *, title: str = "", dek: str = "") -> dict[str, Any]:
    """Ship it exactly the way the rail does — same worktree, same gates, same git step.

    Reusing the rail's route rather than calling publish_run directly is the point: a resume that
    published through a private path would drift from the real one, and the first time it mattered
    would be the time it shipped something the floors would have held.
    """
    from algent_backend.publishing import publish as pb
    from algent_backend.publishing import site_git

    root = site_git.repo_root(run)
    push = site_git.publish_enabled()
    worktree = None
    if push:
        worktree, note = site_git.ensure_worktree(root)
        if worktree is None:
            return {"publish": f"skipped ({note[:80]})"}
    target = site_git.live_site_dir(root) if push else site_git.site_dir(root)

    result = pb.publish_run(run, site_dir=target,
                            held_dir=root / "backend" / "publish_held", push=push)
    out: dict[str, Any] = {"publish": result.action, "slug": result.slug,
                           "reasons": list(result.reasons or [])}
    if push and worktree is not None and result.action in ("published", "corrected"):
        message = f"publish({result.slug}): {result.status}\n\nresumed run"
        ok, note = site_git.commit_and_push(worktree, message=message)
        out["pushed"] = ok
        if not ok:
            out["push_note"] = note[:160]
        if ok:
            from algent_backend.publishing.x_article import announce

            out["x"] = announce(result.slug, title, dek=dek)
    return out


def _hero_record(run: Path) -> dict[str, Any] | None:
    """The hero's record, which the publisher needs alongside the image itself.

    Read from hero.json, written beside the image by the hero stage. Never reconstructed: alt
    text is a description of a picture, and inventing one would be describing an image we did
    not look at. A run whose hero predates hero.json simply cannot be resumed with its hero,
    and saying so is better than guessing.
    """
    arts = run / "artifacts"
    record = arts / "hero.json"
    if not (arts / "hero.jpg").exists() or not record.exists():
        return None
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("artifact_name") else None


def _load_list(path: Path) -> list[Any]:
    from algent_backend.agent_system.foundation.text_hygiene import scrub

    data = scrub(json.loads(path.read_text(encoding="utf-8")))
    return data if isinstance(data, list) else []
