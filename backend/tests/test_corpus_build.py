"""The corpus index: deterministic ids, incremental watermarks, rebuild == incremental, entity resolution, every query. Small fixture stores per product."""

from __future__ import annotations

import gc
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from algent_backend import corpus
from algent_backend.agent_system.agents.pulse import Influence, Pulse, PulseDefinition, PulseStore, Situation
from algent_backend.agent_system.agents.research.profile import Claim, Entity, SignalProfile, SourceArtifact
from algent_backend.agent_system.agents.research.store import JsonProfileStore
from algent_backend.agent_system.agents.statements.contracts import Statement
from algent_backend.agent_system.agents.statements.store import append_statements
from algent_backend.corpus import schema
from algent_backend.corpus.query import Corpus
from algent_backend.instruments import store as inst_store
from algent_backend.instruments.contracts import Observation
from algent_backend.lookahead import contracts as cal_contracts
from algent_backend.lookahead import store as cal_store
from algent_backend.sanctions import store as sx_store
from algent_backend.sanctions.contracts import SanctionsEvent

STORES = {"ALGENT_INTEL_STORE": "intel", "ALGENT_PULSE_STORE": "pulse", "ALGENT_PROFILE_STORE": "profiles", "ALGENT_STATEMENTS_STORE": "statements",
          "ALGENT_SANCTIONS_STORE": "sanctions", "ALGENT_CALENDAR_STORE": "calendar", "ALGENT_INSTRUMENTS_STORE": "instruments",
          "ALGENT_ACTORS_STORE": "actors", "ALGENT_GEOLEDGER_STORE": "geo", "ALGENT_MARKETS_STORE": "markets", "ALGENT_MARITIME_STORE": "maritime",
          "ALGENT_AI_BENCHMARKS_STORE": "bench", "ALGENT_CORPUS_STORE": "corpus", "ALGENT_CONFLICT_STORE": "conflict", "ALGENT_GNSS_STORE": "gnss", "ALGENT_ELECTIONS_STORE": "elections"}
THR = "thr_hormuz_crisis"


@pytest.fixture()
def record(tmp_path, monkeypatch) -> Path:
    for env, name in STORES.items():
        monkeypatch.setenv(env, str(tmp_path / name))
    from algent_backend.ops.products import locations
    monkeypatch.setattr(locations, "site_articles", lambda: tmp_path / "no-articles")
    _daily(tmp_path / "intel", "2026-10-05")
    _profile()
    _statements()
    _pulses()
    _sanction()
    _calendar()
    inst_store.append("chk_hormuz_transits", [Observation(series_id="chk_hormuz_transits", period=f"2026-10-0{d}", value=100 + d, fetched_at="2026-10-06T00:00:00+00:00",
                                                          source_url="https://portwatch.imf.org/") for d in range(1, 5)])
    return tmp_path


def _daily(root: Path, day: str, headline: str = "Tehran answers Washington over Hormuz") -> None:
    folder = root / "daily" / "geopolitics"
    folder.mkdir(parents=True)
    rec = {"schema": "ohmega.daily/1", "domain": "geopolitics", "date": day, "researched": True,
           "summary": {"headline": "Hormuz stays shut", "the_day": ["Iran held the strait."]},
           "theaters": [{"theater_id": THR, "name": "Hormuz crisis", "pulses": [{"id": "pls_hormuz_flow", "name": "Flow"}],
                         "bottom_line": "Iran keeps the Strait of Hormuz closed.", "since_yesterday": ["talks stalled"], "outlook": "Closure persists.",
                         "watch_next": ["mediators"], "key_figures": [{"label": "Oil disrupted", "value": 6.0, "unit": "mb/d", "as_of": day, "source": "https://iea.org/x"}],
                         "developments": [{"headline": headline, "detail": "Foreign Minister Araghchi awaited a reply via Oman.", "when": day, "where": "Tehran",
                                           "actors": ["Iran", "United States"], "verification": "researched", "sources": ["https://aljazeera.com/hormuz"],
                                           "place": {"name": "Tehran", "country": "Iran", "lat": 35.7, "lon": 51.4}}]}],
           "cross_theater": [], "watch": [], "quiet": []}
    (folder / f"{day}.json").write_text(json.dumps(rec), encoding="utf-8")


