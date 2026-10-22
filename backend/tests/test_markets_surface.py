"""Markets surface: the daily's 'where we disagree' lines, the published track-record document, and the CLI wiring (fake HTTP, no network)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("legacy_supabase")

import json
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.markets import desk, publish, store
from algent_backend.markets.contracts import Forecast, Market, Snapshot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))


def seed_gap():
    store.save_markets([Market(id="a", question="Will A happen?", url="https://polymarket.com/event/a")])
    store.append_snapshots([Snapshot(market_id="a", at=T0.isoformat(), p=0.2)])
    store.append_forecast(Forecast(id="fc1", market_id="a", made_at=T0.isoformat(), p=0.6, rationale="r"))


def test_daily_view_is_labelled_mechanical_and_absent_without_a_gap():
    assert desk.daily_view(now_iso=T0.isoformat()) is None
    seed_gap()
    v = desk.daily_view(now_iso=(T0 + timedelta(hours=1)).isoformat())
    assert v and "not financial advice" in v["note"] and v["page"] == "/intel/track-record"
    assert "Our forecast 60%" in v["lines"][0]["text"] and "market prices it at 20%" in v["lines"][0]["text"]


def test_publish_sends_one_document_and_never_raises():
    import gzip

    index: list = []
    uploads: dict = {}

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, args=()):
            if sql.strip().startswith("insert"):
                index.append(args)
        def fetchall(self): return []

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return Cur()
        def commit(self): pass

    def http(method, url, headers, body):
        uploads[url.split("/published-assets/", 1)[1]] = body
        return 200

    seed_gap()
    out = publish.publish(connect=lambda: Conn(), http=http)
    doc = json.loads(gzip.decompress(uploads["docs/data/track-record.json.gz"]))
    assert out["db"] is True and index[0][0] == "data/track-record.json" and doc["paper_only"] is True and doc["forecasts"] == 1
    assert doc["disagreements"] == []                                                       # the 2026-10-01 forecast is long past DISAGREE_MAX_AGE_DAYS
    assert publish.publish(connect=lambda: (_ for _ in ()).throw(RuntimeError("down")), http=http)["db"] is False


def test_the_daily_record_carries_the_view_without_the_writers_seeing_it():
    # the attach point is the record builder, after sections exist: the module that builds writer prompts must not import markets
    import inspect

    from algent_backend.agent_system.agents.intel import daily, sensing

    assert "markets" not in inspect.getsource(sensing)
    src = inspect.getsource(daily)
    assert "markets_desk.daily_view()" in src and src.index("markets_desk.daily_view()") > src.index("calendar_extract.attach(")
