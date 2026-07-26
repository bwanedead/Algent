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
commit+push to the ``site-live`` branch lives in ``site_git.py`` and runs by default
(``ALGENT_SITE_PUBLISH`` ON unless explicitly set to 0/false/off).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .converter import SiteArticle, build_slug, convert, parse_published_article

# The pipeline's terminal statuses.
_PUBLISHABLE = "publishable"
_BLOCKED = "blocked"

# THE STATUS GATE IS OFF BY DEFAULT. Operator decision: nothing may stand between a produced
# article and the operator reading it — the site IS the review surface, and a held piece breaks the
# only feedback loop that improves the machine. So every finished piece publishes regardless of
# status, and its honest `status` rides in the frontmatter for the reader to see (the site shows
# it). The gate machinery is kept, not deleted, because this is a "for now" call: set
# ALGENT_PUBLISH_GATE=1 to restore hold-on-status once quality no longer needs the tight loop.
_GATE_ENV = "ALGENT_PUBLISH_GATE"


def _gate_enabled() -> bool:
    return os.environ.get(_GATE_ENV, "0").strip().lower() in ("1", "true", "yes", "on")

# Accusation-class language — the coarse signal for the OPTIONAL named-individual hold-lane. This is
# where defamation risk concentrates, so an operator can choose to route pieces that pair a named
# person with this language to a human glance even in full-auto. Deliberately conservative (errs
# toward holding); NOT a guarantee, and off by default.
_ACCUSATION = re.compile(
    r"\b(accus|alleg|fraud|guilt|convict|charg|indict|lied|lying|corrupt|scandal|misconduct|"
    r"crimina|embezzl|brib|launder|perjur|assault|abus|harass)\w*", re.IGNORECASE)


def named_individual_flag(profile: dict, article_md: str) -> str | None:
    """Coarse opt-in check: does the piece pair a named person (a profile 'person' entity) with
    accusation-class language? If so, return a hold reason. Conservative, not authoritative."""
    persons = [str(e.get("name", "")) for e in (profile.get("entities") or [])
               if str(e.get("type", "")).lower() == "person" and e.get("name")]
    if not persons or not _ACCUSATION.search(article_md):
        return None
    # Word-boundary match, not bare substring — a person named "Mark" must not match "marketplace"
    # and phantom-hold the piece (a chronic false-positive lane starves the site like an over-strict gate).
    hit = next((p for p in persons if re.search(rf"\b{re.escape(p)}\b", article_md, re.IGNORECASE)), None)
    return (f"names a person ({hit}) alongside accusation-class language — held for a human glance "
            "(named-individual lane)") if hit else None

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


def _load(art: Path, name: str) -> Any:
    f = art / name
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a malformed optional artifact must not sink the publish
        return None


def _read_run(run_dir: Path) -> tuple[str, dict, dict, dict, dict, list] | None:
    """Load (article_md, rail, pipeline, profile, vector, analytics) from a run dir. None if incomplete.

    Only the article + pipeline report are required; the rest enrich the frontmatter (the vector
    supplies pillars for topic tags, the analytics supply the thumbnail) and are optional so an
    editorial-only run still publishes.
    """
    art = run_dir / "artifacts"
    article = art / "article_published.md"
    pipeline = _load(art, "editorial_pipeline_report.json")
    if not article.exists() or not pipeline:
        return None
    return (article.read_text(encoding="utf-8"),
            _load(art, "newsroom_rail_report.json") or {},
            pipeline,
            _load(art, "profile.json") or {},
            _load(art, "selected_vector.json") or {},
            _load(art, "analytics_artifacts.json") or [])


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
    hold_named_individuals: bool = False,
) -> PublishResult:
    """Gate a finished run and stage/hold it. ``push`` (live ship, ON by default) is applied by the
    caller's git step; here it only distinguishes the recorded action (``staged`` vs ``published``)."""
    today = today or _today()
    loaded = _read_run(run_dir)
    if loaded is None:
        return PublishResult(action="error", reasons=["run has no article_published.md + pipeline report"])
    article_md, rail, pipeline, profile, vector, analytics = loaded

    status = str(pipeline.get("status") or "")
    title, _dek, _rest = parse_published_article(article_md)
    profile_id = str(pipeline.get("profile_id") or rail.get("profile_id") or "")
    slug = build_slug(title, profile_id)
    run_id = run_dir.name

    # ── the gate (OFF by default — see _gate_enabled) ─────────────────────────────────────────
    if _gate_enabled():
        if status == _BLOCKED:
            return _hold(held_dir, slug, status, ["status is blocked — dropped required evidence"],
                         run_id, rail, pipeline, action="blocked")
        if status != _PUBLISHABLE:
            # Name the lane that actually held it — a held piece is triaged by a human, and
            # "caveat lane did not pass" on a piece held for comprehension sends them looking
            # in the wrong place.
            why = {
                "needs_hedging": "the prose does not keep a promise the caveat pass flagged",
                "needs_ramp": "a general reader could not follow it, and the repair lap did not fix it",
                "needs_revision": "the body collapsed below publishable length",
            }.get(status, "it did not earn publishable")
            reason = f"status is '{status or 'unknown'}', not publishable — {why}"
            return _hold(held_dir, slug, status, [reason], run_id, rail, pipeline)
    if hold_named_individuals and (flag := named_individual_flag(profile, article_md)):
        return _hold(held_dir, slug, status, [flag], run_id, rail, pipeline)

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
                      date=today, run_id=run_id, corrections=corrections or None,
                      vector=vector, analytics=analytics,
                      hero=(pipeline.get("hero") or None))
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

_SVG_SCRIPT = re.compile(rb"<script[\s\S]*?</script\s*>", re.IGNORECASE)
_SVG_FOREIGN = re.compile(rb"<foreignObject[\s\S]*?</foreignObject\s*>", re.IGNORECASE)
_SVG_ON_ATTR = re.compile(rb"""\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_SVG_JS_HREF = re.compile(rb"""((?:xlink:)?href)\s*=\s*("|')\s*javascript:[^"']*\2""", re.IGNORECASE)


def _sanitize_svg(data: bytes) -> bytes:
    """Strip active content from an SVG. The site renders analytics via <img> (scripts never run
    there), but a grok-produced SVG served from our own origin could execute if opened DIRECTLY —
    so we neutralize scripts/handlers/foreignObject/javascript: at copy time. Defense in depth."""
    data = _SVG_SCRIPT.sub(b"", data)
    data = _SVG_FOREIGN.sub(b"", data)
    data = _SVG_ON_ATTR.sub(b"", data)
    return _SVG_JS_HREF.sub(rb'\1=\2#\2', data)


def _write_article(site_dir: Path, article: SiteArticle, run_dir: Path) -> None:
    content_path = site_dir / "content" / "articles" / f"{article.slug}.md"
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(article.markdown, encoding="utf-8")
    if article.assets:
        dest = site_dir / "public" / "analytics" / article.slug
        dest.mkdir(parents=True, exist_ok=True)
        for name in article.assets:
            src = run_dir / "artifacts" / name
            if not src.exists():
                continue
            data = src.read_bytes()
            (dest / name).write_bytes(_sanitize_svg(data) if name.lower().endswith(".svg") else data)


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