def _profile() -> None:
    p = SignalProfile(id="prof_hormuz", title="Hormuz closure", summary="Iran closed the strait.", as_of="2026-10-04", generated_at="2026-10-04T08:00:00+00:00",
                      source_ledger=[SourceArtifact(id="src_1", url="https://reuters.com/hormuz", title="Reuters on Hormuz", retrieved_at="2026-10-04")],
                      claim_ledger=[Claim(id="clm_1", text="Iran closed the Strait of Hormuz to tanker traffic.", status="confirmed", grounding="snapshotted",
                                          supported_by=["src_1"])],
                      entities=[Entity(id="e1", name="Iran", type="org", role="closer"), Entity(id="e2", name="IRGC Navy", type="org", role="enforcer")])
    JsonProfileStore().save(p)


def _statements() -> None:
    mk = lambda i, who, what: Statement(id=f"st_{i}", speaker=who, role="Foreign Minister", affiliation="Iran", date="2026-10-03", quote="", paraphrase=what,  # noqa: E731
                                        about=["United States"], topics=["Hormuz"], signal="threat", stance=-1, significance="reopening conditions",
                                        source_url=f"https://example.org/{i}", transcript_id="t1")
    append_statements([mk(1, "Abbas Araghchi", "Iran will not back down on Hormuz conditions."), mk(2, "Abbas Araghchi", "A seven day roadmap was offered.")])


def _pulses() -> None:
    s = PulseStore()
    s.save_situation(Situation(id="sit_hormuz", title="Hormuz", entities=["Iran"], pulse_ids=["pls_hormuz_flow"]))
    s.create_pulse(Pulse(id="pls_hormuz_flow", situation_id="sit_hormuz", name="Flow", definitions=[PulseDefinition(question="How blocked is the strait?")]))
    s.append(Influence(key="inf_1", pulse_id="pls_hormuz_flow", at="2026-10-04T08:00:00+00:00", mode="reassess", definition_version=1, proposed_position=80.0,
                       decision="applied", rationale="Traffic is a fraction of normal."))


def _sanction() -> None:
    sx_store.append_events([SanctionsEvent(id="sx1", source="ofac", action="designated", date="2026-10-02", observed_on="2026-10-03", ref="9", name="MAR AZUL",
                                           type="vessel", programmes=["IRAN"], countries=["IR"], imo="7406784", flag="PA", owner="Samir Navegacion",
                                           source_url="https://ofac.treasury.gov/")])


def _calendar() -> None:
    item = cal_contracts.make("summit", "corpus", "2026-10-20", "Gulf security summit", "https://example.org/summit", countries=["IR"])
    cal_store._append([item])


def snapshot(db_path: Path) -> dict[str, list]:
    db = schema.connect(db_path)
    out = {}
    for t in ("entities", "entity_alias", "documents", "claims", "sources", "claim_sources", "mentions", "relations", "observations", "events", "event_actors"):
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})") if c[1] != "ingested_at"]
        out[t] = [tuple(r) for r in db.execute(f"SELECT {','.join(cols)} FROM {t} ORDER BY 1,2,3")]
    db.close()
    return out


def test_full_build_ingests_every_product(record):
    r = corpus.build(full=True)
    assert not r["errors"], r["errors"]
    rows = r["rows"]
    assert rows["documents"] >= 7 and rows["claims"] >= 2 and rows["observations"] >= 6 and rows["events"] >= 3
    with Corpus.open() as c:
        s = c.stats()
        assert s["documents_by_kind"]["statement"] == 2 and s["documents_by_kind"]["daily"] == 1
        assert s["rows_by_product"]["profiles"] == 1


def test_ids_are_deterministic_and_rebuild_equals_rebuild(record):
    corpus.build(full=True)
    first = snapshot(corpus.db_file())
    corpus.build(full=True)
    assert snapshot(corpus.db_file()) == first


def test_incremental_equals_full_and_touches_only_changes(record):
    corpus.build(full=True)
    again = corpus.build()
    assert all(s["skipped"] for s in again["sources"].values())                 # watermarks: nothing re-read
    _daily_second_day(record)
    inc = corpus.build()
    assert inc["sources"]["dailies"]["changed"] == 1 and inc["sources"]["statements"]["skipped"]
    incremental = snapshot(corpus.db_file())
    corpus.build(full=True)
    assert snapshot(corpus.db_file()) == incremental                            # rebuild equals incremental


def _daily_second_day(root: Path) -> None:
    folder = root / "intel" / "daily" / "geopolitics"
    rec = json.loads((folder / "2026-10-05.json").read_text(encoding="utf-8"))
    rec["date"] = "2026-10-06"
    rec["theaters"][0]["developments"][0].update(headline="Oman carries a message to Washington", when="2026-10-06")
    (folder / "2026-10-06.json").write_text(json.dumps(rec), encoding="utf-8")


