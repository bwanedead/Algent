"""Tests for the site converter — a run's article -> a site content file (pure, deterministic)."""

from __future__ import annotations

import yaml

from algent_backend.publishing import converter as cv

# A miniature of the real article_published.md shape (title / dek / body / receipts).
_ARTICLE = """# U.S. says it will enforce a Hormuz port blockade, but legal authority remains contested
*CENTCOM's notice preserves transit for non-Iran destinations, yet the toll plan is unverified.*

The immediate reality is operational: CENTCOM said forces would begin a blockade.

![Implied outcome probabilities](analytic_ar_1.svg)

*Chart caption — AI-assisted analytic, built only from cited data.*

Markets reacted as a risk premium, not proof of a durable shock.

---
## How we know this — sources & verification
_The receipts._

**Sources**
- (primary) CENTCOM notice — https://centcom.mil/x  ·  _read in full_
"""

_RAIL = {"profile_id": "prof_rv1", "total_usd": 0.10096}
_PIPELINE = {
    "profile_id": "prof_rv1", "status": "needs_hedging", "draft_outcome": "grounded",
    "treatment_verdict": "needs_revision", "caveat_verdict": "needs_hedging", "caveat_findings": 6,
    "analytics_produced": 1, "analytics_escapes": 0, "barriers": [], "unverified_figures": [],
}
_PROFILE = {"id": "prof_rv1", "as_of": "2026-07-14"}


def _convert(**over):
    kw = dict(article_md=_ARTICLE, rail=_RAIL, pipeline=_PIPELINE, profile=_PROFILE,
              date="2026-07-15", run_id="run_abc")
    kw.update(over)
    return cv.convert(**kw)


def test_parse_splits_title_dek_and_rest() -> None:
    title, dek, rest = cv.parse_published_article(_ARTICLE)
    assert title.startswith("U.S. says it will enforce")
    assert dek.startswith("CENTCOM's notice") and not dek.startswith("*")
    assert "# U.S." not in rest and "*CENTCOM" not in rest      # title/dek lifted out
    assert rest.startswith("The immediate reality")             # body begins here
    assert "## How we know this" in rest                        # receipts carried for the site to split


def test_slug_is_stable_per_story_not_per_run() -> None:
    a = _convert()
    b = _convert(rail={**_RAIL})          # a different "run" of the same story (same profile id)
    assert a.slug == b.slug               # collides on purpose -> a re-run is a correction, not a dupe
    assert a.slug.endswith("-" + __import__("hashlib").sha1(b"prof_rv1").hexdigest()[:6])
    assert a.slug.startswith("u-s-says-it-will-enforce")


def test_frontmatter_carries_publish_date_and_as_of() -> None:
    art = _convert()
    fm = yaml.safe_load(art.markdown.split("---\n")[1])
    assert fm["date"] == "2026-07-15" and fm["as_of"] == "2026-07-14"   # published Y, reporting as of X
    assert fm["status"] == "needs_hedging"
    assert fm["title"].startswith("U.S. says") and fm["dek"].startswith("CENTCOM")
    # body follows the frontmatter and no longer carries the H1/dek
    assert "\nThe immediate reality" in art.markdown and "\n# U.S." not in art.markdown


def test_image_refs_rewritten_to_site_path_and_collected() -> None:
    art = _convert()
    assert art.assets == ["analytic_ar_1.svg"]
    assert f"](/analytics/{art.slug}/analytic_ar_1.svg)" in art.markdown
    assert "](analytic_ar_1.svg)" not in art.markdown          # the bare ref is gone


def test_digest_carries_channel_provenance_when_present() -> None:
    art = _convert(rail={**_RAIL, "pool_by_channel": {"gkg": 40, "x": 24}, "promoted_from": {"x": 4},
                         "x_searches": 1, "cost_by_stage": {"profile": 0.05, "editorial": 0.05},
                         "disposition": "needs_verification"})
    assert "pool: gkg=40, x=24" in art.digest
    assert "promoted_from: x=4" in art.digest
    assert "x_searches: 1" in art.digest
    assert "cost_by_stage:" in art.digest and "editorial=$0.0500" in art.digest
    assert "disposition: needs_verification" in art.digest


def test_digest_carries_the_floor_signals_and_cost() -> None:
    art = _convert()
    d = art.digest
    assert "status: needs_hedging" in d and "caveats: needs_hedging (6 findings)" in d
    assert "cost: ~$0.1010" in d and "run: run_abc" in d
    assert "mode: normal" in d
    assert "analytics: 1 produced, 0 escapes" in d


