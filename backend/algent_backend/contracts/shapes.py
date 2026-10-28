"""
What the site reads of each published document family, keyed by schema id (language: ``spec.py``). The declarations that say which paths carry which
schema and version are in the product registry; ``tests/test_contracts.py`` keeps the two in step and checks every shape against its writer or example.

A shape lists the fields the site's parsers *use*. Extra fields are always allowed (additive change = no new major); a renamed, removed or retyped field
fails here before it reaches a reader.
"""

from __future__ import annotations

from typing import Any

_ENV: dict[str, Any] = {"schema": "str", "built_at": "str", "as_of": "str", "provenance": {"builder": "str", "sources": [{"product": "str", "from": "str"}]}}

_ASSET = {"id": "str", "name": "str", "aliases": ["str"], "type": "str", "country": "str", "lat": "num|null", "lon": "num|null", "loc_precision": "str", "capacity_mw": "num|null",
          "fuel": "str", "attrs": "obj", "source": "str", "licence": "str", "provenance": "str", "status": "str|null", "status_on": "str|null", "status_by": "str|null", "events": "int",
          "merged_into": "str|null"}
_GEO_EVENT = {"id": "str", "asset_id": "str", "occurred_on": "str", "occurred_at": "str", "status": "str", "claimant": "str", "confidence": "str", "sources": ["str"],
              "provenance": "str", "observed_at": "str", "note": "str", "via": "str"}
_MARITIME = {"id": "str", "kind": "str", "mmsi": "int", "name": "str", "imo": "str", "flag": "str", "ship_class": "str", "started_at": "str", "ended_at": "str|null", "state": "str",
             "active": "bool", "lat": "num|null", "lon": "num|null", "area": "str", "countries": ["str"], "confidence": "num", "summary": "str", "evidence": "list", "updated_at": "str"}

_CONFLICT_ROW = {"id": "str", "source": "in:gdelt,reliefweb,acled,ucdp", "on_date": "str", "type": "str", "lat": "num|null", "lon": "num|null", "place": "str", "country": "str", "actor1": "str",
                 "actor2": "str", "fatalities": "int|null", "articles": "int", "title": "str", "urls": ["str"], "coding": "in:machine,curated,report", "confidence": "in:low,medium,high",
                 "basis": "str", "assets": [{"id": "str", "name": "str", "type": "str", "km": "num"}]}
_ZONE_ROW = {"id": "str", "on_date": "str", "source": "in:ohmega_adsb,gpsjam", "cell": "str", "lat": "num", "lon": "num", "size_deg": "num", "country": "str", "severity": "in:low,medium,high",
             "degraded_share": "num", "aircraft": "int", "flag": "str", "cross_check": "str"}