def test_changed_unit_is_replaced_and_removed_unit_is_forgotten(record):
    corpus.build(full=True)
    path = record / "intel" / "daily" / "geopolitics" / "2026-10-05.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["theaters"][0]["developments"][0]["headline"] = "Tehran rejects the roadmap"
    path.write_text(json.dumps(rec), encoding="utf-8")
    corpus.build()
    with Corpus.open() as c:
        titles = [e["title"] for e in c.about("Hormuz crisis")["events"]]
        assert titles == ["Tehran rejects the roadmap"]
    path.unlink()
    corpus.build()
    with Corpus.open() as c:
        assert c.stats()["documents_by_kind"].get("daily") is None


def test_since_only_considers_recent_units_and_never_deletes(record):
    corpus.build(full=True)
    shutil.rmtree(record / "intel" / "daily")
    r = corpus.build(since="2026-10-01")
    assert r["sources"]["dailies"]["removed"] == 0
    with Corpus.open() as c:
        assert c.stats()["documents_by_kind"]["daily"] == 1


def test_entity_resolution_countries_aliases_and_unresolved(record):
    corpus.build(full=True)
    with Corpus.open() as c:
        assert c.entity("Iran")["entity"]["id"] == "country:IR"
        assert c.entity("Islamic Republic of Iran")["entity"]["id"] == "country:IR"
        about = c.about("United States", kinds={"event"})
        assert about["events"], "the free-text actor 'United States' resolved to the country"
        names = {u["name"] for u in c.unresolved(100)}
        assert "IRGC Navy" not in names                                         # declared by the profile: resolvable
        assert "Samir Navegacion" in names and "Samir Navegacion" not in {e["name"] for e in c.db.execute("SELECT name FROM entities").fetchall()}
        assert c.entity("no such thing") is None


def test_queries(record):
    corpus.build(full=True)
    with Corpus.open() as c:
        prof = c.entity("Strait of Hormuz")
        assert prof is None or prof["entity"]["kind"] in {"place", "topic"}
        iran = c.entity("Iran")
        assert iran["counts"]["claims"] >= 1 and iran["situations"] and iran["timeline"]
        ab = c.about("Iran", since="2026-10-01")
        assert ab["documents"] and ab["claims"][0]["sources"][0]["url"] == "https://reuters.com/hormuz"
        assert c.about("Iran", since="2026-12-01")["documents"] == []
        tl = c.timeline(f"situation:{THR}")
        assert [t["date"] for t in tl] == sorted(t["date"] for t in tl) and tl
        hits = c.search("strait closed tanker traffic")
        assert hits[0]["type"] in {"claim", "document", "event"} and hits[0]["sources"] or hits
        assert c.search("zzzznothing") == []
        rel = c.related("Iran")
        assert rel and all(r["entity"] != "country:IR" for r in rel)
        ser = c.series("pulse.*")
        assert ser[0]["basis"] == "model" and ser[0]["n"] == 1
        flow = c.series("chk_hormuz_transits")
        assert flow[0]["n"] == 4 and flow[0]["basis"] == "official"
        assert c.series("country:IR", metric="nope") == []


def test_like_fallback_when_fts5_is_missing(record, monkeypatch):
    monkeypatch.setattr(schema, "fts5_available", lambda: False)
    corpus.build(full=True)
    with Corpus.open() as c:
        assert c.stats()["fts"] == "like"
        assert c.search("Hormuz")


def test_a_broken_store_is_reported_not_fatal(record, monkeypatch):
    from algent_backend.corpus.sources import statements as st_src

    def boom():
        raise OSError("disk")
    monkeypatch.setattr(st_src.st, "load_statements", boom)
    r = corpus.build(full=True)
    assert any("statements" in e for e in r["errors"]) and r["rows"]["documents"] > 0


def test_retrieval_uses_the_index_and_falls_back_without_one(record, monkeypatch):
    from algent_backend.retrieval import search as rsearch

    corpus.build(full=True)
    idx = rsearch.Index.build(date(2026, 10, 6), embedder=None, claims=False)
    assert idx.ranker is not None
    hits = idx.search("Hormuz closed", k=5)
    assert hits and hits[0].id.startswith(("daily:", "statement:", "sanction:", "calendar:"))
    del idx
    gc.collect()                                                                # release the read-only connection (Windows will not delete an open file)
    shutil.rmtree(record / "corpus")
    plain = rsearch.Index.build(date(2026, 10, 6), embedder=None, claims=False)
    assert plain.ranker is None and plain.search("Hormuz closed", k=5)
