"""Tests for the publish orchestration — the floors-as-gate, held queue, corrections, retraction."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from algent_backend.publishing import publish as pb

_ARTICLE = ("# Fed holds, hike tail still live\n*A hold is the base case, but a hike is not off.*\n\n"
            "The committee held rates.\n\n---\n## How we know this — sources & verification\n_Receipts._\n")


def _run(tmp: Path, *, status="publishable", name="0001__abc", article=_ARTICLE, assets=None) -> Path:
    art = tmp / "runs" / name / "artifacts"
    art.mkdir(parents=True)
    (art / "article_published.md").write_text(article, encoding="utf-8")
    (art / "editorial_pipeline_report.json").write_text(json.dumps({
        "profile_id": "prof_x", "status": status, "draft_outcome": "grounded",
        "treatment_verdict": "promoted", "caveat_verdict": "verified", "caveat_findings": 0,
        "analytics_produced": 0, "analytics_escapes": 0, "barriers": [], "unverified_figures": [],
    }), encoding="utf-8")
    (art / "newsroom_rail_report.json").write_text(json.dumps(
        {"profile_id": "prof_x", "total_usd": 0.2314}), encoding="utf-8")
    (art / "profile.json").write_text(json.dumps({"id": "prof_x", "as_of": "2026-07-14"}), encoding="utf-8")
    for a in assets or []:
        (art / a).write_bytes(b"<svg/>")
    return art.parent


def _dirs(tmp: Path):
    return {"site_dir": tmp / "site", "held_dir": tmp / "held"}


def test_publishable_is_staged_when_push_off(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    r = pb.publish_run(_run(tmp_path), push=False, today="2026-07-15", **d)
    assert r.action == "staged"
    content = (d["site_dir"] / "content" / "articles" / f"{r.slug}.md")
    assert content.exists()
    fm = yaml.safe_load(content.read_text(encoding="utf-8").split("---\n")[1])
    assert fm["status"] == "publishable" and fm["date"] == "2026-07-15" and fm["as_of"] == "2026-07-14"
    ledger = (d["site_dir"] / "publish-ledger.md").read_text(encoding="utf-8")
    assert "staged; push paused" in ledger and "cost: ~$0.2314" in ledger


def test_publishable_is_published_when_push_on(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    r = pb.publish_run(_run(tmp_path), push=True, today="2026-07-15", **d)
    assert r.action == "published"
    assert "push paused" not in (d["site_dir"] / "publish-ledger.md").read_text(encoding="utf-8")


def test_needs_hedging_goes_to_held_queue_not_the_site(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    r = pb.publish_run(_run(tmp_path, status="needs_hedging"), today="2026-07-15", **d)
    assert r.action == "held" and "not publishable" in r.reasons[0]
    assert not (d["site_dir"] / "content" / "articles").exists()          # nothing on the site
    assert (d["held_dir"] / "held-ledger.md").exists()                    # recorded for the operator


def test_blocked_is_refused(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    r = pb.publish_run(_run(tmp_path, status="blocked"), today="2026-07-15", **d)
    assert r.action == "blocked"
    assert "HELD" not in (d["held_dir"] / "held-ledger.md").read_text(encoding="utf-8").split("\n")[0]


def test_assets_are_copied_into_the_site_public_dir(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    article = _ARTICLE.replace("The committee held rates.",
                               "The committee held rates.\n\n![Chart](analytic_c1.svg)")
    r = pb.publish_run(_run(tmp_path, article=article, assets=["analytic_c1.svg"]), today="2026-07-15", **d)
    asset = d["site_dir"] / "public" / "analytics" / r.slug / "analytic_c1.svg"
    assert asset.exists()
    content = (d["site_dir"] / "content" / "articles" / f"{r.slug}.md").read_text(encoding="utf-8")
    assert f"/analytics/{r.slug}/analytic_c1.svg" in content


def test_republish_without_correction_is_refused(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    pb.publish_run(_run(tmp_path, name="0001__a"), today="2026-07-15", **d)             # first publish
    r = pb.publish_run(_run(tmp_path, name="0002__b"), today="2026-07-16", **d)         # same story again
    assert r.action == "refused" and "--correction" in r.reasons[0]


def test_republish_with_correction_appends_a_visible_note(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    first = pb.publish_run(_run(tmp_path, name="0001__a"), today="2026-07-15", **d)
    r = pb.publish_run(_run(tmp_path, name="0002__b"), correction="fixed the rate figure",
                       today="2026-07-16", **d)
    assert r.action == "corrected" and r.slug == first.slug
    fm = yaml.safe_load((d["site_dir"] / "content" / "articles" / f"{r.slug}.md")
                        .read_text(encoding="utf-8").split("---\n")[1])
    assert fm["corrections"] == [{"date": "2026-07-16", "reason": "fixed the rate figure"}]


def test_retract_leaves_an_honest_tombstone(tmp_path: Path) -> None:
    d = _dirs(tmp_path)
    r0 = pb.publish_run(_run(tmp_path), today="2026-07-15", **d)
    r = pb.retract(r0.slug, "source turned out to be fabricated", site_dir=d["site_dir"], today="2026-07-20")
    assert r.action == "retracted"
    text = (d["site_dir"] / "content" / "articles" / f"{r0.slug}.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---\n")[1])
    assert fm["status"] == "retracted" and fm["retraction"]["reason"].startswith("source turned out")
    assert "retracted on 2026-07-20" in text.lower()
    assert "RETRACTED" in (d["site_dir"] / "publish-ledger.md").read_text(encoding="utf-8")


def test_missing_artifacts_is_a_clean_error(tmp_path: Path) -> None:
    empty = tmp_path / "runs" / "0009__x"
    (empty / "artifacts").mkdir(parents=True)
    r = pb.publish_run(empty, today="2026-07-15", **_dirs(tmp_path))
    assert r.action == "error"
