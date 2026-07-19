"""
The site converter — a finished run's article -> a site content file. Pure and deterministic.

The site (``sites/ohmega-monster``) already parses exactly what the editorial pipeline emits: a
markdown file with ``title/dek/date/status`` frontmatter, the body, and a ``## How we know this``
receipts section it splits out. This module does the format-map — no model, no IO, no git — so it
is trivially testable against a real run's artifacts. All side effects (file writes, asset copies,
git) live in ``publish.py``; this only turns strings into strings.

The slug is derived from STORY identity (title + profile id), not run identity, so a corrected
re-run of the same story lands on the same slug by construction — which is what makes "overwrite is
a visible correction, never a silent one" mechanically enforceable downstream.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import yaml

from .tagging import derive_all

# The receipts appendix heading the pipeline emits and the site splits on (substring-matched there).
_RECEIPTS_HEADING = "## How we know this"
# Analytic image refs the publish view embeds, e.g. "![Chart](analytic_ar_1.svg)". Tables are inline
# markdown (no asset); only real images (.svg/.png) become files under the site's public/ dir.
_IMAGE_REF = re.compile(r"!\[([^\]]*)\]\((analytic_[^)]+\.(?:svg|png))\)")
_SLUG_MAX_TITLE = 60


@dataclass
class SiteArticle:
    """The converted article, ready for ``publish.py`` to write + commit (or hold)."""

    slug: str
    markdown: str                                  # the full site content file (frontmatter + body + receipts)
    title: str
    dek: str
    date: str
    status: str
    assets: list[str] = field(default_factory=list)   # analytic image filenames to copy into public/analytics/<slug>/
    digest: str = ""                                   # the quality digest (commit message + ledger entry)


def parse_published_article(md: str) -> tuple[str, str, str]:
    """Split ``article_published.md`` into (title, dek, rest). ``rest`` is body + receipts verbatim.

    The reader-facing markdown is ``# Title`` / ``*dek*`` / body / ``---`` / ``## How we know this``.
    Title and dek move into frontmatter; everything from the first body line onward is carried as-is
    (the site itself splits the receipts at the heading).
    """
    lines = md.splitlines()
    title, dek, cut = "", "", 0
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            title = ln[2:].strip()
            cut = i + 1
            break
    j = cut
    while j < len(lines) and not lines[j].strip():   # skip blanks between title and dek
        j += 1
    if j < len(lines) and (s := lines[j].strip()).startswith("*") and s.endswith("*") and len(s) > 1:
        dek = s.strip("*").strip()
        cut = j + 1
    rest = "\n".join(lines[cut:]).strip()
    return title, dek, rest


def build_slug(title: str, profile_id: str) -> str:
    """``<kebab-title>-<6-hex of profile id>`` — stable per story, so a re-run collides on purpose."""
    kebab = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:_SLUG_MAX_TITLE].strip("-") or "article"
    h = hashlib.sha1((profile_id or "").encode("utf-8")).hexdigest()[:6]
    return f"{kebab}-{h}"


def rewrite_image_refs(body: str, slug: str) -> tuple[str, list[str]]:
    """Rewrite analytic image refs to the site's public path; return (body, asset filenames).

    ``![alt](analytic_x.svg)`` -> ``![alt](/analytics/<slug>/analytic_x.svg)``. The site renders these
    via <img> (which never executes an SVG's embedded scripts) — the ref rewrite keeps that contract.
    """
    assets: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        alt, name = m.group(1), m.group(2)
        assets.append(name)
        return f"![{alt}](/analytics/{slug}/{name})"

    return _IMAGE_REF.sub(_sub, body), list(dict.fromkeys(assets))


def quality_digest(rail: dict, pipeline: dict, *, run_id: str = "") -> str:
    """The quality digest — commit message + ledger entry. Everything the floors know, so the
    async monitoring surface (the ledger) shows what auto-published and how trustworthy it is."""
    barriers = pipeline.get("barriers") or []
    figs = pipeline.get("unverified_figures") or []
    lines = [
        f"status: {pipeline.get('status', '?')}  ·  draft: {pipeline.get('draft_outcome', '?')}"
        f"  ·  treatment: {pipeline.get('treatment_verdict', '?')}",
        f"caveats: {pipeline.get('caveat_verdict', '?')} ({pipeline.get('caveat_findings', 0)} findings)",
        f"analytics: {pipeline.get('analytics_produced', 0)} produced, {pipeline.get('analytics_escapes', 0)} escapes",
        f"cost: ~${float(rail.get('total_usd', 0.0) or 0.0):.4f}",
    ]
    # Discovery observability across runs: pool share vs what fed the winner (overfit signal).
    if pool := rail.get("pool_by_channel"):
        lines.append("pool: " + ", ".join(f"{k}={v}" for k, v in sorted(pool.items())))
    if promo := rail.get("promoted_from"):
        lines.append("promoted_from: " + ", ".join(f"{k}={v}" for k, v in sorted(promo.items())))
    if x := rail.get("x_searches"):
        lines.append(f"x_searches: {x}")
    if barriers:
        lines.append(f"⚠ walled sources (carried with caveats): {', '.join(barriers)}")
    if figs:
        lines.append(f"⚠ figures not matched to evidence: {', '.join(figs)}")
    if run_id:
        lines.append(f"run: {run_id}")
    return "\n".join(lines)


def _frontmatter(data: dict) -> str:
    """A YAML frontmatter block — safe-dumped so deks with colons/quotes/em-dashes can't break it."""
    body = yaml.safe_dump({k: v for k, v in data.items() if v not in (None, "", [])},
                          allow_unicode=True, sort_keys=False, default_flow_style=False, width=4096)
    return f"---\n{body}---\n"


def convert(
    *, article_md: str, rail: dict, pipeline: dict, profile: dict,
    date: str, run_id: str = "", corrections: list[dict] | None = None,
    vector: dict | None = None, analytics: list[dict] | None = None,
    published_at: str | None = None,
) -> SiteArticle:
    """Turn a run's artifacts into a ``SiteArticle``. Pure: strings in, ``SiteArticle`` out.

    ``date`` is the publish date (drives newest-first ordering); the story's ``as_of`` (recency of
    the facts) is carried separately so the page can say "reporting as of X · published Y".
    """
    title, dek, rest = parse_published_article(article_md)
    profile_id = str(pipeline.get("profile_id") or rail.get("profile_id") or "")
    slug = build_slug(title, profile_id)
    body, assets = rewrite_image_refs(rest, slug)

    fm: dict = {
        "title": title,
        "dek": dek,
        "date": date,
        # Full-precision publish moment. `date` is day-granular and cannot order two pieces
        # published the same day — which a newsroom does routinely, and which silently left the
        # feed in arbitrary order. This is what the index actually sorts on.
        "published_at": published_at or datetime.now(UTC).isoformat(),
        "as_of": str(profile.get("as_of") or ""),
        "status": str(pipeline.get("status") or ""),
        # Derived, never generated (see tagging.py) — categorisation that costs no model call and
        # cannot hallucinate. Also the substrate for tag+recency search later.
        **{k: v for k, v in derive_all(profile, vector).items() if v},
    }
    # THUMBNAIL: a produced analytic is the best thumbnail this article can have — a real visual
    # built from the piece's own cited evidence, on-brand via the worker's spec, with zero
    # fabrication risk. Strictly better than a generated illustration, and it needs no AI-image
    # floor to ship. Articles without one fall back to their flags for visual texture.
    if thumb := next((a.get("artifact_name") for a in (analytics or [])
                      if a.get("status") == "produced"
                      and str(a.get("artifact_name", "")).endswith((".svg", ".png"))), None):
        fm["thumbnail"] = f"/analytics/{slug}/{thumb}"
    if corrections:
        fm["corrections"] = corrections
    markdown = _frontmatter(fm) + "\n" + body + "\n"

    return SiteArticle(
        slug=slug, markdown=markdown, title=title, dek=dek, date=date,
        status=fm["status"], assets=assets,
        digest=quality_digest(rail, pipeline, run_id=run_id),
    )
