"""
One typed example document per (non-view) schema: ``EXAMPLES[schema] = (logical document path, document)``. Hand-written to the shape the writers produce
(tests/test_contracts.py checks each against ``shapes.SHAPES`` and against the writers' own output where a pure builder exists), and served as a fake bucket to the site's
own TypeScript parsers by ``sites/ohmega-monster/scripts/contract-check.mjs`` (tests/test_site_contracts.py). The views are not here: their examples are built by the
views builders from the test record (tests/test_site_views_contract.py).

Every document carries its stamp, as a published one does. Values the site checks by name (the sentinels in contract-check.mjs) are the ones spelled out below.
"""

from __future__ import annotations

from typing import Any

TODAY = "2026-10-23"
AT = f"{TODAY}T06:00:00+00:00"


def _stamp(schema: str, version: int, doc: dict[str, Any]) -> dict[str, Any]:
    return {"schema": f"{schema}/{version}", **doc}


_PULSE = {"id": "pls_hormuz", "name": "Hormuz flow", "title": "Hormuz flow title", "actors_iso2": ["IR"], "position": 61.0, "band": "severe", "confidence": "medium"}
_SECTION = {"theater_id": "thr_hormuz", "name": "Hormuz crisis", "kind": "section", "temperature": {"heat": 14.0, "trend": "heating", "coverage": "rising", "recent_share": 0.1, "prior_share": 0.05},
            "escalation": {"direction": "rising", "pace": "fast"}, "pulses": [_PULSE], "headline": "Hormuz: the strait stays closed", "bottom_line": "Hormuz bottom line.",
            "developments": [{"headline": "Hormuz development 1", "detail": "d", "when": TODAY, "sources": ["https://example.org/a"], "verification": "researched"}]}
_ASSET = {"id": "plant1", "name": "Bandar Abbas power plant", "aliases": [], "type": "power_plant", "country": "IR", "lat": 27.1, "lon": 56.2, "loc_precision": "exact", "capacity_mw": 500.0,
          "fuel": "gas", "attrs": {}, "source": "wri", "licence": "CC BY", "provenance": "aggregated", "status": "reported_damaged", "status_on": "2026-10-21", "status_by": "Iran", "events": 1,
          "merged_into": None}
_GEO_EVENT = {"id": "e1", "asset_id": "plant1", "occurred_on": "2026-10-21", "occurred_at": "", "status": "reported_damaged", "claimant": "Iran", "confidence": "medium",
              "sources": ["https://example.org/x"], "provenance": "aggregated", "observed_at": "2026-10-22", "note": "", "via": "daily:2026-10-21:thr_hormuz"}
_MARITIME = {"id": "m1", "kind": "ais_gap", "mmsi": 123456789, "mmsi2": None, "name": "MAR AZUL", "name2": "", "imo": "9876543", "flag": "PA", "flag2": "", "ship_class": "tanker",
             "started_at": f"{TODAY}T01:00:00+00:00", "ended_at": None, "last_seen": AT, "state": "ongoing", "active": True, "lat": 26.5, "lon": 56.3, "area": "Strait of Hormuz", "countries": ["IR"],
             "confidence": 0.8, "rationale": "r", "summary": "Went silent for 9 hours.", "detail": {}, "evidence": [[1760000000, 26.5, 56.3, 11.0, "last"]], "provenance": "ohmega_derived", "updated_at": AT}
_SANCTION = {"id": "sx1", "source": "ofac", "action": "designated", "on_date": "2026-10-20", "observed_on": "2026-10-21", "ref": "R1", "name": "MAR AZUL", "type": "vessel",
             "programmes": ["IRAN"], "countries": ["IR"], "imo": "9876543", "flag": "PA", "owner": "X Ltd", "source_url": "https://ofac.treasury.gov/", "baseline": False, "asset_id": "plant1"}
_CAL = {"id": "c1", "on_date": "2099-01-15", "end_date": None, "title": "Gulf summit", "kind": "summit", "countries": ["IR", "SA"], "theaters": [], "source": "official",
        "source_url": "https://example.org/summit", "confidence": "high", "provenance": "aggregated", "via": "", "active": True,
        "situations": [], "grade": "official", "topic": "diplomacy", "importance": 3, "sources": [{"source": "official", "url": "https://example.org/summit"}]}
