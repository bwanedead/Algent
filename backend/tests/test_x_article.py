"""Announcing a published article on X — the half of publishing that was never automated."""

from __future__ import annotations

import json

import pytest

from algent_backend.publishing import x_article

# Bound before the autouse stub replaces the module attribute.
_WAIT = x_article.wait_until_live


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(x_article, "LEDGER", tmp_path / "x_announced.jsonl")
    # Announce tests are about posting, not Vercel. The wait is tested on its own.
    monkeypatch.setattr(x_article, "wait_until_live", lambda url, **k: True)


def test_an_article_is_never_announced_twice(monkeypatch) -> None:
    """Publishing is retryable and `resume` can run over the same article again.

    Without a ledger, every re-publish would post the same link — which looks like a bot
    stuck in a loop and cannot be undone once it is on the timeline.
    """
    sent: list[str] = []

    class _Posted:
        url = "https://x.test/1"

    monkeypatch.setattr(x_article, "compose", lambda *a, **k: "A finding.")
    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: True)
    monkeypatch.setattr(xc, "post", lambda text, **k: (sent.append(text), _Posted())[1])

    first = x_article.announce("a-slug", "A title", dek="A dek")
    assert first["announced"] is True and len(sent) == 1
    assert "https://www.ohmega.monster/articles/a-slug" in sent[0]

    second = x_article.announce("a-slug", "A title", dek="A dek")
    assert second["announced"] is False and second["reason"] == "already announced"
    assert len(sent) == 1

    row = json.loads(x_article.LEDGER.read_text(encoding="utf-8").splitlines()[0])
    assert row["slug"] == "a-slug" and row["post_url"] == "https://x.test/1"


def test_a_missing_credential_is_reported_not_raised(monkeypatch) -> None:
    """Distribution must never retroactively fail an article we already published."""
    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: False)
    out = x_article.announce("s", "T")
    assert out["announced"] is False and "credentials" in out["reason"]


def test_a_long_framing_line_is_not_clipped_to_a_card(monkeypatch) -> None:
    """400 characters used to trip a house 280 guard. The post is as long as it is."""
    sent: list[str] = []

    class _Posted:
        url = "https://x.test/2"

    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: True)
    monkeypatch.setattr(xc, "post", lambda text, **k: (sent.append(text), _Posted())[1])
    monkeypatch.setattr(x_article, "compose", lambda *a, **k: "x" * 400)

    out = x_article.announce("s2", "A short true title")
    assert out["announced"] is True
    assert sent[0].startswith("x" * 40)


def test_an_overlong_framing_line_falls_back_to_the_title(monkeypatch) -> None:
    """A clipped sentence reads as a broken post; a title is a complete thought by construction."""
    sent: list[str] = []

    class _Posted:
        url = "https://x.test/2"

    import algent_backend.publishing.x_client as xc
    from algent_backend.publishing.x_client import LIMIT

    monkeypatch.setattr(xc, "write_configured", lambda: True)
    monkeypatch.setattr(xc, "post", lambda text, **k: (sent.append(text), _Posted())[1])
    monkeypatch.setattr(x_article, "compose", lambda *a, **k: "x" * (LIMIT + 50))

    out = x_article.announce("s2b", "A short true title")
    assert out["announced"] is True
    assert sent[0].startswith("A short true title")


def test_compose_falls_back_to_the_title_when_the_model_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "algent_backend.agent_system.foundation.models.resolver.ModelResolver.resolve",
        lambda self, spec: (_ for _ in ()).throw(RuntimeError("no model")),
    )
    assert x_article.compose("The title", "the dek") == "The title"


def test_copy_from_draft_prefers_the_finding_over_the_topic() -> None:
    """The espresso-shot composer is only as good as the dek and gist it is given."""
    dek, gist = x_article.copy_from_draft({
        "title": "China's 3,500 GW target",
        "standfirst": "The plan is judged on grid integration, not gigawatts installed.",
        "quick_take": {
            "what_happened": "China pivoted from raw capacity to firm power.",
            "why_it_matters": "Installed gigawatts stopped being the scoreboard.",
            "what_is_uncertain": "Whether the grid can absorb the next 500 GW.",
        },
    })
    assert "grid integration" in dek
    assert "firm power" in gist
    assert "scoreboard" in gist


def test_copy_from_draft_is_empty_when_there_is_no_draft() -> None:
    assert x_article.copy_from_draft(None) == ("", "")
    assert x_article.copy_from_draft({}) == ("", "")


