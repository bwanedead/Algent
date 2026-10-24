"""The site's data as published documents (no database): the document store, name indexes, articles, and each domain's builder. Offline."""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone

import pytest

from algent_backend.geoledger import site_docs
from algent_backend.geoledger.contracts import Asset, StatusEvent, event_id
from algent_backend.geoledger.store import Ledger
from algent_backend.lookahead import publish as calendar_publish
from algent_backend.lookahead import store as calendar_store
from algent_backend.lookahead.contracts import CalendarItem
from algent_backend.maritime import publish as maritime_publish
from algent_backend.maritime import store as maritime_store
from algent_backend.maritime.contracts import BehaviourEvent
from algent_backend.publishing import object_docs, object_store, published_db, site_data
from algent_backend.sanctions import publish as sanctions_publish
from algent_backend.sanctions import store as sanctions_store
from algent_backend.sanctions.contracts import SanctionsEvent

R2 = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKID", "R2_SECRET_ACCESS_KEY": "sek", "R2_BUCKET": "ohmega", "R2_PUBLIC_BASE": "https://pub.example"}
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


class Bucket:
    """A fake R2: remembers every PUT by key."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts = 0

    def __call__(self, method, url, headers, body):
        key = url.split("/ohmega/", 1)[1]
        if method == "PUT":
            self.objects[key] = body
            self.puts += 1
        return 200, {}, b""

    def doc(self, path: str):
        return json.loads(gzip.decompress(self.objects[f"docs/{path}.gz"]))


@pytest.fixture
def bucket(monkeypatch, tmp_path):
    for k, v in R2.items():
        monkeypatch.setenv(k, v)
    b = Bucket()
    monkeypatch.setattr(object_store, "default_call", b)
    monkeypatch.setenv("ALGENT_MARITIME_STORE", str(tmp_path / "maritime"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    monkeypatch.setenv("ALGENT_SANCTIONS_STORE", str(tmp_path / "sanctions"))
    monkeypatch.setenv("ALGENT_CALENDAR_STORE", str(tmp_path / "calendar"))
    return b


# ── the document store ──────────────────────────────────────────────────────────────────────────
def test_documents_are_gzipped_at_docs_path_and_unchanged_ones_cost_no_request(bucket) -> None:
    docs = {"daily/geopolitics/2026-10-01.json": {"a": 1}, "record.json": {"b": [1, 2]}}
    out = published_db.publish_documents(docs)
    assert out["db"] is True and out["ok"] is True and out["documents"] == 2 and out["unchanged"] == 0
    assert bucket.doc("daily/geopolitics/2026-10-01.json") == {"a": 1, "schema": "ohmega.daily/1"}   # stamped with its contract
    puts = bucket.puts
    again = published_db.publish_documents(docs)
    assert again["documents"] == 0 and again["unchanged"] == 2 and bucket.puts == puts          # hash-skip: nothing sent, nothing read back
    changed = published_db.publish_documents({"record.json": {"b": [1, 2, 3]}})
    assert changed["documents"] == 1 and bucket.doc("record.json") == {"b": [1, 2, 3], "schema": "ohmega.record/1"}
    forced = published_db.publish_documents({"record.json": {"b": [1, 2, 3]}}, force=True)
    assert forced["documents"] == 1


def test_name_indexes_list_a_directory_without_listing_the_bucket(bucket) -> None:
    published_db.publish_documents({"daily/geopolitics/2026-10-01.json": {}, "daily/geopolitics/2026-10-02.json": {}, "daily/ai/2026-10-02.json": {}})
    assert bucket.doc("_names/daily/geopolitics.json") == ["2026-10-01.json", "2026-10-02.json"]
    assert bucket.doc("_names/daily/ai.json") == ["2026-10-02.json"]
    assert bucket.doc("_names/daily.json") == []                    # files directly in a dir only; sub-directories are their own index
    published_db.publish_documents({"daily/geopolitics/2026-10-03.json": {}})
    assert bucket.doc("_names/daily/geopolitics.json")[-1] == "2026-10-03.json"


def test_a_failed_upload_is_reported_and_retried(monkeypatch, bucket) -> None:
    ok = bucket.__call__
    monkeypatch.setattr(object_store, "default_call", lambda m, u, h, b: (500, {}, b"") if "bad" in u else ok(m, u, h, b))
    out = published_db.publish_documents({"ok/a.json": {"a": 1}, "bad/b.json": {"b": 1}})
    assert out["db"] is False and "failed" in out["note"] and out["documents"] == 1
    monkeypatch.setattr(object_store, "default_call", bucket)
    assert published_db.publish_documents({"ok/a.json": {"a": 1}, "bad/b.json": {"b": 1}})["documents"] == 1        # only the failed one is resent


def test_nothing_is_attempted_without_an_object_store(monkeypatch) -> None:
    for k in R2:
        monkeypatch.delenv(k, raising=False)
    out = published_db.publish_documents({"x.json": {}})
    assert out["db"] is False and "off" in out["note"]
    assert site_data.publish_built(lambda: (_ for _ in ()).throw(AssertionError("builder must not run")))["ok"] is False


def test_articles_publish_a_body_and_a_front_matter_index(bucket) -> None:
    md = "---\ntitle: Hello\ndek: d\npublished_at: '2026-10-01T10:00:00+00:00'\ntags: [a, b]\n---\n\nbody\n"
    out = published_db.publish_article("hello", md, title="Hello", status="publishable")
    assert out["db"] is True and out["articles"] == 1
    assert bucket.doc("articles/hello.json")["markdown"] == md
    idx = bucket.doc("articles/index.json")["articles"]
    assert idx[0]["slug"] == "hello" and idx[0]["data"]["tags"] == ["a", "b"] and "markdown" not in idx[0]
    published_db.publish_article("newer", md.replace("2026-10-01", "2026-10-05").replace("Hello", "Newer"))
    assert [a["slug"] for a in bucket.doc("articles/index.json")["articles"]] == ["newer", "hello"]          # newest first


# ── per-domain builders ─────────────────────────────────────────────────────────────────────────
def ev(i: int, kind="sts", ended=None, conf=0.5, imo="9074729", started="2026-10-21T08:00:00+00:00", **kw) -> BehaviourEvent:
    return BehaviourEvent(id=f"mb-{i}", kind=kind, mmsi=636092000 + i, name=f"SHIP {i}", imo=imo, started_at=started, ended_at=ended,
                          last_seen="2026-10-22T11:00:00+00:00", state="ended" if ended else "ongoing", area="Hormuz", confidence=conf,
                          summary=f"s{i}", evidence=[[k, 26.0, 56.0, 1.0, ""] for k in range(30)], **kw)


def test_maritime_documents_split_live_recent_counts_and_vessels(bucket) -> None:
    maritime_store.upsert([ev(1), ev(2, kind="ais_gap", ended="2026-10-10T00:00:00+00:00", imo=""), ev(3, ended="2026-10-21T22:00:00+00:00")], NOW.timestamp())
    docs = maritime_publish.documents(NOW)
    assert set(docs) == {"maritime/live.json", "maritime/recent.json", "maritime/counts.json", "maritime/vessel/9074729.json"}
    live = docs["maritime/live.json"]["events"]
    assert [e["id"] for e in live] == ["mb-1", "mb-3"] and all(len(e["evidence"]) == maritime_publish.EVIDENCE_LIVE for e in live)   # ended 12 days ago: not live
    recent = docs["maritime/recent.json"]["events"]
    assert [e["id"] for e in recent][0] == "mb-1" and len(recent) == 3 and len(recent[0]["evidence"]) == maritime_publish.EVIDENCE_RECENT
    assert docs["maritime/counts.json"] == {"total": 3, "ongoing": 1, "byKind": {"ais_gap": 1, "sts": 2, "identity": 0, "sanctioned": 0, "loiter": 0}}
    assert docs["maritime/live.json"]["events"][0]["active"] is True and docs["maritime/live.json"]["events"][0]["last_seen"]


def test_maritime_rows_are_stable_while_only_moving_parts_change(bucket) -> None:
    maritime_store.upsert([ev(1)], NOW.timestamp())
    first = maritime_publish.publish_files(NOW)
    assert first["ok"] is True
    puts = bucket.puts
    maritime_store.upsert([ev(1).model_copy(update={"last_seen": "2026-10-22T11:30:00+00:00", "evidence": [[99, 1.0, 2.0, 3.0, ""]]})], NOW.timestamp() + 300)
    again = maritime_publish.publish_files(datetime.fromtimestamp(NOW.timestamp() + 300, tz=timezone.utc))
    assert again["documents"] == 0 and bucket.puts == puts                     # last-heard and evidence moved; the documents did not
    maritime_store.upsert([ev(1).model_copy(update={"summary": "now different words"})], NOW.timestamp() + 600)
    changed = maritime_publish.publish_files(datetime.fromtimestamp(NOW.timestamp() + 600, tz=timezone.utc))
    assert changed["documents"] >= 2                                           # a change a reader sees is published at once


def sx(i: int, day: str, countries=("IR",), **kw) -> SanctionsEvent:
    base = dict(id=f"sx-{i}", source="ofac", action="designated", date=day, observed_on=day, ref=str(i), name=f"N{i}", type="entity",
                countries=list(countries), source_url="https://x")
    return SanctionsEvent(**{**base, **kw})


def test_sanctions_documents_hold_the_window_and_per_country_files(bucket) -> None:
    sanctions_store.append_events([sx(1, "2026-10-20"), sx(2, "2026-10-01", countries=("RU", "IR")), sx(3, "2025-01-01")])
    docs = sanctions_publish.documents(date(2026, 10, 22))
    rows = docs["sanctions/recent.json"]["rows"]
    assert [r["id"] for r in rows] == ["sx-1", "sx-2"] and rows[0]["on_date"] == "2026-10-20" and rows[0]["asset_id"] is None
    assert set(docs) == {"sanctions/recent.json", "sanctions/country/IR.json", "sanctions/country/RU.json"}
    assert [r["id"] for r in docs["sanctions/country/IR.json"]["rows"]] == ["sx-1", "sx-2"]
    out = sanctions_publish.publish(today=date(2026, 10, 22))
    assert out["ok"] is True and sanctions_store.published_count() == sanctions_store.line_count()          # the watermark still moves


def test_calendar_document_has_active_items_in_the_window_only(bucket) -> None:
    def item(i, day, **kw):
        return CalendarItem(id=f"c{i}", date=day, title=f"T{i}", kind="election", source="elections", source_url="https://x", **kw)

    calendar_store.sync("elections", [item(1, "2026-10-25"), item(2, "2026-10-01"), item(3, "2027-06-01"), item(4, "2026-10-23", countries=["US"])],
                        date(2026, 10, 22), withdraw=False)
    rows = calendar_publish.documents(date(2026, 10, 22))["calendar/next.json"]["items"]
    assert [r["id"] for r in rows] == ["c4", "c1"] and rows[0]["on_date"] == "2026-10-23" and rows[0]["end_date"] is None and rows[0]["countries"] == ["US"]


def plant(id_, name, country="UA", cap=None, lat=50.0, lon=30.0) -> Asset:
    return Asset(id=id_, name=name, type="power_plant", country=country, lat=lat, lon=lon, attrs={"capacity_mw": cap} if cap else {})


def test_geo_documents_cover_country_place_and_month_questions(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([plant("wri-1", "Alpha", cap=500), plant("wri-2", "Beta", cap=900), plant("wri-3", "Gamma", country="PL", lat=52.0, lon=21.0)])
    led.add_events([StatusEvent(id=event_id("wri-1", "2026-10-20", "reported_damaged", "Kyiv"), asset_id="wri-1", occurred_on="2026-10-20",
                                status="reported_damaged", claimant="Kyiv", sources=["https://example.org/a"])])
    docs = site_docs.documents(led)
    ua = docs["geo/c/UA.json"]["assets"]
    assert [a["id"] for a in ua] == ["wri-1", "wri-2"] and ua[0]["status"] == "reported_damaged" and ua[0]["events"] == 1 and isinstance(ua[0]["attrs"], dict)
    idx = {c["iso"]: c for c in docs["geo/countries.json"]["countries"]}
    assert idx["UA"]["n"] == 2 and idx["UA"]["n_events"] == 1 and idx["PL"]["bbox"] == [21.0, 52.0, 21.0, 52.0]
    assert [a["id"] for a in docs["geo/events-assets.json"]["assets"]] == ["wri-1"]
    page = docs["geo/a/wri-1.json"]
    assert page["asset"]["name"] == "Alpha" and page["events"][0]["asset_id"] == "wri-1" and "geo/a/wri-2.json" not in docs
    assert docs["geo/events/2026-10.json"]["events"][0]["status"] == "reported_damaged"


def test_live_event_rows_use_the_sites_column_names_and_keep_a_stable_updated_at(bucket) -> None:
    from algent_backend.live import publish as live_publish
    from algent_backend.live import store as live_store
    from algent_backend.live.contracts import LiveEvent

    live_store.write_events("usgs", [LiveEvent(id="q1", feed="usgs", kind="quake", title="M5", start="2026-10-22T10:00:00+00:00")])
    first = live_publish.event_rows()
    assert first[0]["starts_at"] == "2026-10-22T10:00:00+00:00" and first[0]["ends_at"] is None and "start" not in first[0]
    stamp = first[0]["updated_at"]
    assert live_publish.event_rows()[0]["updated_at"] == stamp                                    # unchanged content, unchanged stamp
    live_store.write_events("usgs", [LiveEvent(id="q1", feed="usgs", kind="quake", title="M5.1", start="2026-10-22T10:00:00+00:00")])
    assert live_publish.event_rows()[0]["title"] == "M5.1"
    assert live_publish.documents(with_stats=False)["live/events.json"]["events"][0]["id"] == "q1"


def test_stamped_rows_only_restamp_on_a_content_change(tmp_path) -> None:
    rows = [{"id": "a", "v": 1}]
    first = site_data.stamped("t", [dict(r) for r in rows], now="2026-10-22T00:00:00+00:00", held=tmp_path)
    again = site_data.stamped("t", [dict(r) for r in rows], now="2026-10-23T00:00:00+00:00", held=tmp_path)
    changed = site_data.stamped("t", [{"id": "a", "v": 2}], now="2026-10-24T00:00:00+00:00", held=tmp_path)
    assert first[0]["updated_at"] == again[0]["updated_at"] == "2026-10-22T00:00:00+00:00" and changed[0]["updated_at"] == "2026-10-24T00:00:00+00:00"


def test_the_objects_the_documents_use_stay_under_the_cap(bucket) -> None:
    assert object_docs.NAMES_DIR == "_names" and published_db.budget.STORAGE_OBJECT_BYTES >= 10 * 1024 * 1024
