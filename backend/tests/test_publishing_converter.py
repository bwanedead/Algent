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
                         "x_searches": 1})
    assert "pool: gkg=40, x=24" in art.digest
    assert "promoted_from: x=4" in art.digest
    assert "x_searches: 1" in art.digest


def test_digest_carries_the_floor_signals_and_cost() -> None:
    art = _convert()
    d = art.digest
    assert "status: needs_hedging" in d and "caveats: needs_hedging (6 findings)" in d
    assert "cost: ~$0.1010" in d and "run: run_abc" in d
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