_STATEMENT = {"id": "s1", "speaker": "A. Official", "role": "Minister", "affiliation": "Government", "iso2": "IR", "date": TODAY, "venue": "", "quote": "We will respond.", "paraphrase": "",
              "about": [], "about_iso2": ["US"], "signal": "threat", "stance": -1, "significance": "", "url": "https://example.org/s", "reported_by": ""}
_BENCH = {"id": "swe", "name": "SWE-bench", "source": "swe-bench", "source_url": "https://example.org/swe", "unit": "fraction", "ceiling": 1.0, "baseline": 0.0, "released": "2024-01-01",
          "superseded_by": "", "n_models": 3, "n_results": 5, "as_of": TODAY, "frontier": [{"d": TODAY, "s": 0.5, "m": "Model A", "l": "lab_a"}], "best": None, "saturation": 0.5, "velocity": 0.01,
          "new_records": [], "open": [], "closed": [], "open_lag_days": None, "gap": None, "labs": {}, "top": [], "claimed": []}
_VESSEL_ROW = ["123456789", 56.3, 26.5, 90, 11, 0, 1760000000, "MAR AZUL"]


def _examples() -> dict[str, tuple[str, dict[str, Any]]]:
    e: dict[str, tuple[str, dict[str, Any]]] = {}

    def add(schema: str, path: str, doc: dict[str, Any], version: int = 1) -> None:
        e[schema] = (path, _stamp(schema, version, doc))

    add("ohmega.daily", f"daily/geopolitics/{TODAY}.json", {"domain": "geopolitics", "date": TODAY, "built_at": AT, "researched": True,
                                                            "summary": {"headline": "Hormuz stays shut", "the_day": ["Iran held the strait."]},
                                                            "editions": [{"n": 1, "label": "Part 1", "cycle": "Asia", "built_at": AT}], "theaters": [_SECTION]})
    add("ohmega.brief", "briefs/hormuz-brief.json", {"slug": "hormuz-brief", "as_of": TODAY, "built_at": AT, "theater_id": "thr_hormuz", "theater_name": "Hormuz crisis", "title": "Hormuz brief",
                                                   "bottom_line": "Closure persists.", "escalation": {"direction": "rising", "pace": "fast", "assessment": "a"},
                                                   "timeline": [{"date": TODAY, "what": "Tankers turned back", "actors": ["Iran"], "verification": "researched", "source": "https://example.org/t"}]})
    add("ohmega.snapshot", "snapshots/2026-10-23-0600.json", {"slug": "2026-10-23-0600", "built_at": AT, "situations": [{"id": "sit_hormuz", "title": "Hormuz", "summary": "s", "domain": "geopolitics",
                                                                                                                       "pulses": [_PULSE], "watches": []}], "theaters": [], "daily": [], "briefs": []})
    add("ohmega.dossier", "theaters/thr_hormuz.json", {"theater_id": "thr_hormuz", "name": "Hormuz crisis", "domain": "geopolitics", "built_at": AT, "first_seen": "2026-10-01", "last_seen": TODAY,
                                                      "days_covered": 5, "current": {"date": TODAY, "bottom_line": "Closure persists.", "headline": "Head"}, "pulses": [],
                                                      "escalation_history": [{"date": f"2026-10-{d:02d}", "direction": "rising", "pace": "fast"} for d in range(1, 24)],
                                                      "coverage_series": [{"day": f"2026-10-{d:02d}", "count": d, "editions": 1} for d in range(1, 24)],
                                                      "actors": [{"name": "Iran", "mentions": 9, "first": "2026-10-01", "last": TODAY}], "places": [{"name": "Tehran", "country": "Iran", "count": 3, "last_date": TODAY}]})
    add("ohmega.dossier.index", "theaters/index.json", {"theaters": [{"theater_id": "thr_hormuz", "name": "Hormuz crisis", "domain": "geopolitics", "first_seen": "2026-10-01", "last_seen": TODAY,
                                                                      "days_covered": 5, "heat": 10, "coverage": "rising", "escalation_direction": "rising", "max_band": "severe", "state": "",
                                                                      "last_novel": TODAY, "parent_id": "", "merged_into": ""}]})
    add("ohmega.pulse", "pulses/pls_hormuz.json", {**_PULSE, "situation_id": "sit_hormuz", "situation": "Hormuz", "status": "active", "velocity_7d": 6.0, "last_assessed": AT, "evidence_through": TODAY,
                                                  "history": [{"at": AT, "position": 61.0}], "definition": {"version": 1, "question": "How closed is the strait?", "low_end": "open", "high_end": "shut"},
                                                  "url": "/pulses", "data_url": "/data/pulses/pls_hormuz.json",
                                                  "readings": [{"at": AT, "mode": "reassessment", "moves_pulse": True, "decision": "applied", "position": 61.0, "rationale": "r", "confidence": "medium"}]})
    add("ohmega.pulses", "data/pulses.json", {"built_at": AT, "pulses": [{"id": "pls_hormuz", "situation_id": "sit_hormuz", "situation": "Hormuz", "name": "Hormuz flow", "position": 61.0, "band": "severe"}]})
    add("ohmega.article.source", "articles/hello.json", {"slug": "hello", "title": "Hello", "status": "published", "published_at": TODAY, "markdown": "---\ntitle: Hello\n---\nBody."})
    add("ohmega.article.index", "articles/index.json", {"articles": [{"slug": "hello", "title": "Hello", "status": "published", "published_at": TODAY, "data": {"title": "Hello"}}]})
    add("ohmega.radar", "radar/2026-10-23-0600.json", {"slug": "2026-10-23-0600", "built_at": AT, "leads": [{"n": 1, "title": "A lead", "thesis": "t", "pillars": ["p"], "kind": "story", "sources": ["https://example.org/l"]}]})
    add("ohmega.record", "record.json", {"window_days": 60, "as_of": TODAY, "count": 1, "total": 1, "statements": [_STATEMENT]})
    add("ohmega.actor", "actors/IR.json", {"iso2": "IR", "name": "Iran", "region": "Middle East", "capital": "Tehran", "data_as_of": TODAY, "headline": [], "groups": {"people": [], "economy": [], "trade": [], "energy": [], "military": []},
                                          "energy_role": {"surplus": [], "deficit": []}, "leadership": {"head_of_state": None, "head_of_government": None, "as_of": TODAY, "nuclear": None},
                                          "statements": [], "involved": {"theaters": [{"id": "thr_hormuz", "name": "Hormuz crisis", "mentions": 9}], "pulses": []}, "credits": []})
    add("ohmega.actor.index", "actors/index.json", {"data_as_of": TODAY, "actors": [{"iso2": "IR", "name": "Iran", "region": "Middle East", "theaters": 1, "statements": 0, "figures": {"gdp": None}}]})
    add("ohmega.forecasts", "data/forecasts.json", {"as_of": AT, "scorecard": {"resolved": 0, "void": 0, "open": 1}, "forecasts": [{"id": "f1", "statement": "Strait reopens", "probability": 0.3, "horizon": "30d",
                                                                                                                                   "made_at": AT, "status": "open", "brief_slug": "hormuz-brief", "resolution": None}]})
    add("ohmega.changes", "data/changes.json", {"window_days": 30, "as_of": AT, "events": [{"type": "daily_published", "at": AT, "domain": "geopolitics", "date": TODAY}]})
    add("ohmega.intel.index", "data/intel.json", {"built_at": AT, "daily": [], "briefs": [], "theaters": []})
    add("ohmega.live.events", "live/events.json", {"events": [{"id": "ev1", "feed": "usgs", "kind": "quake", "title": "M5.1 near Bandar Abbas", "detail": "d", "lat": 27.1, "lon": 56.2, "countries": ["IR"],
                                                               "severity": "notable", "starts_at": AT, "ends_at": None, "source_url": "https://example.org/q", "source": "USGS", "tags": [], "data": {}, "updated_at": AT}]})
    add("ohmega.live.stats", "live/stats.json", {"stats": [{"series_id": "ship.hormuz", "period": TODAY, "value": 80.0, "partial": True, "name": "Hormuz ships", "unit": "ships", "kind": "ships",
                                                            "region": "hormuz", "lat": 26.5, "lon": 56.3, "source_url": "https://example.org"}]})
    add("ohmega.live.anomalies", "live/anomalies.json", {"anomalies": [{"id": "an1", "series": "ship.tanker", "layer": "ship", "klass": "tanker", "place_kind": "gate", "place_id": "hormuz", "label": "Hormuz", "lat": 26.5,
                                                                        "lon": 56.3, "countries": ["IR"], "direction": "above", "starts_at": AT, "ends_at": None, "last_seen": AT, "active": True, "hours": 3.0,
                                                                        "value": 20.0, "normal": 10.0, "ratio": 2.0, "score": 3.0, "confidence": 0.8, "learning": False, "n_cells": 1,
                                                                        "sentence": "Tankers above normal", "provenance": "ohmega_derived", "updated_at": AT}]})
    add("ohmega.live.world", "live/world.json", {"bbox": [-180, -90, 180, 90], "width": 360, "height": 180, "countries": [{"name": "Iran", "d": "M0 0L1 1Z"}], "credit": "Natural Earth"})
    add("ohmega.live.summary", "live/summary.json", {"as_of": AT, "headlines": [{"id": "h1", "layer": "quake", "text": "M5.1 near Bandar Abbas", "score": 3.0, "lat": 27.1, "lon": 56.2, "zoom": 6}],
                                                     "gates": {"hormuz": {"label": "Strait of Hormuz", "lat": 26.5, "lon": 56.3}}, "fresh": {"ships": AT}})
    add("ohmega.live.energy", "live/energy.json", {"as_of": AT, "gas": None, "lng": None, "tiles": [{"id": "brent", "label": "Brent", "unit": "usd", "value": 80.0, "as_of_day": TODAY, "change_pct": 1.0,
                                                                                                    "spark": [1, 2], "source": "EIA", "source_url": "https://example.org"}], "credits": {"gas": {"text": "t", "url": "u"}, "lng": {"text": "t", "url": "u"}}})
    add("ohmega.live.fires", "live/fires.json", {"as_of": AT, "cell_deg": 0.5, "detections": 3, "occupied": 2, "cells": [[56.0, 26.0, 2, 10.0]]})
    add("ohmega.live.vessels", "live/vessels.json", {"as_of": AT, "ttl": 3600, "n": 1, "classes": ["tanker"], "counts": {"tanker": 1}, "rows": [_VESSEL_ROW]})
    add("ohmega.live.aircraft", "live/aircraft.json", {"as_of": AT, "n": 1, "classes": ["civil"], "counts": {"civil": 1, "military": 0}, "rows": [["abc", 56.0, 26.0, 90, 400, 0, 1760000000]]})
    add("ohmega.live.coverage", "live/coverage.json", {"as_of": AT, "deg": 1, "hours": 24, "cells": [1, 2, 3]})
    add("ohmega.live.points", "live/points.json", {"as_of": AT, "aircraft_as_of": AT, "deg": 0.05, "layers": {"vessels": {"n": 1, "counts": {"tanker": 1}, "classes": ["tanker"], "p": [1, 2, 3]},
                                                                                                          "aircraft": {"n": 0, "counts": {}, "classes": ["civil"], "p": []}}})
    add("ohmega.live.tiles.index", "live/tiles/index.json", {"as_of": AT, "aircraft_as_of": AT, "deg": 5, "vessels": {"r1c1": [1, "etag"]}, "aircraft": {}})
    add("ohmega.live.tile", "live/tiles/r1c1.json", {"tile": "r1c1", "n": 1, "rows": [_VESSEL_ROW]})
    add("ohmega.live.tracks", "live/tracks/0.json", {"as_of": AT, "t": {"123456789": [56.3, 26.5, 56.4, 26.6]}})
    add("ohmega.flows", "live/flows.json", {"v": 1, "as_of": AT, "today": TODAY, "classes": [{"id": "tanker", "label": "Tankers"}], "places": {},
                                            "ais": {"since": TODAY, "days": 3, "windows": [7, 30], "note": "n", "learning": True, "places": [], "lanes": []}})
    add("ohmega.satellite", "live/satellite.json", {"v": 1, "as_of": AT, "credit": "Copernicus", "read_as": "A machine signal.", "pass": {}, "counts": {"watched": 1, "with_imagery": 1, "changed": 0, "dimmer": 0},
                                                    "sites": [{"id": "plant1", "name": "Bandar Abbas power plant", "kind": "asset", "asset_type": "power_plant", "lat": 27.1, "lon": 56.2, "half_km": 2.0,
                                                               "priority": 1, "why": [], "state": "ok", "baseline": None, "latest": None, "change": None, "night": None, "bbox": [56, 27, 56.3, 27.3],
                                                               "event_on": None, "countries": ["IR"], "links": {}, "note": "", "checked_at": None}]})
    add("ohmega.maritime.events", "maritime/recent.json", {"events": [_MARITIME]})
    add("ohmega.maritime.counts", "maritime/counts.json", {"total": 1, "ongoing": 1, "byKind": {"ais_gap": 1}})
    add("ohmega.sanctions", "sanctions/recent.json", {"rows": [_SANCTION]})
    add("ohmega.calendar", "calendar/next.json", {"items": [_CAL]})
    add("ohmega.geo.place", "geo/a/plant1.json", {"asset": _ASSET, "events": [_GEO_EVENT]})
    add("ohmega.geo.assets", "geo/c/IR.json", {"assets": [_ASSET]})
    add("ohmega.geo.countries", "geo/countries.json", {"countries": [{"iso": "IR", "n": 1, "n_events": 1, "bbox": [56.2, 27.1, 56.2, 27.1]}]})
    add("ohmega.geo.grid", "geo/grid/IR.json", {"iso": "IR", "as_of": TODAY, "line": "Grid down 12% in 30 days.", "windows": {"7": {}, "30": {}}, "installed": {}})
    add("ohmega.geo.events", "geo/events/2026-10.json", {"events": [_GEO_EVENT]})
    add("ohmega.ai-benchmarks", "data/ai-benchmarks.json", {"as_of": TODAY, "note": "", "sources": [{"source": "swe-bench", "name": "SWE-bench", "last_ok": AT, "last_error": "", "rows": 5, "newest_result": TODAY,
                                                                                                   "stale": False, "reasons": [], "page": "https://example.org", "licence": "MIT"}],
                                                          "labs": [{"id": "lab_a", "name": "Lab A", "models": 3, "records": 5}], "benchmarks": [_BENCH]})
    add("ohmega.track-record", "data/track-record.json", {"as_of": AT, "paper_only": True, "disclaimer": "Paper trading only.", "markets": {"open": 1, "resolved": 0, "void": 0}, "forecasts": 2,
                                                          "scores": {"compared": 0, "resolved_with_forecast": 0}, "portfolio": {}, "trader": {"limits": {"bankroll": 1000}, "summary": {"equity": 1010, "pnl": 10, "open": 1},
                                                                                                                                              "curve": [{"day": TODAY, "flat": 1000, "trader": 1010}], "open_positions": []},
                                                          "open_positions": [], "disagreements": [], "worst_misses": [], "market_beat_us": 0, "resolved": [], "other": {}, "rules": {"bankroll": 1000},
                                                          "fast": {"summary": {"equity": 1005, "pnl": 5, "open": 1}, "curve": [{"day": TODAY, "flat": 1000, "trader": 1005, "rule": None}],
                                                                   "open_positions": [{"market_id": "m1", "question": "Will it settle soon?", "url": "https://polymarket.com/event/x", "ends": TODAY,
                                                                                       "side": "yes", "shares": 10, "entry": 0.4, "now": 0.5, "cost": 4, "value": 5, "pnl": 1, "opened": TODAY,
                                                                                       "rationale": "Why.", "rationale_on": TODAY, "ours": 0.6, "evidence": "sufficient",
                                                                                       "trail": [{"id": "country:IR", "kind": "country", "title": "Iran", "date": "", "href": "/intel/actors/IR"}]}],
                                                                   "log": [], "today": {}, "since": TODAY, "limits": {"bankroll": 1000}, "horizon_days": 7, "every_hours": 4, "enabled": True},
                                                          "evidence": {"coverage": {"n": 3, "rated": 3, "sufficient": 2, "thin": 1, "gap": 0, "share_sufficient": 0.667, "share_gap_requested": 0.333,
                                                                                    "forecasts": {"n": 2, "rated": 2, "sufficient": 1, "thin": 1, "gap": 0, "share_sufficient": 0.5, "share_gap_requested": 0.5},
                                                                                    "trades": {"n": 1, "rated": 1, "sufficient": 1, "thin": 0, "gap": 0, "share_sufficient": 1.0, "share_gap_requested": 0.0}},
                                                                       "citations": {"n": 3, "mean": 2.3, "median": 2, "none_share": 0.0},
                                                                       "tools": {"traces": 3, "corpus": 3, "fallback": 0, "queries": 9, "by_tool": {"search": 5, "entity": 4}, "mean_results": 4.1, "empty_share": 0.1,
                                                                                 "error_share": 0.0, "median_latency_ms": 900, "mean_usd": 0.01, "mean_tokens": 800, "mean_rounds": 1.5},
                                                                       "top_gaps": [{"topic": "Hormuz insurance rates", "asks": 2, "why": "to size the risk", "last": TODAY, "status": "open", "filled": "",
                                                                                     "markets": [{"market_id": "m1", "question": "Will it settle soon?"}]}],
                                                                       "accuracy": {"rich_min_cited": 3, "min_for_verdict": 30, "forecasts": [{"label": "cited 3 or more corpus items", "n": 1, "shown": False, "brier_ours": None,
                                                                                                                                              "brier_market": None, "skill": None}],
                                                                                    "trades": [{"label": "opened on 3 or more cited items", "n": 0, "shown": False, "pnl": None, "hit_rate": None}], "note": "Withheld."},
                                                                       "caps": {"rounds": 2, "queries_per_round": 4, "rows_per_query": 6, "gap_fill_usd_per_day": 0.5, "corpus_only": True},
                                                                       "gap_spend": {"asks": 2, "fills": 0, "usd": 0.0}},
                                                          "day": {"summary": {"equity": 1003, "pnl": 3, "open": 1}, "curve": [{"day": TODAY, "flat": 1000, "trader": 1003, "rule": None}],
                                                                 "open_positions": [{"market_id": "d1", "question": "Will the vote pass today?", "url": "https://polymarket.com/event/y", "ends": TODAY, "ends_at": f"{TODAY}T18:00",
                                                                                     "hours_left": 6.5, "side": "no", "shares": 8, "entry": 0.5, "now": 0.6, "cost": 4, "value": 4.8, "pnl": 0.8, "opened": TODAY,
                                                                                     "rationale": "The vote is already counted.", "rationale_on": TODAY, "ours": 0.3, "evidence": "", "trail": []}],
                                                                 "log": [], "today": {}, "since": TODAY, "limits": {"bankroll": 1000, "max_usd_per_day": 0.45, "max_usd_per_run": 0.15}, "horizon_hours": 48,
                                                                 "run_hours": [8, 14, 20], "run_minute": 40, "enabled": True, "min_for_verdict": 30, "spend_usd": 0.2, "spend_today": 0.1, "avg_hold_h": 5.5,
                                                                 "by_horizon": [{"label": "under 6 hours", "n": 2, "shown": False, "wins": None, "hit_rate": None, "pnl": None}], "by_category": [],
                                                                 "runs": [{"id": "dr-1", "at": AT, "usd": 0.1, "turns": 3, "tool_calls": 7, "stopped": "done", "summary": "Bought one.", "n_considered": 2, "n_queries": 1,
                                                                           "considered": [{"id": "d1", "question": "Will the vote pass today?", "ends": f"{TODAY}T18:00"}], "queries": ["search(vote)"], "equity": 1003,
                                                                           "orders": [{"market_id": "d1", "question": "Will the vote pass today?", "action": "buy_no", "side": "no", "stake": 4, "requested": 4, "price": 0.5,
                                                                                       "reason": "Already counted.", "clips": []}]}],
                                                                 "wishes": [{"topic": "Live vote tallies", "runs": 2, "asks": 2, "why": "d1 turns on the count", "source": "parliament feed", "last": TODAY,
                                                                             "markets": [{"market_id": "d1", "question": "Will the vote pass today?"}]}],
                                                                 "watchlist": [{"market_id": "d2", "question": "Will talks start?", "note": "waiting", "since": TODAY}]},
                                                          "horizons": {"by_horizon": [{"label": "2 days or less", "n": 0, "shown": False, "brier_ours": None, "brier_market": None, "skill": None}], "min_for_verdict": 30,
                                                                       "books": {"fast": {"positions": 1, "resolved": 0, "median_days_to_resolution": None, "mean_days_to_resolution": None}}}}, version=2)
    add("ohmega.status", "status/sanctions.json", {"product": "sanctions", "job": "sanctions", "checked_at": AT, "last_ok": True, "last_changed_at": "2026-10-12T04:00:00+00:00", "last_failed_at": None,
                                                    "cadence_min": 360, "next_due": f"{TODAY}T12:00:00+00:00"})
    return e


EXAMPLES: dict[str, tuple[str, dict[str, Any]]] = _examples()
