"""A small, realistic published record for the view builders: two geopolitics dailies, an AI daily, theaters with dossiers, actor pages, a snapshot, the
record ledger, and the table products' documents. No network, no stores: ``context()`` hands a ViewContext over dictionaries."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.corpus import link, schema
from algent_backend.corpus.query import Corpus
from algent_backend.corpus.sink import Sink
from algent_backend.views.context import ViewContext
from algent_backend.views.sources import DictStaged, Tables

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
TODAY = "2026-10-23"


def pulse(pid: str, name: str, isos: list[str], position: float = 60.0, band: str = "severe") -> dict[str, Any]:
    return {"id": pid, "name": name, "title": f"{name} title", "actors_iso2": isos, "position": position, "band": band, "change_24h": 1.0, "change_7d": 4.0}


def section(tid: str, name: str, *, heat: float = 10.0, direction: str = "rising", isos: tuple[str, ...] = ("IR", "US"), n_dev: int = 2, visuals: int = 1,
            headline: str = "", map_bytes: int = 0, kind: str = "section", edition: int = 1) -> dict[str, Any]:
    devs = [{"headline": f"{name} development {i + 1}", "detail": f"Iran and the United States traded warnings over oil tankers {i}.", "when": "2026-10-23", "where": "Tehran",
             "actors": ["Iran", "United States"], "place": {"name": "Tehran", "country": "Iran", "lat": 35.7, "lon": 51.4}, "statements": [], "significance": "It matters.",
             "verification": "researched", "sources": [f"https://example.org/{tid}/{i}"]} for i in range(n_dev)]
    out: dict[str, Any] = {
        "theater_id": tid, "name": name, "kind": kind, "edition": edition, "temperature": {"heat": heat, "trend": "heating", "coverage": "rising", "recent_share": 0.1, "prior_share": 0.05},
        "escalation": {"direction": direction, "pace": "fast"}, "pulses": [pulse(f"pls_{tid}", f"{name} flow", list(isos))], "headline": headline or f"{name}: the strait stays closed",
        "bottom_line": f"{name} bottom line. " + "More words. " * 30, "since_yesterday": [], "developments": devs, "outlook": "Closure persists.", "watch_next": ["talks"],
        "visuals": [{"id": f"v{i}", "kind": "chart", "title": f"Chart {i}", "caption": "c", "asset": f"/analytics/daily/geopolitics/2026-10-23/v{i}.png"} for i in range(visuals)],
        "numbers": {"as_of": TODAY, "trackers": [{"id": "chk_hormuz_transits", "name": "Hormuz transits", "value": 80.0, "unit": "ships", "changes": {}, "spark": [1, 2, 3]}],
                    "actors": [{"iso2": isos[0], "name": "Iran"}]},
        "map": {"bbox": [50, 24, 60, 30], "points": [{"x": 1, "y": 2, "label": "Tehran", "date": TODAY, "verification": "researched", "n": 1}], "pad": "x" * map_bytes},
        "on_record": [], "updates": [], "key_figures": [],
    }
    return out


def daily(domain: str, date: str, sections: list[dict[str, Any]], headline: str = "Hormuz stays shut") -> dict[str, Any]:
    return {"schema": "ohmega.daily/1", "domain": domain, "date": date, "built_at": f"{date}T06:00:00+00:00", "researched": True,
            "summary": {"headline": headline, "the_day": ["Iran held the strait."]},
            "editions": [{"n": 1, "label": "Part 1", "cycle": "Asia", "built_at": f"{date}T05:30:00+00:00"}], "theaters": sections}


def actor(iso: str, name: str, gdp: float, theaters: list[tuple[str, int]], statements: int = 1) -> dict[str, Any]:
    f = lambda fid, label, v, unit="usd": {"id": fid, "label": label, "unit": unit, "value": v, "year": 2024, "source": "wb", "group": "economy"}   # noqa: E731
    return {"schema": "ohmega.actor/1", "iso2": iso, "name": name, "region": "Middle East", "capital": "Capital", "data_as_of": TODAY,
            "headline": [{**f("gdp", "GDP", gdp), "rank": 1, "of": 100, "percentile": 99}],
            "groups": {"people": [f("population", "Population", gdp / 1000, "people")], "economy": [f("gdp", "GDP", gdp), f("gdp_pc", "GDP per person", gdp / 5000)],
                       "trade": [], "energy": [], "military": [f("milex", "Military spending", gdp / 40)]},
            "energy_role": {"surplus": [], "deficit": []}, "leadership": {"head_of_state": {"name": f"{name} Leader", "since": "2020"}, "head_of_government": None, "as_of": TODAY, "nuclear": None},
            "statements": [{"id": f"st_{iso}_{i}", "speaker": "Official", "role": "Minister", "date": TODAY, "text": "We will respond.", "is_quote": True, "signal": "threat", "stance": -1,
                            "source_url": "https://example.org/s"} for i in range(statements)],
            "involved": {"theaters": [{"id": t, "name": t, "mentions": m} for t, m in theaters], "pulses": [{"id": "pls_thr_hormuz", "name": "flow", "band": "severe", "position": 60.0, "theater_id": "thr_hormuz"}]},
            "credits": []}


def dossier_row(tid: str, name: str, domain: str = "geopolitics", direction: str = "rising", last_seen: str = TODAY, days: int = 5, **kw: Any) -> dict[str, Any]:
    return {"theater_id": tid, "name": name, "domain": domain, "first_seen": "2026-10-01", "last_seen": last_seen, "days_covered": days, "heat": 10, "coverage": "rising",
            "escalation_direction": direction, "max_band": "severe", "state": kw.get("state", ""), "last_novel": last_seen, "parent_id": "", "merged_into": kw.get("merged_into", "")}


def dossier(tid: str, name: str, domain: str = "geopolitics") -> dict[str, Any]:
    return {"theater_id": tid, "name": name, "domain": domain, "built_at": f"{TODAY}T06:00:00+00:00", "first_seen": "2026-10-01", "last_seen": TODAY, "days_covered": 5,
            "current": {"date": TODAY, "bottom_line": "Bottom line.", "headline": "Head"}, "pulses": [{"id": f"pls_{tid}", "name": f"{name} flow", "situation": name, "position": 60.0, "band": "severe",
                                                                                               "history": [{"at": "2026-10-20T00:00:00+00:00", "position": 55.0}]}],
            "escalation_history": [{"date": f"2026-10-{d}", "direction": "rising", "pace": "fast"} for d in range(1, 24)],
            "coverage_series": [{"day": f"2026-10-{d:02d}", "count": d, "editions": 1} for d in range(1, 24)],
            "actors": [{"name": "Iran", "mentions": 9, "first": "2026-10-01", "last": TODAY}], "places": [{"name": "Tehran", "country": "Iran", "count": 3, "last_date": TODAY}],
            "briefs": [{"slug": "b1", "title": "Brief", "as_of": TODAY, "url": "/intel/briefs/b1"}], "map": None}


def snapshot() -> dict[str, Any]:
    return {"slug": "2026-10-23-0600", "built_at": f"{TODAY}T06:00:00+00:00",
            "situations": [{"id": "sit_hormuz", "title": "Hormuz", "summary": "s", "domain": "geopolitics", "watches": [],
                            "pulses": [{**pulse("pls_thr_hormuz", "Hormuz flow", ["IR"]), "velocity_7d": 6.0, "history": [{"at": f"2026-10-{d}T00:00:00+00:00", "position": 50.0 + d} for d in range(10, 23)]},
                                       {**pulse("pls_thr_chips", "Chips", ["CN"], 30.0, "elevated"), "velocity_7d": -2.0, "history": [{"at": "2026-10-20T00:00:00+00:00", "position": 31.0},
                                                                                                                                  {"at": "2026-10-22T00:00:00+00:00", "position": 30.0}]}]}],
            "theaters": [{"id": "thr_hormuz", "name": "Hormuz crisis", "series": [{"day": f"2026-10-{d:02d}", "count": d} for d in range(10, 24)]}], "daily": [], "briefs": [], "forecasts": {}}


def record() -> dict[str, Any]:
    st = lambda i, iso, about: {"id": f"s{i}", "speaker": "A", "role": "Minister", "affiliation": "x", "iso2": iso, "date": TODAY, "quote": "q", "paraphrase": "", "about": [], "about_iso2": about,   # noqa: E731
                                "signal": "threat", "stance": -1, "significance": "", "url": "https://example.org"}
    return {"schema": "ohmega.record/1", "window_days": 60, "as_of": TODAY, "count": 3, "total": 3, "statements": [st(1, "IR", ["US"]), st(2, "US", ["IR"]), st(3, "IR", [])]}


def tables() -> Tables:
    return Tables(docs={
        "sanctions/recent.json": {"rows": [{"id": "sx1", "source": "ofac", "action": "designated", "on_date": "2026-10-20", "observed_on": "2026-10-21", "name": "MAR AZUL", "type": "vessel",
                                            "countries": ["IR"], "programmes": ["IRAN"], "source_url": "https://ofac.treasury.gov/"}]},
        "sanctions/country/IR.json": {"rows": [{"id": "sx1", "source": "ofac", "action": "designated", "on_date": "2026-10-20", "observed_on": "2026-10-21", "name": "MAR AZUL", "type": "vessel",
                                                "countries": ["IR"], "programmes": ["IRAN"], "source_url": "https://ofac.treasury.gov/"}]},
        "calendar/next.json": {"items": [{"id": "c1", "on_date": "2026-10-28", "end_date": None, "title": "Gulf summit", "kind": "summit", "countries": ["IR", "SA"], "theaters": [], "source": "official",
                                          "source_url": "https://example.org/summit", "confidence": "high", "provenance": "aggregated", "via": "", "active": True}]},
        "geo/grid/IR.json": {"iso": "IR", "as_of": TODAY, "line": "Grid down 12% in 30 days.", "windows": {"7": {}, "30": {}}, "installed": {}},
        "live/anomalies.json": {"anomalies": [{"id": "an1", "sentence": "Tankers above normal", "countries": ["IR"], "active": True, "series": "ship.tanker.hormuz", "direction": "above", "confidence": 0.8,
                                               "starts_at": f"{TODAY}T01:00:00+00:00", "ends_at": None, "last_seen": f"{TODAY}T11:00:00+00:00"}]},
        "data/track-record.json": {"as_of": TODAY, "trader": {"limits": {"bankroll": 1000}, "summary": {"equity": 1010, "pnl": 10, "open": 1},
                                                              "curve": [{"day": "2026-10-22", "flat": 1000, "trader": 1005}, {"day": TODAY, "flat": 1000, "trader": 1010}],
                                                              "open_positions": [{"question": "Q?", "side": "yes", "pnl": 5, "value": 50, "url": "https://polymarket.com/x"}]}}})


def staged(extra: dict[str, Any] | None = None) -> DictStaged:
    docs: dict[str, Any] = {
        "daily/geopolitics/2026-10-22.json": daily("geopolitics", "2026-10-22", [section("thr_hormuz", "Hormuz crisis", heat=12), section("thr_taiwan", "Taiwan strait", heat=5, direction="steady", isos=("CN", "US"))]),
        "daily/geopolitics/2026-10-23.json": daily("geopolitics", "2026-10-23", [section("thr_hormuz", "Hormuz crisis", heat=14), section("thr_taiwan", "Taiwan strait", heat=6, direction="steady", isos=("CN", "US")),
                                                                              section("thr_hormuz", "Hormuz update", kind="update", edition=2)]),
        "daily/ai/2026-10-23.json": daily("ai", "2026-10-23", [section("thr_chips", "Chip export war", isos=("CN", "US"))], "Chips war"),
        "theaters/index.json": {"theaters": [dossier_row("thr_hormuz", "Hormuz crisis"), dossier_row("thr_taiwan", "Taiwan strait", direction="steady", state="quiet", last_seen="2026-10-01"),
                                             dossier_row("thr_chips", "Chip export war", domain="ai"), dossier_row("thr_old", "Old story", merged_into="thr_hormuz"),
                                             dossier_row("thr_spot_x", "One-off", days=1)]},
        "theaters/thr_hormuz.json": dossier("thr_hormuz", "Hormuz crisis"), "theaters/thr_taiwan.json": dossier("thr_taiwan", "Taiwan strait"),
        "theaters/thr_chips.json": dossier("thr_chips", "Chip export war", "ai"), "theaters/thr_old.json": dossier("thr_old", "Old story"), "theaters/thr_spot_x.json": dossier("thr_spot_x", "One-off"),
        "actors/IR.json": actor("IR", "Iran", 4e11, [("thr_hormuz", 9)]), "actors/US.json": actor("US", "United States", 2.5e13, [("thr_hormuz", 5), ("thr_taiwan", 4)]),
        "actors/CN.json": actor("CN", "China", 1.8e13, [("thr_taiwan", 7)]), "actors/SA.json": actor("SA", "Saudi Arabia", 1.1e12, [("thr_hormuz", 2)]),
        "actors/FR.json": actor("FR", "France", 3e12, []), "actors/DE.json": actor("DE", "Germany", 4e12, []),
        "snapshots/2026-10-23-0600.json": snapshot(), "record.json": record()}
    docs.update(extra or {})
    return DictStaged(docs)


def corpus(tmp_path: Path) -> Corpus:
    """A tiny corpus index: Iran (country), a person, an org, a geoledger asset with a status event, and a few documents mentioning them."""
    conn = schema.connect(tmp_path / "corpus.db", write=True)
    conn.isolation_level = None
    schema.create(conn, fts=False)
    now = NOW.isoformat()
    reg = Sink(conn, "actors", "registry", now)
    reg.declare("country:IR", "country", "Iran", iso2="IR", rank=0)
    reg.declare("country:US", "country", "United States", aliases=["USA"], iso2="US", rank=0)
    reg.declare("country:FR", "country", "France", iso2="FR", rank=0)
    reg.observation("gdp", "2024", 4e11, entity="country:IR", unit="usd", basis="official", label="GDP")
    reg.observation("gdp", "2023", 3.9e11, entity="country:IR", unit="usd", basis="official", label="GDP")
    reg.relation("head_of_state", src="country:IR", dst="person:iran-leader", date="2020")
    p = Sink(conn, "profiles", "profile:p1", now)
    p.declare("person:iran-leader", "person", "Iran Leader", rank=9)
    p.declare("org:irgc", "org", "IRGC", aliases=["Revolutionary Guards"], rank=9)
    p.document("profile:p1", "profile", date="2026-10-20", title="Hormuz closure", body="Iran closed the strait. IRGC patrols.", url="")
    p.mention(entity="country:IR", document="profile:p1", role="subject", date="2026-10-20")
    p.mention(entity="org:irgc", document="profile:p1", role="actor", date="2026-10-20")
    p.mention(entity="person:iran-leader", document="profile:p1", role="actor", date="2026-10-20")
    p.claim("claim:p1:c1", "Iran closed the strait of Hormuz.", document_id="profile:p1", status="confirmed", grounding="snapshotted", created_at="2026-10-20")
    p.cite("claim:p1:c1", "https://reuters.com/hormuz", title="Reuters")
    p.mention(entity="org:irgc", claim="claim:p1:c1", document="profile:p1", role="in text", date="2026-10-20")
    p.event("profile-timeline:p1:1", "profile_timeline", date="2026-10-19", title="Strait closed", document="profile:p1", actors=["IRGC"])
    d = Sink(conn, "dailies", "daily:geopolitics:2026-10-23", now)
    d.declare("situation:thr_hormuz", "situation", "Hormuz crisis", rank=5)
    d.document("daily:2026-10-23:thr_hormuz", "daily", domain="geopolitics", date="2026-10-23", title="Hormuz crisis (daily of 2026-10-23)", url="/daily/geopolitics", body="Iran keeps the strait closed.")
    d.mention(entity="situation:thr_hormuz", document="daily:2026-10-23:thr_hormuz", role="theater", date="2026-10-23")
    g = Sink(conn, "geoledger", "geo:plant1", now)
    g.declare("asset:plant1", "place", "Bandar Abbas power plant", iso2="IR", lat=27.1, lon=56.2, rank=5)
    g.document("geo:e1", "geo", date="2026-10-21", title="Bandar Abbas power plant (power_plant, IR)", status="damaged", body="Bandar Abbas power plant damaged per Iran.")
    g.mention(entity="asset:plant1", document="geo:e1", role="subject", date="2026-10-21")
    g.mention(entity="asset:plant1", document="geo:e1b", role="subject", date="2026-10-21")
    g.event("event:geo:e1", "status_damaged", date="2026-10-21", title="Bandar Abbas power plant: damaged", place="Bandar Abbas power plant", place_id="asset:plant1", document="geo:e1")
    conn.execute("BEGIN")
    link.finish(conn)
    conn.execute("COMMIT")
    return Corpus(conn, tmp_path / "corpus.db")


def context(tmp_path: Path | None = None, *, with_corpus: bool = False, extra: dict[str, Any] | None = None) -> ViewContext:
    return ViewContext(staged=staged(extra), tables=tables(), corpus=corpus(tmp_path) if with_corpus and tmp_path else None, now=NOW)


def raw_conn(c: Corpus) -> sqlite3.Connection:
    return c.db