def test_digest_flags_barriers_and_unverified_figures() -> None:
    art = _convert(pipeline={**_PIPELINE, "barriers": ["src_a"], "unverified_figures": ["9.9%"]})
    assert "walled sources" in art.digest and "src_a" in art.digest
    assert "figures not matched to evidence: 9.9%" in art.digest


def test_frontmatter_is_valid_yaml_despite_punctuation_in_dek() -> None:
    # a dek with a colon + em-dash + apostrophe must not break the frontmatter
    tricky = "# T\n*A: B — the market's move.*\n\nBody.\n"
    art = _convert(article_md=tricky)
    fm = yaml.safe_load(art.markdown.split("---\n")[1])
    assert fm["dek"] == "A: B — the market's move."


def test_published_at_orders_same_day_pieces() -> None:
    # `date` is day-granular; two pieces published the same day (routine for a newsroom) tie on it,
    # leaving the feed in arbitrary order — which is exactly what shipped. published_at is the key
    # the index actually sorts on.
    fa = yaml.safe_load(_convert(published_at="2026-07-16T10:00:00+00:00").markdown.split("---\n")[1])
    fb = yaml.safe_load(_convert(published_at="2026-07-16T21:00:00+00:00").markdown.split("---\n")[1])
    assert fa["date"] == fb["date"]                  # same day -> `date` cannot order them
    assert fa["published_at"] < fb["published_at"]   # the real moment can


def test_hero_lands_in_frontmatter_and_is_copied_as_an_asset() -> None:
    """A generated hero is decoration: it ships beside the thumbnail, never replacing it."""
    hero = {"artifact_name": "hero.jpg", "alt": "an orca surfacing in coastal water",
            "hook": "Orcas caught taking a sunfish apart",
            "label": "AI-generated illustration — not a photograph of this story",
            "model": "gemini-3.1-flash-lite-image", "size": "1K", "estimated_usd": 0.0336}
    analytics = [{"status": "produced", "artifact_name": "analytic_a1.svg"}]

    art = cv.convert(article_md="# T\n*d*\n\nBody.\n", rail={}, pipeline={"profile_id": "p"},
                  profile={}, date="2026-07-25", analytics=analytics, hero=hero)

    assert "hero: /analytics/" in art.markdown and "hero.jpg" in art.markdown
    assert "Orcas caught taking a sunfish apart" in art.markdown
    assert "AI-generated illustration" in art.markdown      # the label travels with it
    assert "hero.jpg" in art.assets                          # and the file is copied to the site
    # The real figure remains the thumbnail — a chart from cited evidence beats an illustration.
    assert "analytic_a1.svg" in art.markdown


def test_no_hero_leaves_the_frontmatter_untouched() -> None:
    art = cv.convert(article_md="# T\n*d*\n\nBody.\n", rail={}, pipeline={"profile_id": "p"},
                  profile={}, date="2026-07-25")
    assert "hero:" not in art.markdown


def test_digest_carries_analytics_skips_and_surface_issues() -> None:
    art = _convert(pipeline={
        **_PIPELINE,
        "analytics_skipped": ["anx_02:soft_cap_skipped", "anx_03:source_unavailable"],
        "surface_issues": ["title/dek omit plain_subject ('Bronze Age script')"],
    })
    assert "analytics_skipped: anx_02:soft_cap_skipped, anx_03:source_unavailable" in art.digest
    assert "surface_issues: title/dek omit plain_subject" in art.digest


def test_quick_take_lifts_to_frontmatter_and_leaves_body() -> None:
    md = """# Ceuta crossings surge after a Spanish policy shift
*Spain's enclave faces a mass attempt from Morocco; whether the policy caused it remains open.*

## At a glance
- **What happened:** Thousands attempted to cross into Ceuta from Morocco.
- **Why it matters:** The surge pressures an EU border enclave and Spanish politics.
- **What remains uncertain:** Whether a recent Spanish rule change caused the attempt.

Crossings began after dawn near the border fence.

---
## How we know this — sources & verification
_The receipts._
"""
    art = _convert(article_md=md)
    fm = yaml.safe_load(art.markdown.split("---\n")[1])
    assert fm["quick_take"]["what_happened"].startswith("Thousands attempted")
    assert fm["quick_take"]["why_it_matters"].startswith("The surge pressures")
    assert fm["quick_take"]["what_is_uncertain"].startswith("Whether a recent")
    assert "## At a glance" not in art.markdown          # stripped so the site component owns it
    assert "Crossings began after dawn" in art.markdown

