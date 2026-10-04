"""Article figures as their own X posts — hero announce stays; charts are a second beat."""

from __future__ import annotations

import json

import pytest

from algent_backend.publishing import x_figures


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(x_figures, "LEDGER", tmp_path / "x_figures.jsonl")


def _run(tmp_path, *, raster: bool = True, title: str = "Russia needs China more"):
    arts = tmp_path / "artifacts"
    arts.mkdir(parents=True, exist_ok=True)
    png = arts / "analytic_vis_01.png"
    if raster:
        png.write_bytes(b"\x89PNG\r\n\x1a\n")
    (arts / "analytics_artifacts.json").write_text(json.dumps([{
        "request_id": "vis_01",
        "kind": "chart",
        "status": "produced",
        "title": title,
        "artifact_name": "analytic_vis_01.svg",
        "raster_name": "analytic_vis_01.png" if raster else "",
    }]), encoding="utf-8")
    return tmp_path


def test_figures_from_run_need_a_raster(tmp_path) -> None:
    assert x_figures.figures_from_run(_run(tmp_path / "with", raster=True))
    assert x_figures.figures_from_run(_run(tmp_path / "without", raster=False)) == []


def test_a_figure_is_never_posted_twice(tmp_path, monkeypatch) -> None:
    run = _run(tmp_path)
    sent: list[dict] = []

    class _Posted:
        def __init__(self, n: int):
            self.id = str(n)
            self.url = f"https://x.test/{n}"

    def fake_post(text, *, media_ids=None, reply_to=None, verify_identity=True):
        sent.append({"text": text, "media_ids": media_ids, "reply_to": reply_to})
        return _Posted(len(sent))

    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: True)
    monkeypatch.setattr(xc, "upload_media", lambda path: "media-1")
    monkeypatch.setattr(xc, "post", fake_post)

    first = x_figures.announce_figures("a-slug", run)
    assert first["posted"] == 1
    assert sent[0]["media_ids"] == ["media-1"]
    assert "Russia needs China" in sent[0]["text"]
    assert sent[0]["reply_to"] is None
    assert sent[1]["reply_to"] == "1"
    assert "ohmega.monster/articles/a-slug" in sent[1]["text"]

    second = x_figures.announce_figures("a-slug", run)
    assert second["posted"] == 0
    assert second["skipped"][0]["reason"] == "already posted"
    assert len(sent) == 2


def test_a_failed_reply_still_records_the_figure(tmp_path, monkeypatch) -> None:
    """A live chart plus a dead reply must not replay the chart on resume."""
    run = _run(tmp_path)
    n = {"i": 0}

    class _Posted:
        def __init__(self, i: int):
            self.id = str(i)
            self.url = f"https://x.test/{i}"

    def fake_post(text, *, media_ids=None, reply_to=None, verify_identity=True):
        n["i"] += 1
        if reply_to:
            from algent_backend.publishing.x_client import XWriteError
            raise XWriteError("reply refused")
        return _Posted(n["i"])

    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: True)
    monkeypatch.setattr(xc, "upload_media", lambda path: "media-1")
    monkeypatch.setattr(xc, "post", fake_post)

    first = x_figures.announce_figures("a-slug", run)
    assert first["posted"] == 1
    assert first["figures"][0]["reply_url"] == ""
    assert "reply failed" in first["skipped"][0]["reason"]

    second = x_figures.announce_figures("a-slug", run)
    assert second["posted"] == 0
    assert second["skipped"][0]["reason"] == "already posted"


def test_missing_credentials_are_reported_not_raised(monkeypatch, tmp_path) -> None:
    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: False)
    out = x_figures.announce_figures("s", _run(tmp_path))
    assert out["posted"] == 0 and "credentials" in out["reason"]