SHAPES: dict[str, Any] = {
    # ── editorial ─────────────────────────────────────────────────────────────────────────────
    "ohmega.daily": {"domain": "str", "built_at": "str", "summary": {"headline": "str", "the_day?": ["str"]},
                     "theaters": [{"name": "str", "theater_id?": "str", "temperature": {"heat": "num", "trend": "str"}, "escalation": {"direction": "str", "pace?": "str"},
                                   "headline?": "str", "bottom_line?": "str", "developments?": [{"headline": "str", "sources?": ["str"]}]}],
                     "editions?": [{"n": "int"}], "date?": "str", "researched?": "bool"},
    "ohmega.brief": {"slug": "str", "as_of": "str", "theater_id": "str", "theater_name": "str", "title": "str", "bottom_line": "str",
                     "escalation": {"direction": "str"}, "timeline?": [{"date": "str", "what": "str"}]},
    "ohmega.snapshot": {"built_at": "str", "situations": [{"title": "str", "pulses": [{"id": "str", "name": "str", "position": "num|null", "band": "str"}]}], "theaters": "list"},
    "ohmega.dossier": {"theater_id": "str", "name": "str", "domain": "str", "built_at": "str", "first_seen": "str", "last_seen": "str", "days_covered": "int",
                       "escalation_history": [{"date": "str", "direction": "str"}], "coverage_series": [{"day": "str", "count": "num"}],
                       "actors?": [{"name": "str", "mentions": "int"}], "places?": [{"name": "str", "count": "int"}]},
    "ohmega.dossier.index": {"theaters": [{"theater_id": "str", "name": "str", "domain": "str", "first_seen": "str", "last_seen": "str", "days_covered": "int", "heat": "num",
                                           "escalation_direction": "str", "max_band": "str"}]},
    "ohmega.pulse": {"id": "str", "name": "str", "situation_id": "str", "situation": "str", "status": "str", "position": "num|null", "band": "str",
                     "history": [{"at": "str", "position": "num"}], "readings": [{"at": "str", "mode": "str", "position": "num|null"}], "definition": {"question": "str"}},
    "ohmega.pulses": {"built_at": "str", "pulses": [{"id": "str", "situation_id": "str", "name": "str", "position": "num|null", "band": "str"}]},
    "ohmega.article.source": {"slug": "str", "title": "str", "status": "str", "published_at": "str", "markdown": "str"},
    "ohmega.article.index": {"articles": [{"slug": "str", "title": "str", "status": "str", "published_at": "str", "data": "obj"}]},
    "ohmega.radar": {"built_at": "str", "leads": [{"n": "int", "title": "str", "thesis": "str", "sources?": ["str"]}]},
    "ohmega.record": {"as_of": "str", "window_days": "int", "count": "int", "statements": [{"id": "str", "speaker": "str", "date": "str", "signal": "str", "stance": "num"}]},
    "ohmega.actor": {"iso2": "str", "name": "str", "region": "str", "capital": "str", "data_as_of": "str", "headline": "list", "groups": {"*": "list"}, "leadership": "obj",
                     "involved": {"theaters": "list", "pulses": "list"}},
    "ohmega.actor.index": {"data_as_of": "str", "actors": [{"iso2": "str", "name": "str", "region": "str", "theaters": "int", "statements": "int", "figures": "obj"}]},
    "ohmega.forecasts": {"as_of": "str", "scorecard": "obj", "forecasts": [{"id": "str", "statement": "str", "probability": "num", "made_at": "str", "status": "str"}]},
    "ohmega.changes": {"window_days": "int", "as_of": "str", "events": [{"type": "str", "at": "str"}]},
    "ohmega.intel.index": {"built_at": "str", "daily": "list", "briefs": "list", "theaters": "list"},
    # ── measured layers ───────────────────────────────────────────────────────────────────────
    "ohmega.live.events": {"events": [{"id": "str", "feed": "str", "kind": "str", "title": "str", "severity": "str", "countries": ["str"], "lat": "num|null", "lon": "num|null", "updated_at": "str"}]},
    "ohmega.live.stats": {"stats": [{"series_id": "str", "period": "str", "value": "num", "partial": "bool", "name": "str", "unit": "str", "kind": "str", "region": "str"}]},
    "ohmega.live.anomalies": {"anomalies": [{"id": "str", "series": "str", "sentence": "str", "direction": "str", "confidence": "num", "active": "bool", "starts_at": "str", "ends_at": "str|null",
                                             "countries": ["str"]}]},
    "ohmega.live.world": {"bbox": "list", "width": "num", "height": "num", "countries": [{"name": "str", "d": "str"}]},
    "ohmega.live.summary": {"as_of": "str", "headlines": [{"id": "str", "layer": "str", "text": "str", "score": "num"}], "gates": {"*": {"label": "str", "lat": "num", "lon": "num"}}, "fresh": "obj"},
    "ohmega.live.energy": {"as_of": "str", "tiles": [{"id": "str", "label": "str", "unit": "str", "value": "num", "source": "str"}], "credits": "obj"},
    "ohmega.live.fires": {"as_of": "str", "cell_deg": "num", "detections": "int", "occupied": "int", "cells": "list"},
    "ohmega.live.vessels": {"as_of": "str", "ttl": "num", "n": "int", "classes": ["str"], "counts": "obj", "rows": "list"},
    "ohmega.live.aircraft": {"as_of": "str", "n": "int", "classes": ["str"], "counts": "obj", "rows": "list"},
    "ohmega.live.coverage": {"as_of": "str", "deg": "num", "hours": "num", "cells": "list"},
    "ohmega.live.points": {"as_of": "str", "aircraft_as_of": "str", "deg": "num", "layers": {"vessels": {"n": "int", "classes": ["str"], "p": "list"}, "aircraft": {"n": "int", "classes": ["str"], "p": "list"}}},
    "ohmega.live.tiles.index": {"as_of": "str", "aircraft_as_of": "str", "deg": "num", "vessels": "obj", "aircraft": "obj"},
    "ohmega.live.tile": {"tile": "str", "n": "int", "rows": "list"},
    "ohmega.live.tracks": {"as_of": "str", "t": "obj"},
    "ohmega.flows": {"v": "int", "as_of": "str", "today": "str", "classes": [{"id": "str", "label": "str"}], "places": "obj",
                     "ais": {"days": "num", "windows": ["num"], "note": "str", "learning": "bool", "places": "list", "lanes": "list"}},
    "ohmega.satellite": {"v": "int", "as_of": "str", "credit": "str", "read_as": "str", "pass": "obj", "counts": {"watched": "int", "with_imagery": "int", "changed": "int", "dimmer": "int"},
                         "sites": [{"id": "str", "name": "str", "kind": "str", "lat": "num", "lon": "num", "half_km": "num"}]},
    "ohmega.maritime.events": {"events": [_MARITIME]},
    "ohmega.maritime.counts": {"total": "int", "ongoing": "int", "byKind": {"*": "int"}},
    "ohmega.sanctions": {"rows": [{"id": "str", "source": "str", "action": "str", "on_date": "str", "observed_on": "str", "ref": "str", "name": "str", "type": "str", "programmes": ["str"],
                                   "countries": ["str"], "imo": "str", "flag": "str", "owner": "str", "source_url": "str", "baseline": "bool", "asset_id": "str|null"}]},
    "ohmega.conflict.recent": {"as_of": "str", "since": "str", "window_days": "int", "total": "int", "shown": "int", "capped": "bool",
                               "by_day": {"*": {"events": "int", "machine": "int", "curated": "int"}}, "sources": {"*": {"keyed": "bool", "active": "bool", "last_ok": "str"}}, "coverage": {"*": "str"},
                               "rows": [_CONFLICT_ROW]},
    "ohmega.conflict.country": {"iso": "str", "as_of": "str", "window_days": "int", "total": "int", "capped": "bool", "rows": [_CONFLICT_ROW]},
    "ohmega.gnss.latest": {"day": "str", "generated_at": "str", "samples": "int", "baseline_days": "int", "baseline_since": "str", "coverage": {"*": "str"},
                           "ours": [_ZONE_ROW], "gpsjam": [_ZONE_ROW], "history": [{"day": "str", "zones": "int", "high": "int", "flagged": "int"}]},
    "ohmega.gnss.overlay": {"v": "int", "as_of": "str", "date": "str", "zones": [{"lat": "num", "lon": "num", "r": "num", "s": "in:low,medium,high", "share": "num", "f": "str", "src": "in:o,g"}],
                            "p": {"ours": {"basis": "str", "coverage_note": "str"}, "gpsjam": {"basis": "str", "coverage_note": "str"}}},
    "ohmega.calendar": {"items": [{"id": "str", "on_date": "str", "end_date": "str|null", "title": "str", "kind": "str", "countries": ["str"], "theaters": ["str"], "source": "str",
                                   "source_url": "str", "confidence": "str", "provenance": "str", "via": "str", "active": "bool",
                                   "situations": ["str"], "grade": "str", "topic": "str", "importance": "int", "sources": [{"source": "str", "url": "str"}]}]},
    "ohmega.geo.place": {"asset": _ASSET, "events": [_GEO_EVENT]},
    "ohmega.geo.assets": {"assets": [_ASSET]},
    "ohmega.geo.countries": {"countries": [{"iso": "str", "n": "int", "n_events": "int", "bbox": "list|null"}]},
    "ohmega.geo.grid": {"windows": {"7": "obj", "30": "obj"}, "installed": "obj"},
    "ohmega.geo.events": {"events": [_GEO_EVENT]},
    "ohmega.ai-benchmarks": {"as_of": "str", "sources": [{"source": "str", "name": "str", "last_ok": "str", "rows": "int", "stale": "bool"}], "labs": [{"id": "str", "name": "str", "models": "int", "records": "int"}],
                             "benchmarks": [{"id": "str", "name": "str", "source": "str", "unit": "str", "n_models": "int", "n_results": "int", "as_of": "str", "frontier": "list"}]},
    "ohmega.track-record": {"as_of": "str", "markets": {"open": "int", "resolved": "int", "void": "int"}, "forecasts": "int", "scores": "obj", "trader": "obj", "open_positions": "list",
                            "resolved": "list", "rules": "obj",
                            # additive since 10-23 (no major bump): the fast book, the evidence section and forecast accuracy by horizon
                            "fast?": {"summary": "obj", "curve": "list", "open_positions": [{"market_id": "str", "question": "str", "trail?": [{"id": "str", "title": "str"}]}],
                                      "horizon_days": "num", "every_hours": "num"},
                            "evidence?": {"coverage": {"n": "int", "rated": "int", "sufficient": "int", "thin": "int", "gap": "int", "share_sufficient": "num|null"},
                                          "citations": "obj", "tools": {"queries": "int", "by_tool": "obj"},
                                          "top_gaps": [{"topic": "str", "asks": "int", "status": "str"}],
                                          "accuracy": {"rich_min_cited": "int", "min_for_verdict": "int", "forecasts": [{"label": "str", "n": "int", "shown": "bool"}], "trades": "list", "note": "str"},
                                          "caps": "obj", "gap_spend": "obj"},
                            "horizons?": {"by_horizon": [{"label": "str", "n": "int", "shown": "bool"}], "books": "obj"},
                            # additive since 10-28: the strategy roster (markets/strategies.py), every bot its own forecaster; one section each, shaped like `day`
                            "strategies?": [{"id": "str", "name": "str", "method": "str", "method_name": "str", "style": "str", "must_trade": "bool", "summary": "obj", "curve": "list",
                                             "open_positions": "list", "log": "list", "next_run": "str", "last_at": "str", "run_hours": "list",
                                             # additive since 10-28: forecast feedback (markets/bot_forecasts.py) and the activity floor
                                             "forecasts?": {"made": "int", "resolved": "int", "min_resolved": "int", "shown": "bool", "brier": "num|null", "brier_market": "num|null",
                                                            "log_loss": "num|null", "skill_vs_market": "num|null",
                                                            "recent": [{"market_id": "str", "question": "str", "p": "num", "market": "num|null", "outcome": "str"}]},
                                             "exposure?": {"pct": "num", "floor_pct": "num"},
                                             "floor?": {"opened": "int", "groups": [{"label": "str", "n": "int", "shown": "bool"}]}}]},
    "ohmega.status": {"product": "str", "job": "str", "checked_at": "str", "last_ok": "bool", "last_changed_at": "str|null", "last_failed_at": "str|null", "cadence_min": "num|null", "next_due": "str|null"},
    # ── views (docs/architecture/views.md) ────────────────────────────────────────────────────
    "ohmega.view.country": {**_ENV, "iso": "str", "name": "str", "region": "str", "capital": "str", "profiled": "bool",
                            "panel": {"iso": "str", "stats": [{"id": "str", "label": "str", "value": "num", "unit": "str"}], "counts": {"theaters": "int", "sanctions": "int", "calendar": "int"},
                                      "leaders": {"head_of_state": "str", "head_of_government": "str"}, "briefs": "list", "briefsTotal": "int"},
                            "context": {"theaters": "list", "said": "list", "developments": "list", "related": "list"}, "sanctions": "list", "calendar": "list", "anomalies": "list", "attacks?": "any", "gnss?": "any"},
    "ohmega.view.situation": {**_ENV, "id": "str", "name": "str", "desk": "str", "domain": "str", "stream": {"days_total": "int", "full": "list", "index": "list", "index_total": "int"},
                              "involved": "list", "states": "list", "related": "list"},
    "ohmega.view.situations": {**_ENV, "desks": [{"desk": "str", "active": "list", "quiet": "list", "merged": "list"}]},
    "ohmega.view.entity": {**_ENV, "id": "str", "kind": "str", "name": "str", "aliases": ["str"], "uses": "int", "counts": "obj", "relations": "list", "related": "list", "documents": "list",
                           "claims": "list", "events": "list", "series": "list"},
    "ohmega.view.event": {**_ENV, "date": "str", "theater": {"id": "str", "name": "str"}, "name": "str", "anchor": "str", "index": "int", "domain": "str", "developments": "list", "actor_isos": "list"},
    "ohmega.view.series": {**_ENV, "metric": "str", "key": "str", "label": "str", "unit": "str", "basis": "str", "product": "str", "n": "int", "entities_total": "int", "entities": "list"},
    "ohmega.view.series-index": {**_ENV, "metrics": [{"metric": "str", "key": "str", "label": "str", "unit": "str", "basis": "str", "product": "str", "n": "int"}], "metrics_total": "int"},
    "ohmega.view.home": {**_ENV, "reports": "obj", "moving": [{"id": "str", "name": "str", "desk": "str", "stamp": "str"}], "coming": "list",
                         "facts": {"daily_stamp": "str", "situations": {"active": "int", "rising": "int", "stamp": "str"}, "actors": "int", "pulses": {"total": "int", "severe": "int", "built_at": "str"},
                                   "calendar_30d": "int", "sanctions": {"additions": "int", "newest_observed": "str"}}},
    "ohmega.view.hud": {**_ENV, "globe": "any", "hud": {"asOf": "str", "daily": "any", "theaters": "list", "pulses": "list", "coming": "list", "sanctions": "list", "trader": "any", "attacks?": "any", "gnss?": "any"}},
    "ohmega.view.daily-hub": {**_ENV, "desks": [{"desk": "str", "date": "str", "dates_total": "int", "recent": ["str"], "report": "any"}]},
    "ohmega.view.graph": {**_ENV, "theaters": "list", "ties": "obj", "names": "obj", "linkable": ["str"]},
    "ohmega.view.search-index": {**_ENV, "fields": {"entities": ["str"], "documents": ["str"]}, "entities": "list", "entities_total": "int", "documents": "list"},
    "ohmega.view.manifest": {**_ENV, "families": "obj", "count": "int"},
}
