"""The attack log and the GPS-interference zones as products of the new architecture: their registry entries, the corpus adapters, the view blocks (country, situation,
globe HUD), the doctor checks and the stats registry entries the site needs. Offline."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from test_conflict import row as gdelt_row
from views_fixture import context

from algent_backend import corpus
from algent_backend.conflict import publish as cx_publish
from algent_backend.conflict import store as cx_store
from algent_backend.conflict.contracts import ConflictEvent, event_id
from algent_backend.conflict.sources import gdelt
from algent_backend.corpus import schema
from algent_backend.gnss import publish as gx_publish
from algent_backend.gnss import store as gx_store
from algent_backend.gnss.contracts import Zone
from algent_backend.ops import doctor
from algent_backend.ops.products import validate, views
from algent_backend.views import country, graph, hud, situation

REPO = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 23)
DAY = TODAY.isoformat()


@pytest.fixture()
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_CONFLICT_STORE", str(tmp_path / "cx"))
    monkeypatch.setenv("ALGENT_GNSS_STORE", str(tmp_path / "gx"))
    monkeypatch.setenv("ALGENT_CORPUS_STORE", str(tmp_path / "corpus"))
    # one machine event barely supported (stays out of the index), one well supported, one researcher-coded with a casualty figure
    cx_store.append(gdelt.parse([gdelt_row(day="20261023", cc="IR", feature="F1", arts="9", place="Bandar Abbas, Hormozgan, Iran"),
                                 gdelt_row(day="20261023", cc="IR", feature="F2", arts="2", place="Qeshm, Hormozgan, Iran")], "2026-10-23T08:00:00+00:00"))
    cx_store.append([ConflictEvent(id=event_id("acled", "A1", DAY), source="acled", date=DAY, observed_at="t", type="airstrike", country="IR", place="Bushehr", lat=28.9, lon=50.8,
                                   fatalities=4, coding="curated", confidence="high", basis="third_party", actor1="Unknown", urls=["https://acleddata.com/x"])])
    base = dict(date=DAY, size_deg=1.0, country="IR", aircraft=40)
    ours = Zone(id="gz1", source="ohmega_adsb", cell="27,56", lat=27.5, lon=56.5, severity="high", degraded_share=0.4, basis="our_estimate", baseline_since="2026-10-10", flag="new",
                cross_check="agrees", **base)
    quiet = Zone(id="gz2", source="ohmega_adsb", cell="30,50", lat=30.5, lon=50.5, severity="low", degraded_share=0.05, basis="our_estimate", baseline_since="2026-10-10", **base)
    gx_store.save_zones(DAY, {"date": DAY, "generated_at": f"{DAY}T06:00:00+00:00", "baseline_since": "2026-10-10", "baseline_days": 13, "samples": 24,
                              "zones": [ours.model_dump(), quiet.model_dump()], "gpsjam": []})
    return tmp_path


# ── the registry ─────────────────────────────────────────────────────────────────────────────────
def test_both_products_are_registered_with_budget_retention_jobs_contracts_and_routes():
    assert validate.validate() == []
    cx, gx = views.by_id("conflict"), views.by_id("gnss")
    assert [s.name for s in cx.stores] == ["conflict_store"] and cx.stores[0].budget.fail_mb > cx.stores[0].budget.warn_mb > cx.stores[0].budget.steady_mb
    assert [s.name for s in gx.stores] == ["gnss_store"] and gx.stores[0].backed_up and gx.irreplaceable and not cx.irreplaceable
    assert all(r.kind == "prune" and r.by == "on-write" for r in cx.retention + gx.retention)
    assert {j.name for j in cx.job_list()} == {"conflict", "reliefweb", "conflict-daily"} and [j.name for j in gx.job_list()] == ["gnss"]
    assert all(not j.lock for j in (*cx.job_list(), *gx.job_list())), "collectors on short cadences must not wait behind a daily"
    assert views.job("conflict")[1].when() == "*:4/15" and views.job("gnss")[1].when() == "*:12"
    assert {c.schema for c in cx.contracts + gx.contracts} == {"ohmega.conflict.recent", "ohmega.conflict.country", "ohmega.gnss.latest", "ohmega.gnss.overlay"}
    assert cx.site_routes == ("/intel/attacks",) and gx.site_routes == ("/intel/gnss",)
    assert gx.job_list()[0].argv == ("gnss", "run") and "gdelt" in views.job("conflict")[1].argv


def test_the_keyed_sources_are_inactive_until_their_keys_exist(stores):
    st = cx_publish.source_state()
    assert not st["acled"]["active"] and st["acled"]["keyed"] and not st["gdelt"]["keyed"]
    cx_store.save_status("gdelt", last_ok="2026-10-23T08:00:00+00:00")
    cx_store.save_status("acled", needs_key="ALGENT_ACLED_EMAIL")
    st = cx_publish.source_state()
    assert st["gdelt"]["active"] and not st["acled"]["active"]


# ── the corpus ───────────────────────────────────────────────────────────────────────────────────
def test_the_corpus_gets_attack_events_with_provenance_and_zone_series(stores):
    report = corpus.build(full=True, only=["actors", "conflict", "gnss"])
    assert not report["errors"], report["errors"]
    db = schema.connect(corpus.db_file())
    events = {r[0]: r for r in db.execute("SELECT id, kind, date, status, place, lat, lon, detail FROM events WHERE id LIKE 'event:%'")}
    kinds = sorted(r[1] for r in events.values())
    assert kinds == ["conflict_airstrike", "conflict_armed_clash", "gnss_new"]                     # the 2-article machine event is not evidence: it stays out
    acled = next(r for r in events.values() if r[1] == "conflict_airstrike")
    assert acled[3] == "curated" and acled[5] == 28.9 and "oded by researchers" in acled[7] and "4 killed per the source" in acled[7] and "Basis: third_party" in acled[7]
    gdelt_ev = next(r for r in events.values() if r[1] == "conflict_armed_clash")
    assert gdelt_ev[3] == "machine" and "software" in gdelt_ev[7] and "Machine-coded" in gdelt_ev[7] and "Casualties not stated" in gdelt_ev[7]
    docs = {r[0]: r for r in db.execute("SELECT id, kind, status, url, body FROM documents WHERE kind='conflict_event'")}
    assert len(docs) == 2 and all("Source:" in r[4] for r in docs.values())
    obs = {(r[0], r[1]): (r[2], r[3]) for r in db.execute("SELECT metric, ts, value, basis FROM observations WHERE metric LIKE 'gnss.%'")}
    assert obs[("gnss.zones", DAY)] == (2.0, "our_derived") and obs[("gnss.zones.high", DAY)][0] == 1.0
    again = corpus.build(only=["actors", "conflict", "gnss"])
    assert all(s["skipped"] for s in again["sources"].values())                                    # watermarks: an untouched store is not even read
    db.close()


def test_a_pruned_shard_leaves_the_corpus_on_the_next_full_build(stores):
    corpus.build(full=True, only=["actors", "conflict"])
    cx_store.shard_path(DAY).unlink()
    corpus.build(full=True, only=["actors", "conflict"])
    db: sqlite3.Connection = schema.connect(corpus.db_file())
    assert db.execute("SELECT COUNT(*) FROM events WHERE kind LIKE 'conflict_%'").fetchone()[0] == 0
    db.close()


# ── views ────────────────────────────────────────────────────────────────────────────────────────
def _ctx():
    ctx = context()
    ctx.tables._docs.update({**cx_publish.documents(TODAY), **gx_publish.documents(TODAY)})
    return ctx


def test_the_country_view_carries_attacks_and_zones_with_their_counts(stores):
    ctx = _ctx()
    g = graph.shared(ctx)
    v = country.build_one(ctx, "IR", g, country.briefs_by_country(ctx)).body
    assert v["attacks"]["total"] == 3 and v["attacks"]["rows"][0]["source"] == "acled" and v["attacks"]["rows"][0]["url"] == "https://acleddata.com/x"
    assert v["attacks"]["since"] and v["attacks"]["sources"]["acled"] is False and "coverage_note" not in v["attacks"]["rows"][0]
    assert v["gnss"]["total"] == 2 and v["gnss"]["zones"][0]["flag"] == "new" and v["gnss"]["baseline_since"] == "2026-10-10"
    assert v["panel"]["counts"]["attacks"] == 3 and v["panel"]["counts"]["jamming"] == 2
    assert country.build_one(ctx, "FR", g, {}).body["attacks"] is None                              # a country with nothing reported has no block, not a zero
    assert not country.build_one(ctx, "IR", g, {}).over_budget()


def test_the_situation_view_reads_the_events_over_its_main_states(stores):
    ctx = _ctx()
    v = next(v for v in situation.build(ctx) if v.key == "situation/thr_hormuz").body
    sig = v["signals"]
    assert "IR" in sig["states"] and sig["attacks"]["total"] == 3 and sig["attacks"]["rows"][0]["source"] == "acled" and sig["gnss"]["total"] == 2
    quiet = next(v for v in situation.build(context()) if v.key == "situation/thr_hormuz").body
    assert quiet["signals"] is None


def test_the_hud_view_has_recent_attacks_and_zones_or_nothing(stores):
    ctx = _ctx()
    h = hud.build(ctx)[0].body["hud"]
    assert h["attacks"]["total"] == 3 and h["attacks"]["days"] == 3 and h["gnss"]["zones"][0]["id"] == "gz1"
    assert hud.build(context())[0].body["hud"]["attacks"] is None and hud.build(context())[0].body["hud"]["gnss"] is None


# ── the doctor ───────────────────────────────────────────────────────────────────────────────────
def test_the_doctor_is_quiet_on_a_machine_without_the_stores_and_flags_a_stale_collector(stores, tmp_path, monkeypatch):
    assert doctor.check_conflict()["conflict"]["status"] == "ok" and doctor.check_gnss()["gnss"]["status"] == "ok"
    cx_store.save_status("gdelt", last_ok="2020-01-01T00:00:00+00:00")
    gx_store.save_status("ohmega_adsb", last_ok="2020-01-01T00:00:00+00:00")
    assert doctor.check_conflict()["conflict"]["status"] == "warn" and doctor.check_gnss()["gnss"]["status"] == "warn"
    cx_store.save_status("acled", needs_key="ALGENT_ACLED_EMAIL")
    assert "acled" not in doctor.check_conflict()["conflict"]["detail"].split("stale:")[-1]         # a key never set is not a fault


# ── the site's stats registry ────────────────────────────────────────────────────────────────────
def _stats() -> dict[str, dict]:
    """Each ``def({ ... })`` entry of lib/stats/registry.ts: id, basis, whether it renders as a minimum, its surfaces (read as text, like scripts/stats-audit.mjs)."""
    text = (REPO / "sites" / "ohmega-monster" / "lib" / "stats" / "registry.ts").read_text(encoding="utf-8")
    out = {}
    for chunk in text.split("def({")[1:]:
        sid, basis = re.search(r'\bid:\s*"([^"]+)"', chunk), re.search(r'\bbasis:\s*"([^"]+)"', chunk)
        if sid and basis:
            surf = re.search(r"surfaces:\s*\[([^\]]*)\]", chunk)
            out[sid.group(1)] = {"basis": basis.group(1), "minimum": "minimum: true" in chunk or basis.group(1) in ("our_count", "machine_coded"),
                                 "surfaces": re.findall(r'"([^"]+)"', surf.group(1) if surf else "")}
    return out


def test_every_number_the_event_pages_show_has_a_stats_entry():
    ours = {k: v for k, v in _stats().items() if k.startswith(("attacks_", "gnss_"))}
    assert {"attacks_events", "attacks_machine", "attacks_curated", "attacks_countries", "gnss_zones", "gnss_high", "gnss_flagged", "gnss_gpsjam"} <= set(ours)
    assert ours["attacks_machine"]["basis"] == "machine_coded" and ours["gnss_zones"]["basis"] == "our_derived" and ours["gnss_flagged"]["basis"] == "our_derived"
    for k in ("attacks_events", "attacks_machine", "attacks_countries", "gnss_zones", "gnss_high", "gnss_flagged"):
        assert ours[k]["minimum"], f"{k}: counts of what we only partly see are minimums and must render as one"
    site = REPO / "sites" / "ohmega-monster"
    for k, v in ours.items():
        assert v["surfaces"] and all((site / s).exists() for s in v["surfaces"]), f"{k}: a surface it names does not exist"


def test_the_site_renders_every_event_number_through_the_registry():
    site = REPO / "sites" / "ohmega-monster"
    for rel, ids in (("components/conflict/AttackLog.tsx", ("attacks_events", "attacks_machine", "attacks_curated", "attacks_countries")),
                     ("components/conflict/GnssView.tsx", ("gnss_zones", "gnss_high", "gnss_flagged", "gnss_gpsjam")),
                     ("components/hud/panels/AttacksPanel.tsx", ("attacks_events",)), ("components/hud/panels/GnssPanel.tsx", ("gnss_zones",))):
        text = (site / rel).read_text(encoding="utf-8")
        assert all(f'id="{i}"' in text for i in ids), rel
    used = set()
    for folder in ("app", "components", "lib"):
        for p in (site / folder).rglob("*.ts*"):
            used |= set(re.findall(r'\bid[:=]\s*"((?:attacks|gnss)_[a-z]+)"', p.read_text(encoding="utf-8")))
    assert used and used <= set(_stats())
