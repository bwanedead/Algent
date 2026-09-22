"""The daily roundup: the whole synthesis menu as one preliminary X post, once a day."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from algent_backend.agent_system.agents.briefing.compose import format_daily_roundup
from algent_backend.cli.newsroom import briefing as b
from algent_backend.publishing import briefing_queue as q

MENU = {"t0_ref": "t0x", "vectors": [
    {"title": "Fire amoeba", "thesis": "A Cascades amoeba survives record heat."},
    {"title": "Jumping genes", "thesis": "Transposons became partners in evolution."},
]}


def test_the_roundup_says_it_is_preliminary_and_carries_every_lead() -> None:
    text = format_daily_roundup(MENU, day="Tuesday, Sep 22")
    assert text.startswith("Preliminary news roundup — Tuesday, Sep 22")
    assert "before we've verified them" in text
    assert "• A Cascades amoeba survives record heat." in text
    assert "• Transposons became partners in evolution." in text


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(q, "PAUSE_FILE", tmp_path / "briefing.pause")
    monkeypatch.setattr(b, "write_configured", lambda: True)
    sent: list[str] = []

    class _Posted:
        url = "https://x.com/ohmegamonster/status/1"

    monkeypatch.setattr(b, "post", lambda text, **_: sent.append(text) or _Posted())
    return sent


def test_it_posts_once_a_day_not_once_per_menu(lane) -> None:
    now = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)
    first = b.post_daily_roundup(MENU, now=now)
    second = b.post_daily_roundup(MENU, now=now)
    assert first["posted"] is True and second["posted"] is False
    assert "already posted today" in second["reason"]
    assert len(lane) == 1


def test_a_paused_lane_posts_nothing(lane) -> None:
    q.request_pause()
    assert b.post_daily_roundup(MENU)["posted"] is False
    assert lane == []
