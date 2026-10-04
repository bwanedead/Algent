"""The free rescue ladder: jina -> wayback -> playwright (opt-in) -> firecrawl, with a read ledger."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.agent_system.tools.sourcing.depth import fetch_content as fc
from algent_backend.agent_system.tools.sourcing.depth import free_rungs, read_ledger

GOOD = " ".join(["substance"] * 200)
SHELL = "<html>shell</html>"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("ALGENT_FETCH_CACHE", "0")
    monkeypatch.delenv("ALGENT_FETCH_PLAYWRIGHT", raising=False)
    monkeypatch.setattr(fc, "_http_get", lambda url: SHELL)
    monkeypatch.setattr(fc, "_extract", lambda html: GOOD if "article" in html else "tiny")
    monkeypatch.setattr(fc, "_extract_meta", lambda html: {})
    monkeypatch.setattr(fc, "get_service_api_key", lambda svc: "fc-key")
    calls: list[str] = []
    monkeypatch.setattr(fc, "_jina_markdown", lambda u: calls.append("jina") or None)
    monkeypatch.setattr(fc, "_wayback_html", lambda u: calls.append("wayback") or None)
    monkeypatch.setattr(fc, "_playwright_html", lambda u: calls.append("playwright") or None)
    monkeypatch.setattr(fc, "_firecrawl_markdown", lambda u, k: calls.append("firecrawl") or GOOD)
    return calls


def _ledger() -> list[dict]:
    return [json.loads(x) for x in read_ledger.ledger_path().read_text().splitlines()]


def test_order_and_firecrawl_last(_offline, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "1")
    result = fc._fetch("https://a.test/x")
    assert _offline == ["jina", "wayback", "playwright", "firecrawl"]
    assert result["via"] == "firecrawl"


def test_jina_good_short_circuits(_offline, monkeypatch) -> None:
    monkeypatch.setattr(fc, "_jina_markdown", lambda u: GOOD)
    result = fc._fetch("https://a.test/x")
    assert result["via"] == "jina" and result["quality"] == "good"
    assert _offline == []  # nothing later ran


def test_jina_error_page_is_failure_not_content(monkeypatch) -> None:
    class Resp:
        status_code, text = 200, "Warning: Target URL returned error 403: Forbidden\n" + GOOD

    monkeypatch.setattr("httpx.get", lambda *a, **k: Resp())
    monkeypatch.setattr(free_rungs, "_JINA_MIN_INTERVAL_S", 0.0)
    assert free_rungs.jina_markdown("https://a.test/x") is None
    Resp.text = "Title: T\n\nURL Source: https://a.test/x\n\nWarning: cached.\n\nMarkdown Content:\nhello world"
    assert free_rungs.jina_markdown("https://a.test/x") == "hello world"


def test_jina_key_sent_as_bearer(monkeypatch) -> None:
    seen = {}

    class Resp:
        status_code, text = 200, "body"

    monkeypatch.setattr("httpx.get", lambda url, headers=None, **k: seen.update(h=headers) or Resp())
    monkeypatch.setattr(free_rungs, "_JINA_MIN_INTERVAL_S", 0.0)
    monkeypatch.setenv("ALGENT_JINA_KEY", "k123")
    free_rungs.jina_markdown("https://a.test/x")
    assert seen["h"]["Authorization"] == "Bearer k123"


def test_wayback_snapshot_reports_archived_at(_offline, monkeypatch) -> None:
    monkeypatch.setattr(fc, "_wayback_html", lambda u: ("<html>article</html>", "20240102030405"))
    result = fc._fetch("https://a.test/x")
    assert result["via"] == "wayback" and result["archived_at"] == "20240102030405"
    assert "2024-01-02" in result["hint"] and "firecrawl" not in _offline


def test_wayback_no_snapshot(monkeypatch) -> None:
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"archived_snapshots": {}}

    monkeypatch.setattr(free_rungs, "_WAYBACK_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr("httpx.get", lambda *a, **k: Resp())
    assert free_rungs.wayback_html("https://a.test/x") is None


def test_wayback_uses_raw_id_form(monkeypatch) -> None:
    urls = []

    class Resp:
        status_code, text = 200, "<html>old</html>"

        @staticmethod
        def json():
            return {"archived_snapshots": {"closest": {"available": True, "timestamp": "20230101000000"}}}

    monkeypatch.setattr(free_rungs, "_WAYBACK_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr("httpx.get", lambda url, **k: urls.append(url) or Resp())
    assert free_rungs.wayback_html("https://a.test/x") == ("<html>old</html>", "20230101000000")
    assert urls[-1] == "https://web.archive.org/web/20230101000000id_/https://a.test/x"


def test_paid_skipped_when_disallowed(_offline) -> None:
    result = fc._fetch("https://a.test/x", allow_paid_fallback=False)
    assert "firecrawl" not in _offline and result["quality"] != "good"


def test_not_found_short_circuits_and_is_logged(_offline, monkeypatch) -> None:
    def gone(url):
        raise fc.PageNotFound("nope")

    monkeypatch.setattr(fc, "_http_get", gone)
    assert fc._fetch("https://a.test/x")["not_found"] is True
    assert _offline == []
    assert _ledger()[-1]["not_found"] is True


def test_playwright_never_imported_when_env_off(_offline, monkeypatch) -> None:
    monkeypatch.setattr(fc, "_playwright_html", free_rungs.playwright_html)
    sys.modules.pop("playwright", None)
    fc._fetch("https://a.test/x", allow_paid_fallback=False)
    assert "playwright" not in sys.modules


def test_playwright_skipped_silently_when_not_importable(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    assert free_rungs.playwright_html("https://a.test/x") is None


def test_ledger_line_has_no_content_or_query(_offline) -> None:
    fc._fetch("https://News.A.test/secret/path?token=abc", allow_paid_fallback=False)
    raw = read_ledger.ledger_path().read_text()
    assert "token" not in raw and "secret" not in raw and "substance" not in raw
    row = _ledger()[-1]
    assert row["domain"] == "news.a.test" and row["rungs"][:3] == ["http", "jina", "wayback"]
    assert set(row) == {"ts", "domain", "via", "quality", "rungs", "ms", "not_found"}


def test_reads_summary_on_fixture_ledger(tmp_path) -> None:
    now = datetime.now(UTC)

    def row(domain, via, quality, rungs, nf=False, when=None):
        return {"ts": (when or now).isoformat(), "domain": domain, "via": via, "quality": quality,
                "rungs": rungs, "ms": 5, "not_found": nf}

    rows = [
        row("a.test", "trafilatura", "good", ["http"]),
        row("b.test", "jina", "good", ["http", "jina"]),
        row("c.test", "firecrawl", "good", ["http", "jina", "wayback", "firecrawl"]),
        row("w.test", "trafilatura", "thin", ["http"]),
        row("x.test", "none", "empty", ["http"], nf=True),
        row("old.test", "none", "empty", [], when=now - timedelta(days=30)),
    ]
    path = tmp_path / "l.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    s = read_ledger.summarise(7, path=path)
    assert s["reads"] == 5 and s["failure_rate"] == 0.4 and s["not_found"] == 1
    assert s["good_by_rung"] == {"trafilatura": 1, "jina": 1, "firecrawl": 1}
    assert s["rescued_only_by_paid_or_playwright"] == {"firecrawl": 1}
    assert s["top_failing_domains"] == [("w.test", 1)]


def test_reads_cli_prints_json(capsys) -> None:
    from algent_backend.cli.newsroom import reads

    class A:
        days = 7

    assert reads.run_reads(A()) == 0
    assert json.loads(capsys.readouterr().out)["reads"] == 0


def test_wayback_429_opens_the_breaker_and_stops_asking(monkeypatch) -> None:
    import httpx

    from algent_backend.agent_system.tools.sourcing.depth import free_rungs
    from algent_backend.agent_system.tools.sourcing.search import circuit

    circuit.reset()
    calls: list[str] = []

    class R:
        status_code = 429
        text = ""

        def json(self):
            return {}

    monkeypatch.setattr(free_rungs, "_pace", lambda *a, **k: None)
    monkeypatch.setattr(httpx, "get", lambda url, **k: calls.append(url) or R())
    assert free_rungs.wayback_html("https://example.org/a") is None
    assert circuit.is_open("wayback")
    assert free_rungs.wayback_html("https://example.org/b") is None
    assert len(calls) == 1                      # the second read never contacted archive.org
    circuit.reset()
