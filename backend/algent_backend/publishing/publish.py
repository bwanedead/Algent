"""
The publish orchestration — a finished run -> a staged/live site article, or a held-queue entry.

Auto-publish, with the FLOORS as the gate (not a human): only an article whose pipeline status is
``publishable`` — meaning the caveat reviewer actually ran and passed — is eligible for the site.
``needs_hedging`` / anything that couldn't earn ``publishable`` goes to a held queue (a small ledger
the operator glances at on demand); ``blocked`` is refused outright. Nothing here reads an article
for a human before it ships — the design bet is that the grounding floor, figure checks, caveat
reviewer, and receipts make the machine trustworthy enough to run itself, and that CORRECTIONS
(visible, dated, first-class) are the post-publish safety valve.

This module owns the file/ledger/gating logic (pure enough to test against a tmp site dir). The git
commit+push to the ``site-live`` branch lives in ``site_git.py`` and only runs when the kill switch
(``ALGENT_SITE_PUBLISH``) is on — off by default until the Vercel wiring + one verified end-to-end.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .converter import SiteArticle, build_slug, convert, parse_published_article

# Only a caveat-verified article auto-publishes. These are the pipeline's terminal statuses.
_PUBLISHABLE = "publishable"
_BLOCKED = "blocked"

# Actions a publish attempt can resolve to (the ledger records which).
Action = str  # published | staged | held | corrected | refused | blocked | retracted | error


@dataclass
class PublishResult:
    action: Action
    slug: str = ""
    status: str = ""
    reasons: list[str] = field(default_factory=list)
    digest: str = ""
    content_path: str = ""


def _read_run(run_dir: Path) -> tuple[str, dict, dict, dict] | None:
    """Load (article_md, rail_report, pipeline_report, profile) from a run dir. None if incomplete."""
    art = run_dir / "artifacts"
    article = art / "article_published.md"
    pipeline_f = art / "editorial_pipeline_report.json"
    if not article.exists() or not pipeline_f.exists():
        return None
    pipeline = json.loads(pipeline_f.read_text(encoding="utf-8"))
    rail_f = art / "newsroom_rail_report.json"
    rail = json.loads(rail_f.read_text(encoding="utf-8")) if rail_f.exists() else {}
    profile_f = art / "profile.json"
    profile = json.loads(profile_f.read_text(encoding="utf-8")) if profile_f.exists() else {}
    return article.read_text(encoding="utf-8"), rail, pipeline, profile


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _existing_corrections(content_path: Path) -> list[dict]:
    """The ``corrections`` list already on a published article (so a new correction appends)."""
    if not content_path.exists():
        return []
    try:
        text = content_path.read_text(encoding="utf-8")
        if text.startswith("---"):
            fm = yaml.safe_load(text.split("---\n", 2)[1]) or {}
            got = fm.get("corrections")
            return list(got) if isinstance(got, list) else []
    except Exception:  # noqa: BLE001 — a malformed existing file must not block a correction
        pass
    return []


def publish_run(
    run_dir: Path,
    *,
    site_dir: Path,
    held_dir: Path,
    correction: str = "",
    today: str | None = None,
    push: bool = False,
) -> PublishResult:
    """Gate a finished run and stage/hold it. ``push`` (the kill switch) is applied by the caller's
    git step; here it only distinguishes the recorded action (``staged`` vs ``published``)."""
    today = today or _today()
    loaded = _read_run(run_dir)
    if loaded is None:
        return PublishResult(action="error", reasons=["run has no article_published.md + pipeline report"])
    article_md, rail, pipeline, profile = loaded

    status = str(pipeline.get("status") or "")
    title, _dek, _rest = parse_published_article(article_md)
    profile_id = str(pipeline.get("profile_id") or rail.get("profile_id") or "")
    slug = build_slug(title, profile_id)
    run_id = run_dir.name

    # ── the gate ──────────────────────────────────────────────────────────────────────────────
    if status == _BLOCKED:
        return _hold(held_dir, slug, status, ["status is blocked — dropped required evidence"],
                     run_id, rail, pipeline, action="blocked")
    if status != _PUBLISHABLE:
        reason = f"status is '{status or 'unknown'}', not publishable (caveat lane did not pass)"
        return _hold(held_dir, slug, status, [reason], run_id, rail, pipeline)

    # ── publishable: convert + stage (or correct) ─────────────────────────────────────────────
    content_path = site_dir / "content" / "articles" / f"{slug}.md"
    corrections = _existing_corrections(content_path)
    is_rewrite = content_path.exists()
    if is_rewrite and not correction:
        # Overwriting a live article is a correction, and corrections are visible, never silent.
        return PublishResult(action="refused", slug=slug, status=status,
                             reasons=[f"'{slug}' already published — re-publishing requires "
                                      "--correction \"<reason>\" (no silent overwrite)"])
    if is_rewrite:
        corrections = [*corrections, {"date": today, "reason": correction}]

    article = convert(article_md=article_md, rail=rail, pipeline=pipeline, profile=profile,
                      date=today, run_id=run_id, corrections=corrections or None)
    _write_article(site_dir, article, run_dir)
    _append_publish_ledger(site_dir, article, run_id,
                           kind="correction" if is_rewrite else "publish", pushed=push)

    action = "corrected" if is_rewrite else ("published" if push else "staged")
    return PublishResult(action=action, slug=article.slug, status=status,
                         digest=article.digest, content_path=str(content_path),
                         reasons=([f"correction: {correction}"] if is_rewrite else []))


def retract(slug: str, reason: str, *, site_dir: Path, today: str | None = None) -> PublishResult:
    """Pull a published article, leaving an honest tombstone at its URL (never a silent 404)."""
    today = today or _today()
    content_path = site_dir / "content" / "articles" / f"{slug}.md"
    if not content_path.exists():
        return PublishResult(action="error", slug=slug, reasons=[f"no published article '{slug}'"])
    prior = {}
    try:
        text = content_path.read_text(encoding="utf-8")
        if text.startswith("---"):
            prior = yaml.safe_load(text.split("---\n", 2)[1]) or {}
    except Exception:  # noqa: BLE001
        pass
    fm = {
        "title": prior.get("title", slug), "dek": f"Retracted on {today}.",
        "date": prior.get("date", today), "status": "retracted",
        "retraction": {"date": today, "reason": reason},
    }
    body = (f"**This article was retracted on {today}.**\n\n"
            f"Reason: {reason}\n\n"
            "The original text has been withdrawn. This notice remains so the record is honest and "
            "the URL does not silently disappear.\n")
    content_path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=4096)
                            + "---\n\n" + body, encoding="utf-8")
    _append_ledger(site_dir / "publish-ledger.md",
                   f"### RETRACTED {slug} — {today}\nReason: {reason}\n")
    return PublishResult(action="retracted", slug=slug, reasons=[reason], content_path=str(content_path))


# ── file + ledger writers ──────────────────────────────────────────────────────────────────────

def _write_article(site_dir: Path, article: SiteArticle, run_dir: Path) -> None:
    content_path = site_dir / "content" / "articles" / f"{article.slug}.md"
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(article.markdown, encoding="utf-8")
    if article.assets:
        dest = site_dir / "public" / "analytics" / article.slug
        dest.mkdir(parents=True, exist_ok=True)
        for name in article.assets:
            src = run_dir / "artifacts" / name
            if src.exists():
                shutil.copyfile(src, dest / name)


def _hold(
    held_dir: Path, slug: str, status: str, reasons: list[str], run_id: str,
    rail: dict, pipeline: dict, *, action: str = "held",
) -> PublishResult:
    from .converter import quality_digest
    digest = quality_digest(rail, pipeline, run_id=run_id)
    held_dir.mkdir(parents=True, exist_ok=True)
    entry = (f"### {status.upper() or 'HELD'} {slug} — {_today()}\n"
             + "\n".join(f"- {r}" for r in reasons) + f"\n\n{digest}\n")
    _append_ledger(held_dir / "held-ledger.md", entry)
    return PublishResult(action=action, slug=slug, status=status, reasons=reasons, digest=digest)


def _append_publish_ledger(site_dir: Path, article: SiteArticle, run_id: str, *, kind: str, pushed: bool) -> None:
    head = f"### {kind.upper()} {article.slug} — {article.date}" + ("" if pushed else "  (staged; push paused)")
    _append_ledger(site_dir / "publish-ledger.md", f"{head}\n{article.digest}\n")


def _append_ledger(path: Path, entry: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(("\n" if path.stat().st_size else "") + entry.rstrip() + "\n")
