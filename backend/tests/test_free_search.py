"""Free search tier (DDG keyword + Google News) and honest 404 reads. Offline: real fixtures, mocked HTTP."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.tools.sourcing.depth import fetch_content as fc
from algent_backend.agent_system.tools.sourcing.search import circuit, ddg, gnews, policy, research

FIXTURES = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text, self.status_code = text, status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    circuit.reset()
    monkeypatch.setattr(ddg, "_pace", lambda: None)
    yield
    circuit.reset()


def _ddg_html() -> str:
    return (FIXTURES / "ddg_html_sample.html").read_text(encoding="utf-8")


# -- ddg ----------------------------------------------------------------------------------------

def test_ddg_parses_real_page_and_decodes_uddg() -> None:
    hits = ddg.parse_results(_ddg_html())
    assert len(hits) >= 5
    assert all({"title", "url", "content"} <= set(h) for h in hits)
    assert hits[0]["url"].startswith("https://www.arabnews.com/")
    assert "duckduckgo.com" not in hits[0]["url"] and "%2F" not in hits[0]["url"]
    assert any("spa.gov.sa" in h["url"] for h in hits)
    assert hits[0]["content"]  # snippet text, markup stripped
    assert "<b>" not in hits[0]["content"]


def test_ddg_drops_ads_and_dedupes() -> None:
    ad = '<div class="result result--ad"><a class="result__a" href="//duckduckgo.com/y.js?ad=1">Buy</a></div>'
    y_js = '<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?x=1">Ad2</a></div>'
    dup = (
        '<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.test%2Fx">A</a></div>'
        '<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.test%2Fx&rut=9">A again</a></div>'
    )
    hits = ddg.parse_results(f"<html><body>{ad}{y_js}{dup}</body></html>")
    assert [h["url"] for h in hits] == ["https://a.test/x"]


def test_ddg_search_returns_hits_and_caps(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_ddg_html()))
    assert len(ddg.search("qatar houthi taif", max_results=3)) == 3


@pytest.mark.parametrize("status,body", [
    (202, "<html><body>nothing</body></html>"),
    (200, '<html><body><div class="anomaly-modal">Unfortunately, bots use DuckDuckGo too.</div></body></html>'),
])
def test_ddg_challenge_raises_rate_limit_and_trips_breaker(monkeypatch, status, body) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(body, status))
    with pytest.raises(RuntimeError, match="rate limit") as err:
        ddg.search("anything")
    assert circuit.record_failure("ddg", err.value) is True
    assert circuit.is_open("ddg")


def test_ddg_empty_without_challenge_is_just_empty(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp("<html><body>No results.</body></html>"))
    assert ddg.search("zzzxqv") == []


# -- gnews --------------------------------------------------------------------------------------

def _rss() -> str:
    return (FIXTURES / "gnews_rss_sample.xml").read_text(encoding="utf-8")


def test_gnews_parses_dated_outlet_items() -> None:
    items = gnews.parse_feed(_rss())
    assert len(items) >= 5
    first = items[0]
    assert first["outlet"] == "Al Jazeera" and first["outlet_url"].startswith("https://")
    assert first["published"] == "2026-09-17"
    assert not first["title"].endswith("Al Jazeera")  # outlet suffix stripped
    assert first["url"].startswith("https://news.google.com/rss/articles/") and first["resolved"] is False


def test_gnews_resolves_top_items_via_ddg_site_query(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_rss()))
    monkeypatch.setattr(gnews, "decode_via_google", lambda gid: None)
    queries: list[str] = []

    def fake_ddg(q, max_results=10):
        queries.append(q)
        host = q.rsplit("site:", 1)[1]
        # An off-domain hit first: must be skipped in favour of the outlet's own page.
        return [{"title": "x", "url": "https://other.test/a", "content": ""},
                {"title": "y", "url": f"https://www.{host}/real-article", "content": ""}]

    monkeypatch.setattr(ddg, "search", fake_ddg)
    items = gnews.search("houthi", max_results=8)
    assert len(queries) == gnews._RESOLVE_TOP and all("site:" in q for q in queries)
    assert [i["resolved"] for i in items[: gnews._RESOLVE_TOP]] == [True] * gnews._RESOLVE_TOP
    assert items[0]["url"].endswith("/real-article")
    assert items[gnews._RESOLVE_TOP]["resolved"] is False
    assert items[gnews._RESOLVE_TOP]["url"].startswith("https://news.google.com/")


def test_gnews_resolution_failure_keeps_headline(monkeypatch) -> None:
    from algent_backend.agent_system.tools.sourcing.search import bing

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_rss()))
    monkeypatch.setattr(gnews, "decode_via_google", lambda gid: None)
    monkeypatch.setattr(bing, "search", lambda q, max_results=10: [])
    calls: list[str] = []

    def boom(q, max_results=10):
        calls.append(q)
        raise RuntimeError("duckduckgo rate limit: challenge")

    monkeypatch.setattr(ddg, "search", boom)
    items = gnews.search("houthi")
    assert len(calls) == 1  # stopped after the block instead of hammering
    assert all(i["resolved"] is False for i in items)


# -- facade wiring ------------------------------------------------------------------------------

def test_chains() -> None:
    assert research._provider_chain("keyword") == ["ddg", "tavily", "brave", "exa", "bing", "muse"]
    sem = research._provider_chain("semantic")
    assert sem[:2] == ["exa", "ddg"] and sem[-2:] == ["bing", "muse"]
    assert research._provider_chain("news") == ["gnews", "ddg"]


def test_news_is_allowed_wherever_keyword_is() -> None:
    assert policy.channel_for_kind("news") == policy.KEYWORD
    assert policy.channel_for_kind("semantic") == policy.SEMANTIC
    token = policy.set_allowed([policy.KEYWORD, policy.READ])
    try:
        out = research._search(query="")  # reaches the empty-query guard, not a denial
        assert "permitted" not in out.get("error", "")
        assert "error" in research._search(query="", kind="news")
        assert "not permitted" not in research._search(query="", kind="news")["error"]
    finally:
        policy.reset_allowed(token)


def test_free_providers_never_touch_the_cost_meter(monkeypatch) -> None:
    def forbidden(*a, **k):
        raise AssertionError("free provider must not reserve cost")

    monkeypatch.setattr(cost, "try_reserve", forbidden)
    monkeypatch.setattr(cost, "settle", forbidden)
    monkeypatch.setattr(research, "_invoke_provider",
                        lambda p, q, n: [{"title": "t", "url": "https://x.test", "content": "c"}])
    for kind, provider in (("keyword", "ddg"), ("news", "gnews")):
        out = research._search_web("q", kind, 3)
        assert out["provider"] == provider and out["provider_style"]


def test_bing_is_free_and_answers_in_slim_mode_when_ddg_is_down(monkeypatch) -> None:
    assert "bing" in research._FREE_PROVIDERS and research._PROVIDER_STYLE["bing"]
    monkeypatch.setattr(cost, "is_slim", lambda: True)
    circuit.record_failure("ddg", "429 rate limit")

    def invoke(p, q, n):
        assert p == "bing", f"paid {p} must be skipped in slim mode"
        return [{"title": "t", "url": "u"}]

    monkeypatch.setattr(research, "_invoke_provider", invoke)
    assert research._search_web("q", "keyword", 3)["provider"] == "bing"


def test_free_provider_runs_even_in_slim_mode(monkeypatch) -> None:
    monkeypatch.setattr(cost, "is_slim", lambda: True)
    monkeypatch.setattr(research, "_invoke_provider", lambda p, q, n: [{"title": "t", "url": "u"}])
    assert research._search_web("q", "news", 3)["provider"] == "gnews"


def test_paid_fallback_is_still_metered(monkeypatch) -> None:
    reserved: list[str] = []
    monkeypatch.setattr(cost, "try_reserve", lambda unit, op="", **k: reserved.append(op) or object())
    monkeypatch.setattr(cost, "settle", lambda *a, **k: None)

    def invoke(p, q, n):
        if p == "ddg":
            raise RuntimeError("duckduckgo rate limit")
        return [{"title": "t", "url": "u"}]

    monkeypatch.setattr(research, "_invoke_provider", invoke)
    out = research._search_web("q", "keyword", 3)
    assert out["provider"] == "tavily" and out["fallback_from"] == "ddg"
    assert reserved == ["keyword"]  # tavily metered; the failed ddg attempt was not


def test_news_falls_through_to_ddg(monkeypatch) -> None:
    def invoke(p, q, n):
        if p == "gnews":
            raise RuntimeError("503")
        return [{"title": "t", "url": "u"}]

    monkeypatch.setattr(research, "_invoke_provider", invoke)
    assert research._search_web("q", "news", 3)["provider"] == "ddg"


def test_search_cache_keys_on_kind() -> None:
    from algent_backend.agent_system.foundation import read_cache

    assert read_cache.search_key("news", "q") != read_cache.search_key("keyword", "q")


def test_tool_description_teaches_news_site_and_no_guessing() -> None:
    desc = research._build().description
    assert "news" in desc and "site:domain" in desc and "never construct or guess" in desc


# -- honest reads -------------------------------------------------------------------------------

@pytest.mark.parametrize("status", [404, 410])
def test_404_is_not_found_with_no_paid_escalation(monkeypatch, status) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp("gone", status))
    monkeypatch.setattr(fc, "_cache_get", lambda url: None)
    monkeypatch.setattr(fc, "_firecrawl_markdown",
                        lambda *a, **k: pytest.fail("firecrawl must not run on a 404"))
    monkeypatch.setattr(fc, "get_service_api_key", lambda name: "key")
    out = fc._fetch("https://example.test/news/123456", allow_paid_fallback=True)
    assert out["not_found"] is True
    assert f"HTTP {status}" in out["error"] and "do not construct URLs" in out["error"]


def test_dns_failure_is_not_found(monkeypatch) -> None:
    def refuse(*a, **k):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(httpx, "get", refuse)
    monkeypatch.setattr(fc, "_cache_get", lambda url: None)
    out = fc._fetch("https://no-such-host.invalid/x", allow_paid_fallback=True)
    assert out["not_found"] is True and "DNS" in out["error"]


@pytest.mark.parametrize("url", [
    "https://webcache.googleusercontent.com/search?q=cache:example.com",
    "https://web.archive.org/web/*/example.com/*",
])
def test_dead_url_shapes_refused_without_a_fetch(monkeypatch, url) -> None:
    monkeypatch.setattr(fc, "_cache_get", lambda u: None)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("must not fetch"))
    out = fc._fetch(url, allow_paid_fallback=True)
    assert out["not_found"] is True and out["error"]


def test_read_surfaces_not_found_without_hints_or_spend(monkeypatch) -> None:
    monkeypatch.setattr(fc, "_fetch", lambda url, allow_paid_fallback=True: {
        "url": url, "error": "page does not exist (HTTP 404) — x", "not_found": True})
    monkeypatch.setattr(cost, "settle", lambda *a, **k: pytest.fail("no spend on 404"))
    for rich in (False, True):
        out = research._read("https://example.test/nope", rich=rich)
        assert out["not_found"] is True and "retry_hint" not in out and "barrier" not in out


# -- circuit escalation -------------------------------------------------------------------------

def test_circuit_cooldown_doubles_caps_and_resets(monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(circuit.time, "monotonic", lambda: now[0])
    waits = []
    for _ in range(8):
        circuit.record_failure("ddg", "rate limit")
        waits.append(circuit._open_until["ddg"] - now[0])
        now[0] += waits[-1] + 1  # cooldown elapsed; next probe fails again
    assert waits[:3] == [120.0, 240.0, 480.0]
    assert waits[-1] == 3600.0 and max(waits) == 3600.0
    circuit.record_success("ddg")
    circuit.record_failure("ddg", "rate limit")
    assert circuit._open_until["ddg"] - now[0] == 120.0


def test_circuit_ignores_soft_errors() -> None:
    assert circuit.record_failure("ddg", "connection reset") is False
    assert not circuit.is_open("ddg")


# -- bing ---------------------------------------------------------------------------------------

BING_RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>q</title>
<item><title>On site</title><link>https://www.spa.gov.sa/en/w1</link><description>&lt;b&gt;snip&lt;/b&gt; text</description></item>
<item><title>Junk</title><link>https://junk.test/x</link><description>d</description></item>
</channel></rss>"""


