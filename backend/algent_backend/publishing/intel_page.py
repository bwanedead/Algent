"""
The intel desk on the site — Pulses, hot theaters and briefs, as one data snapshot per build.

The site (static Next.js) reads this contract; keep it stable.

Snapshot file ``content/intel/snapshots/<slug>.json``, slug = UTC "YYYY-MM-DD-HHMM", kept forever
(archive)::

    {"schema":"ohmega.intel/1","slug","built_at",
     "situations":[{"id","title","summary","domain",
         "pulses":[{"id","name","title","actors_iso2":["US","CN"],   // title = who + what ("US-China . Diplomatic
                    // deadlock"), from the display-label cache ``intel_store/pulse_labels.json``
                    // (``pulse_labels.py``); no label yet -> "<situation title> . <name>", actors_iso2 []
                    "question","low_end","high_end","position":float|null,
                    "band":"calm|elevated|severe|critical|unassessed","velocity_7d":float|null,
                    "velocity_30d":float|null,"confidence":str,"last_assessed":str,
                    "evidence_through":str,"history":[{"at","position"}],"rationale":str}],
         "watches":[{"condition","why","direction","horizon","status"}]}],   // open watches only
     "theaters":[{"id","name","domain","why","heat","trend","coverage","recent","prior",   // recent/prior: raw counts
                  // trend/coverage = COVERAGE momentum (share of headlines), NOT severity: coverage is
                  // trend as a label ("rising|steady|falling coverage"/"newly reported"; heating|steady|
                  // cooling|new stay as stored). Escalation = the situation itself (daily/brief);
                  // Pulse band = severity. Never present heat or trend as how bad things are.
                  "recent_share","prior_share",   // 0-1: share of all headlines in that 3-day window's
                                                  // editions; trend compares these, not the counts
                  "first_seen","series":[{"day","count","editions"}],   // editions = radar editions built
                                                  // that day; 0 = coverage gap, not a quiet day
                  "brief":slug|null}],            // newest board, hottest first;
                                                  // brief = newest brief slug for that theater id
     "briefs":[{"slug","title","bottom_line","theater_id","theater_name","as_of","direction","pace"}],
                                                                   // every brief ever, newest first
     "forecasts":{"scorecard":{"resolved","void","open","brier":float|null,   // lower is better, .25 = coin flip
                               "calibration":[{"range":"70-79","count","hit_rate"}]},
                  "open":[{"statement","probability","horizon","theater_name","brief_slug"}],   // 20 soonest horizon
                  "resolved":[{"statement","probability","outcome":"yes|no|void","resolved_at","evidence"}]}}
                                                                   // 20 newest resolved; from intel_store/forecasts.jsonl
     "daily":[{"domain","date","headline","theaters":[{"id","name"}]}]}   // every daily report, newest
                                                                   // first; theaters lets the site cross-link

Brief files: ``content/intel/briefs/<slug>.json`` = the persisted brief record
(``intel_store/briefs/<slug>.json``, schema ``ohmega.brief/1``); it carries ``on_record`` as the daily does.

The record ledger (``content/intel/record.json`` and ``public/data/record.json``, ``on_record.export``)::

    {"schema":"ohmega.record/1","window_days":60,"max_statements":1500,"as_of","count","newest",
     "statements":[<on_record row>],        // statements dated within the last 60 days, newest first, <=1500
     "tone":[{"affiliation","iso2","about","about_iso2","n","mean","points":[{"date","stance","n"}]}]}
        // stance -2 hostile .. +2 conciliatory toward `about`; dyads with >=4 statements on >=2 days, <=12

Daily files: ``content/intel/daily/<domain>/<YYYY-MM-DD>.json`` = the persisted daily report
(``intel_store/daily/<domain>/<date>.json``), schema ``ohmega.daily/1``::

    {"schema","domain","date","built_at","researched":bool,
     "summary":{"headline","the_day":[3-6 one-sentence bullets, most important first]},
     "theaters":[{"theater_id","name",
         "temperature":{"heat","trend","coverage","recent_share","prior_share"},   // coverage, as above
         "escalation":{"direction":"rising|steady|easing|unclear","pace":"fast|gradual|flat"},
         "pulses":[{"id","name","position":float|null,"band","change_24h":float|null,"change_7d":float|null}],
         "on_record":[{"id","speaker","role","affiliation","iso2","date","venue","quote","paraphrase","about":[..],
                       "about_iso2":[..],"signal","stance":-2..2,"significance","url"}],   // the statements the writer
                       // was shown, in sensing's order (``on_record.build``); absent in older records
         "bottom_line","since_yesterday":[{"what","kind":"escalated|eased|new|resolved|unchanged"}],
         "developments":[{"headline","detail","when","where","actors":[...],
             "statements":[{"who","role","said","quote":bool,"when","source"}],   // quote=true: exact, <=25 words
             "significance","verification":"researched|reported","sources":[urls]}],
         "context":[{"what","when","why_relevant","source"}],   // older items that explain today
         "outlook","watch_next":[...],"brief_slug":slug|null,
         "key_figures":[{"label","value":number,"unit","baseline":number|null,"baseline_label",
                         "as_of":"YYYY-MM-DD","source":url}],   // 0-4, only numbers the research states
         "map":null|{"bbox":[w,s,e,n],"projection":"equirectangular","width":1000,"height":int,
                     "countries":[{"name","d"}],   // SVG path in the 0..width x 0..height frame
                     "points":[{"x","y","label","date","verification","n"}],   // n: 1-based, developments[n-1]
                     "credit"}}],   // our own validated points over Natural Earth; null without a point
         // each development also carries "place":{"name","country","lat","lon"}|null (validated)
     "cross_theater":[{"theaters":[names],"link"}],
     "pulse_proposals":[{"theater","name","question","low_end","high_end","why"}]}

Pulse numbers and deltas are computed from the Pulse store, never by a model. Key figures are numbers
the research stated, kept only with a source the research cited; places are validated against the
basemap (inside the country or within ~50 km of its border) and dropped otherwise.

SYNC RULE: /intel and the daily report must never disagree because someone forgot to republish. Every
process that changes what /intel shows ends by calling ``publish_intel()`` (never raises) exactly once:
the rail after it feeds the Pulses, the radar menu build after ``publish_menu`` (heat and theaters derive
from radar editions; no paid heat clustering is run for it), ``newsroom intel`` heat/brief/cycle/daily,
and ``newsroom pulse`` commit/reassess/promote/promote-ready. A process that calls others (daily runs
promote-ready) lets the inner step stay quiet and publishes once at its own end.

Agent feed (static data files in the site checkout under ``public/data``, beside the article twins; built by
``agent_feed.py``; URLs are relative to the site root; ``data_url`` is the JSON, ``url`` the human page)::

    pulses.json = {"schema":"ohmega.pulses/1","built_at",
        "pulses":[{"id","situation_id","situation","name","question","low_end","high_end",
                   "status":"experimental|active|dormant","position":float|null,"band",
                   "confidence","last_assessed","evidence_through","velocity_7d":float|null,
                   "history":[{"at","position"}],"rationale","data_url":"/data/pulses/<id>.json"}]}
        // the registry catalog: what each Pulse measures and where it stands. Needs the Pulse store.
    pulses/<pulse_id>.json = {"schema":"ohmega.pulse/1", id,name,situation_id,situation,status,position,band,
        confidence,velocity_7d,last_assessed,evidence_through,history,   // as in pulses.json
        "definition":{"version","question","low_end","high_end"},"url":"/pulses","data_url",
        "readings":[{"at","mode":"seed|article|reassessment|audit","moves_pulse":bool,
                     "decision":"applied|no_change","position":float|null,"rationale":reader-safe,
                     "confidence":"high|medium|low","evidence_through","model","article_url":"/articles/<slug>"|null}]}
        // oldest first. "audit" = a blind read from evidence alone: kept as honest provenance, never moves
        // the Pulse (moves_pulse=false). Research-profile and claim ids are internal and omitted.
    intel.json = {"schema":"ohmega.intel.index/1","built_at",
        "daily":[{"domain","date","headline","theaters","url":"/geopolitics/<date>","data_url"}],   // newest first
        "briefs":[{"slug","title","bottom_line","theater_id","theater_name","as_of","direction","pace",
                   "url":"/intel/briefs/<slug>","data_url":"/data/briefs/<slug>.json"}],
        "theaters":[{"id","name","domain","heat","trend","coverage","brief_url"|null,"brief_data_url"|null}],
        "forecast_scorecard":{"resolved","void","open","brier","calibration":[...]},
        "forecasts_url":"/data/forecasts.json","changes_url":"/data/changes.json"}
    daily/<domain>/<YYYY-MM-DD>.json, daily/<domain>/latest.json (same content as the newest dated file)
        = the persisted ohmega.daily/1 record (shape above) minus the internal ``pulse_proposals``, plus
        "url" and "data_url".
    briefs/<slug>.json = the persisted ohmega.brief/1 record plus "url", "data_url"; each ``judgments[]``
        entry gains "id" = its stable forecast id (the id in forecasts.json).
    forecasts.json = {"schema":"ohmega.forecasts/1","as_of","scorecard":{...as above},
        "forecasts":[{"id":"fc_<12 hex>","statement","probability":0-100,"horizon":"YYYY-MM-DD","basis",
                      "resolves_yes_if","resolves_no_if","made_at","status":"open|yes|no|void","brief_slug",
                      "brief_url","brief_data_url","theater_id","theater",
                      "resolution":null|{"resolved_at","outcome","evidence"}}]}     // newest made first
    changes.json = {"schema":"ohmega.changes/1","window_days":30,"as_of":newest event "at"|"",
        "events":[{"type","at", ...}]}   // newest first; window = last 30 days by age, never by count
        // types: pulse_created {pulse_id,name,position,band}, pulse_moved {pulse_id,name,from,to,from_band,
        // to_band,band_changed}, brief_published {slug,title,theater}, daily_published {domain,date,headline},
        // forecast_made {forecast_id,statement,probability}, forecast_resolved {..., outcome}; each has
        // "url" and "data_url". Rebuilt statelessly from the stores on every publish. Needs the Pulse store.

Per-item files carry no build timestamp, so an unchanged item is byte-identical and is never rewritten.
Stale files (a Pulse retired, a report removed) are not deleted.

Theater dossiers (built by ``agents/intel/dossier.py``; a living page per theater, accumulated over every daily
report and brief). Written to ``content/intel/theaters/<theater_id>.json`` AND ``public/data/theaters/<theater_id>.json``,
plus ``theaters/index.json`` in both places. ``built_at`` is the newest input's timestamp (not the wall clock), so an
unchanged dossier is byte-identical::

    index = {"schema":"ohmega.dossier.index/1","built_at","theaters":[{"theater_id","name","domain","first_seen",
        "last_seen","days_covered","heat","coverage","escalation_direction","max_band","url":"/intel/theaters/<id>"}]}
        // most recently active first, then heat; max_band = most severe band among its Pulses ("" if none)
    dossier = {"schema":"ohmega.dossier/1","theater_id","name","domain","built_at","first_seen","last_seen",
      "days_covered":int,                      // daily reports covering it
      "primer":{"text","built_at"}|null,       // <=120 words of stable background (intel_store/primers/, reused <=7 days)
      "current":{"date","bottom_line","escalation":{"direction","pace"},"coverage","source":"daily|brief","url"}|null,
      "pulses":[{"id","name","situation","position","band","history":[{"at","position"}]}],   // highest first
      "escalation_history":[{"date","direction","pace"}],        // one per daily, oldest first
      "coverage_series":[{"day","count","editions"}],            // newest heat-board row
      "timeline":[{"date","headline","detail","where","verification","sources":[urls],"from":"/geopolitics/<date>"
                   |"/intel/briefs/<slug>"}],                    // newest first; near-duplicates merged (dossier_timeline.py)
      "places":[{"name","country","lat","lon","count","last_date"}],   // validated; strongest recency-weighted first
      "map": <geo.build_map spec>|null,        // points[n-1] is places[n-1]; each point also has "weight" 0-1
      "actors":[{"name","mentions","first","last"}],             // top 15
      "relations":[{"source","target","kind","count","last_date","note"}],
      "figures":[{"label","unit","series":[{"as_of","value","source"}]}],   // by label (date words removed) + unit
      "forecasts":[{"id","statement","probability","horizon","status","resolution":null|{"resolved_at","outcome","evidence"}}],
      "indicators":[{"signal","history":[{"date","status"}]}],   // by exact wording across briefs
      "statements":[{"who","role","said","quote","when","source"}],   // newest 12
      "on_record":[<on_record row as in the daily>],   // every statement its dailies/briefs showed, by id, newest first, <=150
      "links":[{"theater_id","name","link","date"}],             // cross-theater links from the daily summaries
      "reports":[{"date","url"}], "briefs":[{"slug","title","as_of","url"}]}   // newest first

Actors (built by ``actors_feed.py``; a power profile per state from the actors store): ``content/intel/actors/<ISO2>.json``
(``ohmega.actor/1``) + ``index.json`` (``ohmega.actor.index/1``), mirrored to ``public/data/actors/``. Which actors, the
semantic rule that finds them, and the shapes are documented in ``actors_feed.py``.

Rules: ``rationale`` is the latest APPLIED, non-blind influence's rationale for that pulse, made
reader-safe (claim ids stripped, ~400 chars at a word boundary). Situations that are not "active"
and pulses that are "dormant" are skipped. ``absolute_position`` is internal and never exported.
Situations list assessed ones first (most severe pulse first); pulses inside by position desc,
unassessed last.

Like the radar, the files are data, not markup — the site renders them.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.intel import dossier_store, forecasts, on_record, pulse_labels
from algent_backend.agent_system.agents.intel.brief import safe_name
from algent_backend.agent_system.agents.intel.contracts import coverage_label

from . import actors_feed, agent_feed, site_git
from .agent_feed import reader_safe  # noqa: F401  (re-exported: the contract owner's public helper)

INTEL_SUBDIR = ("content", "intel")
SCHEMA = "ohmega.intel/1"


def _rationale(store: Any, pulse_id: str) -> str:
    applied = [i for i in store.log(pulse_id) if i.decision == "applied" and i.mode != "blind"]
    return reader_safe(max(applied, key=lambda i: i.at).rationale) if applied else ""


def _pulse(store: Any, pulse: Any, label: dict) -> dict:
    st, d = store.state(pulse.id), pulse.definition
    return {"id": pulse.id, "name": pulse.name, **label, "question": d.question, "low_end": d.low_end,
            "high_end": d.high_end, "position": st.position, "band": st.band or "unassessed",
            "velocity_7d": st.velocity_7d, "velocity_30d": st.velocity_30d, "confidence": st.confidence,
            "last_assessed": st.last_assessed, "evidence_through": st.evidence_through,
            "history": [{"at": p.at, "position": p.position} for p in st.history],
            "rationale": _rationale(store, pulse.id)}


def _situations(store: Any) -> list[dict]:
    out, labels = [], pulse_labels.load()
    for sit in store.situations():
        if sit.status != "active":
            continue
        pulses = [_pulse(store, p, pulse_labels.display(labels, p.id, sit.title, p.name))
                  for p in store.pulses(sit.id) if p.status != "dormant"]
        pulses.sort(key=lambda p: (p["position"] is None, -(p["position"] or 0)))
        watches = [{"condition": w.condition, "why": w.why, "direction": w.expected_direction,
                    "horizon": w.horizon, "status": w.status}
                   for w in store.watches(sit.id) if w.status == "open"]
        out.append({"id": sit.id, "title": sit.title, "summary": sit.summary, "domain": sit.domain,
                    "pulses": pulses, "watches": watches})
    out.sort(key=lambda s: (not any(p["position"] is not None for p in s["pulses"]),
                            -max((p["position"] or 0 for p in s["pulses"]), default=0)))
    return out


def _read_all(folder: Path) -> list[dict]:
    out = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _daily_reports(intel_dir: Path) -> list[dict]:
    """Every persisted daily report, newest first (then by domain)."""
    rows = [r for folder in sorted((intel_dir / "daily").glob("*")) if folder.is_dir() for r in _read_all(folder)]
    return sorted(rows, key=lambda r: (r.get("date", ""), r.get("domain", "")), reverse=True)


def _forecasts(intel_dir: Path, theater_names: dict[str, str]) -> dict:
    """The desk's track record: the scorecard, what is still open, and how the latest calls came out."""
    rows = forecasts.current(intel_dir)
    open_ = sorted((f for f in rows if f["status"] == "open"), key=lambda f: f["horizon"])[:20]
    done = sorted((f for f in rows if f["status"] != "open"), key=lambda f: f["resolved_at"], reverse=True)[:20]
    return {"scorecard": forecasts.scorecard(intel_dir),
            "open": [{"statement": f["statement"], "probability": f["probability"], "horizon": f["horizon"],
                      "theater_name": theater_names.get(f["brief_slug"], ""), "brief_slug": f["brief_slug"]}
                     for f in open_],
            "resolved": [{"statement": f["statement"], "probability": f["probability"], "outcome": f["status"],
                          "resolved_at": f["resolved_at"], "evidence": f["evidence"]} for f in done]}


