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
# Analytic image refs the publish view embeds, e.g. "![Chart](analytic_ar_1.svg)" or
# "![Theater](map_bab_el_mandeb.svg)". Tables are inline markdown (no asset); only real images
# (.svg/.png) with a relative filename (no path separators / absolute URLs) become files under
# the site's public/ dir.
_IMAGE_REF = re.compile(
    r"!\[([^\]]*)\]\(((?:analytic_|map_)[^)/]+\.(?:svg|png)|[^/)\s]+\.(?:svg|png))\)"
)
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
        f"analytics: {pipeline.get('analytics_produced', 0)} produced,"
        f" {pipeline.get('analytics_escapes', 0)} escapes",
        f"cost: ~${float(rail.get('total_usd', 0.0) or 0.0):.4f}"
        f"  ·  mode: {rail.get('budget_mode') or 'normal'}"
        f"  ·  soft/hard: ${float(rail.get('soft_cap_usd') or 1):.2f}"
        f"/${float(rail.get('hard_cap_usd') or 3):.2f}",
    ]
    if by_stage := rail.get("cost_by_stage"):
        parts = [f"{k}=${float(v):.4f}" for k, v in sorted(by_stage.items())]
        if parts:
            lines.append("cost_by_stage: " + ", ".join(parts))
    if rail.get("soft_cap_crossed"):
        lines.append(
            "soft_cap_crossed: yes"
            + (f" @ {rail['soft_crossed_at_stage']}" if rail.get("soft_crossed_at_stage") else "")
        )
    if rail.get("hard_stop"):
        lines.append(
            "hard_stop: yes"
            + (f" @ {rail['hard_stop_stage']}" if rail.get("hard_stop_stage") else "")
        )
    skipped = rail.get("skipped_operations") or []
    if skipped:
        lines.append(
            "skipped: " + ", ".join(
                f"{s.get('op', '?')}({s.get('reason', '')})" for s in skipped[:12]
            )
        )
    refused = rail.get("refused_operations") or []
    if refused:
        lines.append(
            "refused: " + ", ".join(
                f"{s.get('op', '?')}({s.get('reason', '')})" for s in refused[:12]
            )
        )
    if disp := rail.get("disposition"):
        lines.append(f"disposition: {disp}")
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


def _derived_frontmatter(profile: dict, vector: dict | None, pipeline: dict) -> dict:
    """Derived tags/places/flags, with the reviewer's rejected flags removed.

    Flags are assigned from the profile's declared geography, which is settled before anyone has
    read the finished article — so the only stage that can tell whether the prose accounts for a
    country is the comprehension reviewer, which reads both. Its removals are applied here.
    Places and flags are positionally paired, so they must be filtered together.
    """
    derived = derive_all(profile, vector)
    drop = {str(p).strip().casefold() for p in (pipeline.get("places_to_drop") or []) if p}
    if not drop:
        return derived

    places = list(derived.get("places") or [])
    flags = list(derived.get("flags") or [])
    kept = [(p, f) for p, f in zip(places, flags) if p.strip().casefold() not in drop]
    return {**derived,
            "places": [p for p, _ in kept],
            "flags": [f for _, f in kept]}


def convert(
    *, article_md: str, rail: dict, pipeline: dict, profile: dict,
    date: str, run_id: str = "", corrections: list[dict] | None = None,
    vector: dict | None = None, analytics: list[dict] | None = None,
    hero: dict | None = None, published_at: str | None = None,
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
        # Tags: derived. Places/flags: from agent countries_of_relevance only (see tagging.py),
        # minus anything the comprehension reviewer judged the finished prose does not earn.
        **{k: v for k, v in _derived_frontmatter(profile, vector, pipeline).items() if v},
    }
    # THUMBNAIL: a produced analytic is the best thumbnail this article can have — a real visual
    # built from the piece's own cited evidence, on-brand via the worker's spec, with zero
    # fabrication risk. Strictly better than a generated illustration, and it needs no AI-image
    # floor to ship. Articles without one fall back to their flags for visual texture.
    if thumb := next((a.get("artifact_name") for a in (analytics or [])
                      if a.get("status") == "produced"
                      and str(a.get("artifact_name", "")).endswith((".svg", ".png"))), None):
        fm["thumbnail"] = f"/analytics/{slug}/{thumb}"

    # HERO: a generated opening illustration, when the run made one. Kept separate from
    # `thumbnail` rather than replacing it — the thumbnail is a real figure built from cited
    # evidence and stays the honest default for anything that wants a picture of the piece's
    # *content*. The hero is decoration, so it carries its AI label everywhere it appears and
    # the surfaces choose which they want.
    hero_name = str((hero or {}).get("artifact_name") or "")
    if hero_name:
        fm["hero"] = f"/analytics/{slug}/{hero_name}"
        fm["hero_alt"] = str(hero.get("alt") or "")
        fm["hero_label"] = str(hero.get("label") or "")
        if hero.get("hook"):
            fm["hero_hook"] = str(hero["hook"])
        assets = [*assets, hero_name]
    if corrections:
        fm["corrections"] = corrections
    markdown = _frontmatter(fm) + "\n" + body + "\n"

    return SiteArticle(
        slug=slug, markdown=markdown, title=title, dek=dek, date=date,
        status=fm["status"], assets=assets,
        digest=quality_digest(rail, pipeline, run_id=run_id),
    )