def test_a_page_without_a_large_image_card_is_not_ready() -> None:
    assert x_article.card_image_url("<html><title>nope</title></html>") == ""
    assert x_article.card_image_url(
        '<meta name="twitter:card" content="summary"/>'
        '<meta name="twitter:image" content="https://x.test/h.jpg"/>'
    ) == ""


def test_a_large_image_card_yields_the_hero_url() -> None:
    html = (
        '<meta name="twitter:card" content="summary_large_image"/>'
        '<meta name="twitter:image" content="https://x.test/hero.jpg"/>'
    )
    assert x_article.card_image_url(html) == "https://x.test/hero.jpg"


def test_announce_waits_until_the_card_is_live_before_posting(monkeypatch) -> None:
    """X crawls at post time. Pushing to site-live is not the same as the page being fetchable."""
    order: list[str] = []

    class _Posted:
        url = "https://x.test/3"

    import algent_backend.publishing.x_client as xc

    monkeypatch.setattr(xc, "write_configured", lambda: True)
    monkeypatch.setattr(xc, "post", lambda text, **k: (order.append("post"), _Posted())[1])
    monkeypatch.setattr(x_article, "compose", lambda *a, **k: "A finding.")
    monkeypatch.setattr(
        x_article, "wait_until_live",
        lambda url, **k: (order.append("wait"), True)[1],
    )

    out = x_article.announce("s3", "T")
    assert out["announced"] is True and out["card_ready"] is True
    assert order == ["wait", "post"]


def test_wait_until_live_polls_until_the_hero_returns_bytes() -> None:
    hits = {"page": 0, "img": 0}

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("/hero.jpg"):
            hits["img"] += 1
            if hits["img"] < 2:
                return 404, "", b""
            return 200, "", b"\xff\xd8jpeg"
        hits["page"] += 1
        if hits["page"] < 2:
            return 404, "not found", b""
        return 200, (
            '<meta name="twitter:card" content="summary_large_image"/>'
            '<meta name="twitter:image" content="https://x.test/hero.jpg"/>'
        ), b""

    slept: list[float] = []
    assert _WAIT(
        "https://x.test/articles/s",
        timeout_s=30, poll_s=1,
        sleep=slept.append, fetch=fetch,
    ) is True
    assert slept  # at least one 404 lap
    assert hits["page"] >= 2 and hits["img"] >= 2


def test_wait_until_live_times_out_rather_than_hanging() -> None:
    def fetch(_url: str) -> tuple[int, str, bytes]:
        return 404, "nope", b""

    assert _WAIT(
        "https://x.test/articles/s",
        timeout_s=0, poll_s=1,
        sleep=lambda _s: None, fetch=fetch,
    ) is False


def test_copy_from_run_reads_the_draft_artifact(tmp_path) -> None:
    arts = tmp_path / "artifacts"
    arts.mkdir()
    (arts / "draft.json").write_text(
        '{"standfirst": "a dek", "quick_take": {"what_happened": "a finding"}}',
        encoding="utf-8")
    assert x_article.copy_from_run(tmp_path) == ("a dek", "a finding")
    assert x_article.copy_from_run(tmp_path / "missing") == ("", "")


def test_a_post_can_carry_an_image_id(monkeypatch) -> None:
    """Briefings attach a collage via media_ids. The tweets body must actually include them."""
    import algent_backend.publishing.x_client as xc

    captured: dict = {}

    class _Resp:
        status_code = 201

        def json(self):
            return {"data": {"id": "99", "text": "hi"}}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(xc, "assert_identity", lambda: "ohmegamonster")
    monkeypatch.setattr("httpx.post", fake_post)
    out = xc.post("today's headlines on energy:\n", media_ids=["555"], verify_identity=True)
    assert out.id == "99"
    assert captured["json"]["media"]["media_ids"] == ["555"]


def test_the_write_ceiling_is_x_longform_not_a_classic_card() -> None:
    """A themed briefing will not fit on a 280-character card. That is not a reason to refuse it.

    280 was a house guard. X's tweets endpoint takes Premium long posts up to 25k; the
    timeline shows a preview and Show more. Articles (~100k) are a different UI product.
    """
    from algent_backend.publishing.x_client import CARD, LIMIT, billable_length

    cluster = "\n\n".join(f"(energy) Blurb {i}. " + ("x" * 200) for i in range(5))
    assert billable_length(cluster) > CARD
    assert billable_length(cluster) < LIMIT
