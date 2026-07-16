"""Tests for the publish kill switch + named-individual hold-lane (git plumbing stays behind the switch)."""

from __future__ import annotations

import json
from pathlib import Path

from algent_backend.publishing import publish as pb
from algent_backend.publishing import site_git


def test_kill_switch_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv("ALGENT_SITE_PUBLISH", raising=False)
    assert site_git.publish_enabled() is False
    monkeypatch.setenv("ALGENT_SITE_PUBLISH", "1")
    assert site_git.publish_enabled() is True
    monkeypatch.setenv("ALGENT_SITE_PUBLISH", "off")
    assert site_git.publish_enabled() is False


def test_named_individual_flag_triggers_on_person_plus_accusation() -> None:
    profile = {"entities": [{"name": "Jane Roe", "type": "person"}, {"name": "Acme Corp", "type": "org"}]}
    assert pb.named_individual_flag(profile, "Regulators allege Jane Roe committed fraud.") is not None
    # a person with no accusation language -> no hold
    assert pb.named_individual_flag(profile, "Jane Roe attended the summit.") is None
    # accusation language but no *person* entity present -> no hold (orgs aren't the defamation lane)
    org_only = {"entities": [{"name": "Acme Corp", "type": "org"}]}
    assert pb.named_individual_flag(org_only, "Acme Corp is accused of fraud.") is None
    # word-boundary match: a person named "Mark" must NOT hold on "marketplace fraud"
    mark = {"entities": [{"name": "Mark", "type": "person"}]}
    assert pb.named_individual_flag(mark, "The marketplace faced fraud allegations.") is None
    assert pb.named_individual_flag(mark, "Mark faces fraud allegations.") is not None


def _run(tmp: Path, article: str, entities: list) -> Path:
    art = tmp / "runs" / "0001__x" / "artifacts"
    art.mkdir(parents=True)
    (art / "article_published.md").write_text(article, encoding="utf-8")
    (art / "editorial_pipeline_report.json").write_text(json.dumps(
        {"profile_id": "prof_x", "status": "publishable", "caveat_verdict": "verified"}), encoding="utf-8")
    (art / "newsroom_rail_report.json").write_text(json.dumps({"total_usd": 0.1}), encoding="utf-8")
    (art / "profile.json").write_text(json.dumps({"id": "prof_x", "entities": entities}), encoding="utf-8")
    return art.parent


def test_named_individual_lane_holds_a_publishable_piece(tmp_path: Path) -> None:
    article = "# X\n*dek*\n\nProsecutors allege John Doe embezzled funds.\n\n## How we know this\n_r_\n"
    run = _run(tmp_path, article, [{"name": "John Doe", "type": "person"}])
    # off by default: publishes despite the accusation (the caveat floor already vetted it)
    off = pb.publish_run(run, site_dir=tmp_path / "s1", held_dir=tmp_path / "h1", today="2026-07-15")
    assert off.action == "staged"
    # opted in: the same piece holds for a human glance
    on = pb.publish_run(run, site_dir=tmp_path / "s2", held_dir=tmp_path / "h2",
                        today="2026-07-15", hold_named_individuals=True)
    assert on.action == "held" and "named-individual lane" in on.reasons[0]