def test_bing_parses_and_filters_site_queries(monkeypatch) -> None:
    from algent_backend.agent_system.tools.sourcing.search import bing

    seen = {}
    monkeypatch.setattr(httpx, "get", lambda url, **k: seen.update(k) or _Resp(BING_RSS))
    plain = bing.search("qatar houthi")
    assert [h["url"] for h in plain] == ["https://www.spa.gov.sa/en/w1", "https://junk.test/x"]
    assert plain[0]["content"] == "snip text"
    filtered = bing.search("site:spa.gov.sa qatar houthi")
    assert [h["url"] for h in filtered] == ["https://www.spa.gov.sa/en/w1"]
    assert "site:" not in seen["params"]["q"]
    assert bing.search("site:nowhere.test x") == []


# -- google news link decoding ------------------------------------------------------------------

def test_gnews_decodes_embedded_old_format_ids() -> None:
    import base64

    raw = b"\x08\x13\x22\x18https://example.test/a/b-c\xd2\x01\x00"
    gid = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert gnews.decode_embedded(gid) == "https://example.test/a/b-c"
    assert gnews.decode_embedded("CBMiowFBVV95cUxPV3pvTmFWQ0RPVWxMUGFz") is None


def test_gnews_parses_batchexecute_reply() -> None:
    import json

    inner = json.dumps(["garturlreq", "https://www.aljazeera.com/news/x", 1])
    reply = ")]}'\n\n" + json.dumps([["wrb.fr", "Fbv4je", inner, None]])
    assert gnews.parse_batch_response(reply) == "https://www.aljazeera.com/news/x"
    assert gnews.parse_batch_response("garbage") is None


def test_gnews_prefers_decode_and_skips_title_search(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_rss()))
    monkeypatch.setattr(gnews, "decode_via_google", lambda gid: "https://real.test/story")
    monkeypatch.setattr(ddg, "search", lambda *a, **k: pytest.fail("title search not needed"))
    items = gnews.search("houthi")
    assert items[0]["resolved"] is True and items[0]["url"] == "https://real.test/story"


def test_gnews_decode_failure_falls_back_to_title_then_bing(monkeypatch) -> None:
    from algent_backend.agent_system.tools.sourcing.search import bing

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_rss()))
    monkeypatch.setattr(gnews, "decode_via_google", lambda gid: (_ for _ in ()).throw(RuntimeError("x")))

    def blocked(q, max_results=10):
        raise RuntimeError("duckduckgo rate limit")

    monkeypatch.setattr(ddg, "search", blocked)
    monkeypatch.setattr(bing, "search", lambda q, max_results=10: [
        {"title": "t", "url": "https://www." + q.rsplit("site:", 1)[1] + "/found", "content": ""}])
    items = gnews.search("houthi")
    assert items[0]["resolved"] is True and items[0]["url"].endswith("/found")
    assert circuit.is_open("ddg")