def build_snapshot(store: Any, intel_dir: Path, *, now: datetime | None = None) -> dict:
    """Everything the site shows of the desk, as of now. Pure read: nothing is written."""
    now = now or datetime.now(UTC)
    briefs = sorted(_read_all(intel_dir / "briefs"), key=lambda b: (b.get("as_of", ""), b.get("built_at", "")),
                    reverse=True)
    newest: dict[str, str] = {}
    for b in briefs:                                   # newest first, so the first one seen wins
        newest.setdefault(b.get("theater_id", ""), b["slug"])
    boards = sorted((intel_dir / "boards").glob("*.json")) if (intel_dir / "boards").is_dir() else []
    board = json.loads(boards[-1].read_text(encoding="utf-8")) if boards else {}
    theaters = {t["id"]: t for t in board.get("theaters", [])}
    rows = []
    for h in board.get("heat", []):                    # already hottest first
        t = theaters.get(h["theater_id"], {})
        rows.append({"id": h["theater_id"], "name": h.get("name") or t.get("name", ""),
                     "domain": t.get("domain", ""), "why": t.get("why", ""), "heat": h.get("heat", 0),
                     "trend": h.get("trend", ""), "coverage": coverage_label(h.get("trend", "")),
                     "recent": h.get("recent", 0), "prior": h.get("prior", 0),
                     "recent_share": h.get("recent_share", 0.0), "prior_share": h.get("prior_share", 0.0),
                     "first_seen": h.get("first_seen", ""), "series": h.get("series", []),
                     "brief": newest.get(h["theater_id"])})
    return {"schema": SCHEMA, "slug": now.astimezone(UTC).strftime("%Y-%m-%d-%H%M"),
            "built_at": now.isoformat(), "situations": _situations(store), "theaters": rows,
            "briefs": [{"slug": b["slug"], "title": b.get("title", ""), "bottom_line": b.get("bottom_line", ""),
                        "theater_id": b.get("theater_id", ""), "theater_name": b.get("theater_name", ""),
                        "as_of": b.get("as_of", ""), "direction": (b.get("escalation") or {}).get("direction", ""),
                        "pace": (b.get("escalation") or {}).get("pace", "")} for b in briefs],
            "forecasts": _forecasts(intel_dir, {b["slug"]: b.get("theater_name", "") for b in briefs}),
            "daily": [{"domain": r.get("domain", ""), "date": r.get("date", ""),
                       "headline": (r.get("summary") or {}).get("headline", ""),
                       "theaters": [{"id": t.get("theater_id", ""), "name": t.get("name", "")}
                                    for t in r.get("theaters") or []]} for r in _daily_reports(intel_dir)]}


