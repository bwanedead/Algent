"""Our own SearXNG answers first; paid engines are monthly-capped and refuse themselves once spent."""

from __future__ import annotations

from algent_backend.agent_system.tools.sourcing.search import circuit, quota, research, searxng


def test_searxng_leads_every_chain_and_free_engines_precede_paid_ones() -> None:
    paid = {"tavily", "brave", "exa", "muse"}
    for kind in ("keyword", "semantic", "news"):
        chain = research._provider_chain(kind)
        assert chain[0] in ("searxng", "gnews")
        free_positions = [i for i, p in enumerate(chain) if p in research._FREE_PROVIDERS]
        paid_positions = [i for i, p in enumerate(chain) if p in paid]
        if kind != "semantic":
            assert not paid_positions or max(free_positions) < min(paid_positions), kind


def test_parse_dedupes_keeps_dates_and_engines() -> None:
    payload = {"results": [
        {"url": "https://a.example/x", "title": "A", "content": "c", "engines": ["google", "duckduckgo"],
         "publishedDate": "2026-10-08T10:00:00"},
        {"url": "https://a.example/x", "title": "dup"},
        {"url": "https://b.example/y", "title": "B"},
        {"url": "", "title": "no url"},
    ]}
    rows = searxng.parse(payload, 5)
    assert [r["url"] for r in rows] == ["https://a.example/x", "https://b.example/y"]
    assert rows[0]["published"] == "2026-10-08" and rows[0]["engines"] == "google,duckduckgo"


def test_paid_engine_refuses_itself_once_the_month_is_spent(monkeypatch) -> None:
    monkeypatch.setitem(quota.MONTHLY_CAPS, "tavily", 2)
    assert quota.allow("tavily")
    quota.spend("tavily", 2)
    assert not quota.allow("tavily") and quota.summary()["tavily"] == {"used": 2, "cap": 2}


def test_the_chain_skips_a_capped_paid_engine_and_never_calls_it(monkeypatch) -> None:
    circuit.reset()
    monkeypatch.setitem(quota.MONTHLY_CAPS, "tavily", 0)
    called: list[str] = []

    def fake(provider, query, max_results):
        called.append(provider)
        if provider in ("searxng", "ddg", "bing"):
            raise RuntimeError("down")
        return [{"title": "t", "url": "https://x.example", "content": "c"}]

    monkeypatch.setattr(research, "_invoke_provider", fake)
    out = research._search_web("q", "keyword", 3)
    assert "tavily" not in called and called[:3] == ["searxng", "ddg", "bing"]
    assert any("tavily: monthly cap reached" in e for e in [out.get("error", "")] + [out.get("provider", "")]) \
        or out.get("provider") != "tavily"
    circuit.reset()
