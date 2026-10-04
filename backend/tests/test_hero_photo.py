"""A real photograph as the hero when the story centres on a real place — else generate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.editorial import hero_stage
from algent_backend.agent_system.agents.editorial.real_images import Candidate
from algent_backend.publishing.converter import convert


class _Artifacts:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_bytes(self, name: str, data: bytes, kind: str = "") -> None:
        (self.root / name).write_bytes(data)

    def write_json(self, name: str, payload: dict, kind: str = "") -> None:
        (self.root / name).write_text(json.dumps(payload), encoding="utf-8")


_NASA = Candidate(title="STS004 Strait of Hormuz.jpg", description="The strait from orbit",
                  license="Public domain", license_url="", artist="NASA", date="1982",
                  thumb_url="https://t/x.jpg",
                  page_url="https://commons.wikimedia.org/wiki/File:STS004.jpg",
                  width=4000, mime="image/jpeg")


def _never_generate(*_a: Any, **_k: Any) -> Any:
    raise AssertionError("a found photo must not also pay for a generated hero")


def test_a_real_place_gets_a_real_photo_hero(tmp_path: Path) -> None:
    asked: list[str] = []

    def find(query: str, subject: str):
        asked.append(query)
        return _NASA, b"\xff\xd8real", "shows the strait"

    hero = hero_stage.make_hero(
        {"image_subject": "tankers in a narrow strait", "image_photo_query": "Strait of Hormuz"},
        _Artifacts(tmp_path), generate=_never_generate, find_photo=find)
    assert asked == ["Strait of Hormuz"]
    assert hero["artifact_name"] == "photo_hero.jpg" and hero["kind"] == "photo"
    assert hero["label"] == "" and hero["credit"] == "Photo: NASA · Public domain · 1982"
    # The X announcement finds it through the record, not a hero.* glob.
    assert hero_stage.hero_file(tmp_path) == str(tmp_path / "photo_hero.jpg")


def test_no_query_or_no_fit_generates_as_before(tmp_path: Path) -> None:
    class _Img:
        data, model, size, estimated_usd = b"gen", "gemini-x-lite-image", "1K", 0.03

        def suffix(self) -> str:
            return ".jpg"

    miss = lambda q, s: (None, b"", "none fit")   # noqa: E731
    hero = hero_stage.make_hero(
        {"image_subject": "tankers in a narrow strait", "image_photo_query": "Strait of Hormuz"},
        _Artifacts(tmp_path), generate=lambda *_a, **_k: _Img(), find_photo=miss)
    assert hero["artifact_name"] == "hero.jpg" and hero["kind"] == "generated"
    assert hero_stage.hero_file(tmp_path) == str(tmp_path / "hero.jpg")


def test_the_photo_hero_carries_its_credit_to_the_page() -> None:
    article = convert(
        article_md="# A title\n*A dek.*\n\nBody text here.",
        rail={}, pipeline={}, profile={"id": "prof_x"}, date="2026-09-23", run_id="r",
        hero={"artifact_name": "photo_hero.jpg", "alt": "the strait", "label": "",
              "credit": "Photo: NASA · Public domain · 1982",
              "credit_url": "https://commons.wikimedia.org/wiki/File:STS004.jpg"})
    md = article.markdown if hasattr(article, "markdown") else str(article)
    assert "hero_credit" in md and "Photo: NASA" in md and "STS004.jpg" in md