def _write_if_changed(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _labelled(catalog: list[dict]) -> list[dict]:
    """Catalog rows with their display ``title`` and ``actors_iso2`` (cached label, else the fallback)."""
    labels = pulse_labels.load()
    return [{**row, **pulse_labels.display(labels, row["id"], row.get("situation", ""), row["name"])} for row in catalog]


def build_pulse_feed(store: Any, *, now: datetime | None = None) -> dict:
    """The agent-facing Pulse list (``public/data/pulses.json``): the registry catalog plus a reader-safe rationale."""
    from algent_backend.agent_system.agents.pulse import registry

    rows = [{**row, "rationale": _rationale(store, row["id"]), "data_url": agent_feed.pulse_data_url(row["id"])}
            for row in _labelled(registry.catalog(store))]
    return {"schema": "ohmega.pulses/1", "built_at": (now or datetime.now(UTC)).isoformat(), "pulses": rows}


def build_index(snapshot: dict) -> dict:
    """The compact agent index (``public/data/intel.json``) distilled from a snapshot."""
    return {"schema": "ohmega.intel.index/1", "built_at": snapshot["built_at"],
            "daily": [{**d, "url": agent_feed.daily_url(d["date"]),
                       "data_url": agent_feed.daily_data_url(d["domain"], d["date"])} for d in snapshot["daily"]],
            "briefs": [{**b, "url": agent_feed.brief_url(b["slug"]), "data_url": agent_feed.brief_data_url(b["slug"])}
                       for b in snapshot["briefs"]],
            "theaters": [{"id": t["id"], "name": t["name"], "domain": t["domain"], "heat": t["heat"],
                          "trend": t["trend"], "coverage": t["coverage"],
                          "brief_url": agent_feed.brief_url(t["brief"]) if t["brief"] else None,
                          "brief_data_url": agent_feed.brief_data_url(t["brief"]) if t["brief"] else None}
                         for t in snapshot["theaters"]],
            "forecast_scorecard": snapshot["forecasts"]["scorecard"],
            "forecasts_url": "/data/forecasts.json", "changes_url": "/data/changes.json"}


def build_dossiers(intel_dir: Path, store: Any = None) -> dict | None:
    """Every theater dossier plus the index (``{"theaters": {id: dossier}, "index": {...}}``), or None if they
    could not be built: the dossiers are a view onto stores that are already safe, so a fault in them must
    never cost the rest of the publish."""
    try:
        return dossier_store.build(intel_dir, store)
    except Exception as exc:  # noqa: BLE001
        print(f"[intel] dossiers not built: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
        return None


def build_agent_files(snapshot: dict, intel_dir: Path, store: Any = None,
                      dossiers: dict | None = None) -> dict[str, dict]:
    """Every agent-feed file as ``{path under public/data: payload}``. Pulse files and the changes feed need
    the Pulse store; without it only the store-independent files are built. ``dossiers``: the
    ``build_dossiers`` result when the caller already built it (it is built here otherwise)."""
    from algent_backend.agent_system.agents.pulse import registry

    now = datetime.fromisoformat(snapshot["built_at"])
    briefs, reports = _read_all(intel_dir / "briefs"), _daily_reports(intel_dir)
    files = {"intel.json": build_index(snapshot), "forecasts.json": agent_feed.forecasts_file(intel_dir, briefs),
             **agent_feed.brief_files(briefs), **agent_feed.daily_files(reports)}
    if store is not None:
        catalog = _labelled(registry.catalog(store))
        files["pulses.json"] = build_pulse_feed(store, now=now)
        files["changes.json"] = agent_feed.changes_file(store, intel_dir, catalog, reports, briefs, now)
        files.update(agent_feed.pulse_files(store, catalog))
    built = dossiers if dossiers is not None else build_dossiers(intel_dir, store)
    if built is not None:
        files.update(agent_feed.dossier_files(built))
    record = build_record()
    if record is not None:
        files["record.json"] = record
    return files


def build_record() -> dict | None:
    """The bounded statements ledger for ``/intel/record`` (``on_record.export``), or None when the ledger
    cannot be read: like the dossiers, a view onto a store that is already safe must not cost the publish."""
    try:
        return on_record.export()
    except Exception as exc:  # noqa: BLE001
        print(f"[intel] record not built: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
        return None


def write_intel(site_dir: Path, snapshot: dict, intel_dir: Path, store: Any = None) -> Path:
    """Write the snapshot and mirror every persisted brief and daily report into a site checkout (only what
    changed), plus the agent feed (``build_agent_files``) under ``public/data``; Pulse files and the changes
    feed need the Pulse store."""
    root = site_dir.joinpath(*INTEL_SUBDIR)
    path = root / "snapshots" / f"{snapshot['slug']}.json"
    _write_if_changed(path, snapshot)
    for record in _read_all(intel_dir / "briefs"):
        _write_if_changed(root / "briefs" / f"{record['slug']}.json", record)
    for record in _daily_reports(intel_dir):
        _write_if_changed(root / "daily" / safe_name(record["domain"]) / f"{record['date']}.json", record)
    built = build_dossiers(intel_dir, store)
    if built is not None:
        for tid, record in built["theaters"].items():
            _write_if_changed(root / "theaters" / f"{tid}.json", record)
        _write_if_changed(root / "theaters" / "index.json", built["index"])
    data = site_dir / "public" / "data"
    files = build_agent_files(snapshot, intel_dir, store, built)
    for rel, payload in files.items():
        _write_if_changed(data / rel, payload)
    for rel, payload in actors_feed.build_actor_files(built).items():        # the actor pages' data (see actors_feed.py)
        _write_if_changed(root / "actors" / rel, payload)
        _write_if_changed(data / "actors" / rel, payload)
    if "record.json" in files:                         # the site reads it at build time, like the other desk files
        _write_if_changed(root / "record.json", files["record.json"])
    return path


def publish_intel() -> dict[str, Any]:
    """Put the desk snapshot live on the site. Never raises — the desk's work is already stored."""
    if not site_git.publish_enabled():
        return {"published": False, "note": "site publishing disabled"}
    try:
        from algent_backend.agent_system.agents.intel.heat import store_dir
        from algent_backend.agent_system.agents.pulse.repository import pulse_store

        root = site_git.repo_root()
        worktree, note = site_git.ensure_worktree(root)
        if worktree is None:
            return {"published": False, "note": note}
        store = pulse_store()
        snapshot = build_snapshot(store, store_dir())
        path = write_intel(site_git.live_site_dir(root), snapshot, store_dir(), store)
        ok, pushed = site_git.commit_and_push(worktree, f"intel({path.stem}): desk snapshot")
        return {"published": ok, "slug": path.stem, "note": pushed}
    except Exception as exc:  # noqa: BLE001
        return {"published": False, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
