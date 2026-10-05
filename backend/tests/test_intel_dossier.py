"""Theater dossiers: aggregation over a synthetic store, the timeline merge rule, primers, and the files."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from algent_backend.agent_system.agents.intel import dossier, dossier_store, forecasts, primers
from algent_backend.agent_system.agents.intel.contracts import Judgment
from algent_backend.agent_system.agents.pulse import PulseStore
from algent_backend.agent_system.agents.pulse.contracts import (
    Influence,
    Pulse,
    PulseDefinition,
    Situation,
)
from algent_backend.publishing import intel_page

TID, OTHER = "thr_alpha", "thr_bravo"
S1, S2, S3 = "https://wire.example/1", "https://wire.example/2", "https://wire.example/3"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _dev(headline, detail="", when="", verification="reported", sources=(), place=None, actors=(), statements=()):
    return {"headline": headline, "detail": detail, "when": when, "where": "", "actors": list(actors),
            "statements": list(statements), "significance": "", "verification": verification,
            "sources": list(sources), "place": place}


def _section(tid, name, devs, *, direction="rising", pace="gradual", figures=(), pulses=(), bottom="BL"):
    return {"theater_id": tid, "name": name, "temperature": {"coverage": "steady coverage"},
            "escalation": {"direction": direction, "pace": pace}, "pulses": list(pulses), "bottom_line": bottom,
            "developments": devs, "key_figures": list(figures), "context": [], "since_yesterday": []}


def _report(day, sections, cross=()):
    return {"schema": "ohmega.daily/1", "domain": "geopolitics", "date": day, "built_at": f"{day}T20:00:00+00:00",
            "theaters": sections, "cross_theater": list(cross), "summary": {"headline": "h", "the_day": []}}


def _brief(slug, tid, as_of, *, timeline=(), relations=(), indicators=(), pulses=(), direction="steady"):
    return {"schema": "ohmega.brief/1", "slug": slug, "as_of": as_of, "built_at": f"{as_of}T09:00:00+00:00",
            "theater_id": tid, "theater_name": "Alpha war", "title": f"Brief {slug}", "bottom_line": f"brief {as_of}",
            "escalation": {"direction": direction, "pace": "flat"}, "timeline": list(timeline),
            "relations": list(relations), "indicators": list(indicators), "pulses": list(pulses)}


TRYP_A = ("Largest combined strike on Kyiv energy system damages Trypillya plant",
          "Russia launched a massive combined drone and missile strike overnight, damaging the Trypillya thermal plant "
          "near Kyiv and cutting power to thousands.")
TRYP_B = ("Massive combined strike opens winter energy campaign, damages Trypillya plant",
          "A combined drone and missile strike overnight hit the Trypillya thermal plant near Kyiv, starting a "
          "winter campaign against energy; power was cut to thousands of homes.")


def _inputs(**over):
    place = {"name": "Kyiv", "country": "Ukraine", "lat": 50.45, "lon": 30.52}
    reports = [
        _report("2026-09-29", [
            _section(TID, "Alpha war", [
                _dev(*TRYP_A, when="2026-09-28", sources=[S1, "javascript:alert(1)"], place=place,
                     actors=["Russia", "Ukraine"],
                     statements=[{"who": "Zelensky", "role": "President", "said": "We will hold", "quote": False,
                                  "when": "2026-09-28", "source": S1}]),
                _dev("Border talks stall over prisoner swap", "Delegations met and parted without a deal.",
                     when="2026-09-29", verification="researched", sources=[S3], actors=["Russia"])],
                direction="rising", pace="fast",
                figures=[{"label": "drones launched Sept 28-29", "value": 100.0, "unit": "drones", "as_of": "2026-09-29",
                          "source": S1}],
                pulses=[{"id": "pls_a", "name": "Strike Intensity", "position": 50.0, "band": "elevated"}]),
            _section(OTHER, "Bravo dispute", [_dev("Bravo thing", when="2026-09-29")])],
            cross=[{"theaters": ["Alpha war", "Bravo dispute"], "link": "Alpha war -> Bravo dispute: shared actor."}]),
        _report("2026-09-30", [
            _section(TID, "Alpha war", [
                _dev(*TRYP_B, when="2026-09-28", verification="researched", sources=[S2],
                     place={"name": "Kyiv", "country": "Ukraine", "lat": 50.4501, "lon": 30.5234}),
                _dev("Border talks stall over prisoner swap", "Same again.", when="2026-09-29")],
                direction="steady", pace="flat",
                figures=[{"label": "drones launched Oct 1", "value": 140.0, "unit": "drones", "as_of": "2026-09-30",
                          "source": S2}],
                pulses=[{"id": "pls_a", "name": "Strike Intensity", "position": 55.0, "band": "elevated"}])]),
    ]
    briefs = [
        _brief("2026-09-27-alpha", TID, "2026-09-27", pulses=["Strike Intensity", "Gone Pulse"],
               timeline=[{"date": "2026-02-24", "what": "Invasion began", "verification": "reported", "source": "src_abc123"},
                         {"date": "2026-09-27", "what": "Winter energy campaign announced", "verification": "researched",
                          "source": S1}],
               relations=[{"source": "Russia", "target": "Ukraine", "kind": "strikes", "note": "old", "date": "2026-09-26"},
                          {"source": "src_e680b069f1", "target": "Ukraine", "kind": "strikes", "note": "x"},
                          {"source": "A -> B ; C -> D", "target": "Ukraine", "kind": "other", "note": "blob"}],
               indicators=[{"signal": "Truce announced", "status": "not seen"},
                           {"signal": "Bridge strike", "status": "emerging"}]),
        _brief("2026-10-01-alpha", TID, "2026-10-01", direction="rising",
               relations=[{"source": "Russia", "target": "Ukraine", "kind": "strikes", "note": "new", "date": "2026-10-01"}],
               indicators=[{"signal": "Truce announced", "status": "emerging"}]),
    ]
    base = dict(reports=reports, briefs=briefs,
                boards=[{"theaters": [{"id": TID, "name": "Alpha war (board)", "domain": "geopolitics"}],
                         "heat": [{"theater_id": TID, "heat": 7.5, "trend": "heating", "first_seen": "2026-09-20",
                                   "series": [{"day": "2026-09-30", "count": 3, "editions": 2}]}]}],
                registry={TID: {"name": "Alpha war", "domain": "geopolitics", "first_seen": "2026-09-25",
                                "last_seen": "2026-10-02"}},
                pulses=[{"id": "pls_a", "name": "Strike Intensity", "situation": "Alpha situation", "position": 62.0,
                         "band": "severe", "history": [{"at": "2026-10-02T10:00:00+00:00", "position": 62.0}]},
                        {"id": "pls_other", "name": "Unrelated", "position": 10.0, "band": "calm", "history": []}])
    base.update(over)
    return dossier.Inputs(**base)


def _alpha(**over):
    return dossier.build_all(_inputs(**over))["theaters"][TID]


def test_every_theater_with_a_section_or_brief_gets_a_dossier() -> None:
    built = dossier.build_all(_inputs(briefs=[_brief("2026-10-01-solo", "thr_solo", "2026-10-01")]))
    assert set(built["theaters"]) == {TID, OTHER, "thr_solo"}
    assert built["theaters"]["thr_solo"]["days_covered"] == 0 and built["theaters"]["thr_solo"]["reports"] == []


def test_identity_dates_and_counts() -> None:
    d = _alpha()
    assert d["schema"] == "ohmega.dossier/1" and d["name"] == "Alpha war" and d["domain"] == "geopolitics"
    assert d["first_seen"] == "2026-09-20" and d["last_seen"] == "2026-10-02" and d["days_covered"] == 2
    assert [r["date"] for r in d["reports"]] == ["2026-09-30", "2026-09-29"]
    assert d["reports"][0]["url"] == "/geopolitics/2026-09-30"
    assert [(b["slug"], b["url"]) for b in d["briefs"]][0] == ("2026-10-01-alpha", "/intel/briefs/2026-10-01-alpha")
    assert d["built_at"] == "2026-10-02T10:00:00+00:00"          # newest input (a Pulse reading), never the clock
    assert d["coverage_series"] == [{"day": "2026-09-30", "count": 3, "editions": 2}]


def test_current_is_the_newest_of_daily_and_brief() -> None:
    d = _alpha()                                                     # daily 09-30 vs brief 10-01
    assert d["current"]["source"] == "brief" and d["current"]["date"] == "2026-10-01"
    assert d["current"]["url"] == "/intel/briefs/2026-10-01-alpha" and d["current"]["escalation"]["direction"] == "rising"
    assert d["current"]["coverage"] == "rising coverage"             # board row: trend "heating"
    older = _alpha(briefs=_inputs().briefs[:1])
    assert older["current"]["source"] == "daily" and older["current"]["date"] == "2026-09-30"
    assert older["current"]["escalation"] == {"direction": "steady", "pace": "flat"}
    assert older["current"]["coverage"] == "steady coverage"
    tie = _alpha(briefs=[_brief("2026-09-30-alpha", TID, "2026-09-30")])
    assert tie["current"]["source"] == "daily"                       # same day: the daily wins


def test_escalation_history_one_per_daily_oldest_first() -> None:
    assert _alpha()["escalation_history"] == [{"date": "2026-09-29", "direction": "rising", "pace": "fast"},
                                              {"date": "2026-09-30", "direction": "steady", "pace": "flat"}]


def test_timeline_merges_near_duplicates_researched_wins_and_sources_union() -> None:
    d = _alpha()
    tl = d["timeline"]
    assert [t["date"] for t in tl] == sorted((t["date"] for t in tl), reverse=True)        # newest first
    strike = [t for t in tl if "Trypillya" in t["headline"]]
    assert len(strike) == 1                                          # two reworded reports became one entry
    s = strike[0]
    assert s["verification"] == "researched" and s["from"] == "/geopolitics/2026-09-30"   # the researched one survives
    assert s["sources"] == [S2, S1]                                  # union, the survivor's first, http(s) only
    stall = [t for t in tl if t["headline"].startswith("Border talks")]
    assert len(stall) == 1 and stall[0]["verification"] == "researched" and stall[0]["detail"].startswith("Delegations")
    assert stall[0]["sources"] == [S3]                               # the most detailed text kept
    assert "Invasion began" in [t["headline"] for t in tl] and all("src_" not in "".join(t["sources"]) for t in tl)
    assert [t for t in tl if t["headline"] == "Invasion began"][0]["sources"] == []        # internal id dropped


def test_timeline_keeps_distinct_and_same_report_items_apart() -> None:
    same_report = _report("2026-09-29", [_section(TID, "Alpha war", [
        _dev("Port closed by strike", "Strike closed the northern port.", when="2026-09-29"),
        _dev("Port closed by strike again", "Strike closed the northern port again.", when="2026-09-29")])])
    assert len(_alpha(reports=[same_report], briefs=[])["timeline"]) == 2           # a report never merges its own
    far = [_report("2026-09-20", [_section(TID, "Alpha war", [_dev(*TRYP_A, when="2026-09-20")])]),
           _report("2026-09-29", [_section(TID, "Alpha war", [_dev(*TRYP_B, when="2026-09-29")])])]
    assert len(_alpha(reports=far, briefs=[])["timeline"]) == 2                     # not adjacent days
    diff = [_report("2026-09-29", [_section(TID, "Alpha war", [_dev(*TRYP_A, when="2026-09-29")])]),
            _report("2026-09-30", [_section(TID, "Alpha war", [
                _dev("Parliament votes budget", "Lawmakers approved the budget after debate.", when="2026-09-29")])])]
    assert len(_alpha(reports=diff, briefs=[])["timeline"]) == 2                    # different events


def test_places_accumulate_and_map_is_built_from_them(monkeypatch) -> None:
    basemap = [object()]
    seen = {}

    def fake_map(devs, countries):
        seen["devs"], seen["countries"] = devs, countries
        return {"points": [{"n": i + 1, "label": d["place"]["name"], "date": d["when"]} for i, d in enumerate(devs)]}

    monkeypatch.setattr(dossier.geo, "build_map", fake_map)
    d = _alpha(countries=basemap)
    assert d["places"] == [{"name": "Kyiv", "country": "Ukraine", "lat": 50.4501, "lon": 30.5234, "count": 2,
                            "last_date": "2026-09-28"}]
    assert seen["countries"] is basemap and seen["devs"][0]["verification"] == "researched"
    assert d["map"]["points"][0]["weight"] == 1.0
    monkeypatch.undo()
    assert _alpha()["map"] is None                                   # no basemap, no map


def test_actors_relations_statements() -> None:
    d = _alpha()
    actors = {a["name"]: a for a in d["actors"]}
    assert actors["Russia"]["mentions"] >= 4 and actors["Russia"]["first"] <= actors["Russia"]["last"]
    assert "Zelensky" in actors and not any("src_" in n or "->" in n for n in actors)
    assert len(dossier.build_all(_inputs())["theaters"][TID]["actors"]) <= dossier.TOP_ACTORS
    rel = [r for r in d["relations"] if r["source"] == "Russia"]
    assert len(rel) == 1 and rel[0]["count"] == 2 and rel[0]["last_date"] == "2026-10-01" and rel[0]["note"] == "new"
    assert len(d["relations"]) == 1                                  # the id endpoint and the blob are skipped
    assert d["statements"] == [{"who": "Zelensky", "role": "President", "said": "We will hold", "quote": False,
                                "when": "2026-09-28", "source": S1}]


def test_figures_are_series_by_label_and_unit() -> None:
    figs = _alpha()["figures"]
    assert len(figs) == 1 and figs[0]["label"] == "drones launched" and figs[0]["unit"] == "drones"
    assert [(p["as_of"], p["value"]) for p in figs[0]["series"]] == [("2026-09-29", 100.0), ("2026-09-30", 140.0)]


def test_indicators_are_tracked_by_exact_signal() -> None:
    ind = {i["signal"]: i["history"] for i in _alpha()["indicators"]}
    assert ind["Truce announced"] == [{"date": "2026-09-27", "status": "not seen"},
                                      {"date": "2026-10-01", "status": "emerging"}]
    assert ind["Bridge strike"] == [{"date": "2026-09-27", "status": "emerging"}]


def test_pulses_are_the_union_with_current_values_and_fall_back_without_a_store() -> None:
    d = _alpha()
    assert [p["id"] for p in d["pulses"]] == ["pls_a"]               # the brief's unknown name and others are dropped
    assert d["pulses"][0]["position"] == 62.0 and d["pulses"][0]["situation"] == "Alpha situation"
    assert d["pulses"][0]["history"][0]["at"] == "2026-10-02T10:00:00+00:00"
    bare = _alpha(pulses=None)["pulses"]
    assert bare[0]["position"] == 55.0 and bare[0]["history"] == [] and bare[0]["band"] == "elevated"


def test_links_from_cross_theater_mentions() -> None:
    assert _alpha()["links"] == [{"theater_id": OTHER, "name": "Bravo dispute",
                                  "link": "Alpha war -> Bravo dispute: shared actor.", "date": "2026-09-29"}]


def test_forecasts_for_this_theater_only(tmp_path) -> None:
    judgments = [Judgment(statement="It ends", probability=40, horizon="2026-12-01"),
                 Judgment(statement="It spreads", probability=60, horizon="2026-11-01")]
    forecasts.record("2026-10-01-alpha", TID, judgments, made_at="2026-10-01T09:00:00+00:00", root=tmp_path)
    forecasts.record("2026-10-01-other", OTHER, [Judgment(statement="Else", probability=10, horizon="2026-11-01")],
                     root=tmp_path)
    fid = forecasts.forecast_id("2026-10-01-alpha", "It ends")
    forecasts.resolve(fid, "yes", "It ended.", at="2026-10-02T00:00:00+00:00", root=tmp_path)
    rows = _alpha(forecasts=forecasts.current(tmp_path))["forecasts"]
    assert [r["statement"] for r in rows] == ["It spreads", "It ends"]            # open first, then the record
    assert rows[0]["resolution"] is None
    assert rows[1]["resolution"] == {"resolved_at": "2026-10-02T00:00:00+00:00", "outcome": "yes", "evidence": "It ended."}
    assert set(rows[0]) == {"id", "statement", "probability", "horizon", "status", "resolution"}


def test_index_orders_by_recent_activity_then_heat() -> None:
    quiet = _report("2026-10-03", [_section("thr_quiet", "Quiet", [])])
    hot = _report("2026-10-03", [_section("thr_hot", "Hot", [])])
    board = {"theaters": [], "heat": [{"theater_id": "thr_quiet", "heat": 1.0, "trend": "steady"},
                                      {"theater_id": "thr_hot", "heat": 9.0, "trend": "new"}]}
    built = dossier.build_all(_inputs(reports=[*_inputs().reports, quiet, hot], boards=[board, *_inputs().boards]))
    rows = built["index"]["theaters"]
    assert [r["theater_id"] for r in rows][:2] == ["thr_hot", "thr_quiet"]           # same day: hotter first
    assert rows[-1]["last_seen"] <= rows[0]["last_seen"]
    alpha = next(r for r in rows if r["theater_id"] == TID)
    assert alpha["max_band"] == "severe" and alpha["escalation_direction"] == "rising" and alpha["days_covered"] == 2
    assert alpha["url"] == "/intel/theaters/thr_alpha" and alpha["heat"] == 7.5
    assert set(alpha) == {"theater_id", "name", "domain", "first_seen", "last_seen", "days_covered", "heat",
                          "coverage", "escalation_direction", "max_band", "url", "state", "last_novel"}
    assert built["index"]["schema"] == "ohmega.dossier.index/1"


# ── primers ───────────────────────────────────────────────────────────────────────────────────
class _Model:
    def __init__(self, text, tasks):
        self.text, self.tasks = text, tasks

    def with_structured_output(self, schema):
        assert schema is primers.Primer
        return self

    def invoke(self, messages, **_k):
        self.tasks.append(messages[1].content)
        return primers.Primer(text=self.text)


def _ctx(text, tasks):
    model = _Model(text, tasks)
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


def test_primer_is_written_once_reused_and_refreshed_when_stale(tmp_path) -> None:
    tasks: list[str] = []
    theater = [{"id": TID, "name": "Alpha war", "description": "A war between A and B.", "why": "one contest"}]
    ctx = _ctx("Alpha is a war. See https://x.example/y for more.", tasks)
    fresh = NOW
    assert primers.ensure(ctx, tmp_path, theater, model_spec=None, now=fresh, store=_NoCorpus())[0]["status"] == "built"
    stored = primers.load(tmp_path)[TID]
    assert stored["text"] == "Alpha is a war. See for more." and stored["built_at"] == fresh.isoformat()
    assert "A war between A and B." in tasks[0] and "THEATER: Alpha war" in tasks[0]
    again = primers.ensure(ctx, tmp_path, theater, model_spec=None, now=fresh + timedelta(days=6), store=_NoCorpus())
    assert again == [{"theater": TID, "status": "reused"}] and len(tasks) == 1     # no needless call
    later = primers.ensure(ctx, tmp_path, theater, model_spec=None, now=fresh + timedelta(days=8), store=_NoCorpus())
    assert later[0]["status"] == "built" and len(tasks) == 2                         # stale: rewritten
    assert primers.load(tmp_path)[TID]["built_at"] == (fresh + timedelta(days=8)).isoformat()


class _NoCorpus:
    """A profile store with nothing in it (the corpus recall then just yields an empty context)."""
    root = None

    def iter_profiles(self):
        return iter(())


def test_primer_is_held_to_120_words_and_failure_is_contained(tmp_path) -> None:
    long = " ".join(f"word{i}" for i in range(300)) + "."
    assert len(primers.fit(long).split()) <= primers.MAX_WORDS
    sentences = ("A short sentence here. " * 40).strip()
    cut = primers.fit(sentences)
    assert len(cut.split()) <= primers.MAX_WORDS and cut.endswith(".")

    class _Boom:
        def __init__(self):
            self.model_resolver = self

        def resolve(self, _spec):
            raise RuntimeError("no model")

    rows = primers.ensure(_Boom(), tmp_path, [{"id": TID, "name": "A"}, {"id": "thr_b", "name": "B"}],
                          model_spec=None, now=NOW, store=_NoCorpus())
    assert [r["status"] for r in rows] == ["failed", "failed"] and primers.load(tmp_path) == {}


def test_dossier_carries_the_stored_primer() -> None:
    d = _alpha(primers={TID: {"theater_id": TID, "text": "Background.", "built_at": "2026-10-03T00:00:00+00:00"}})
    assert d["primer"] == {"text": "Background.", "built_at": "2026-10-03T00:00:00+00:00"}
    assert d["built_at"] == "2026-10-03T00:00:00+00:00" and _alpha()["primer"] is None


# ── files ─────────────────────────────────────────────────────────────────────────────────────
def _write_store(root) -> None:
    inp = _inputs()
    (root / "daily" / "geopolitics").mkdir(parents=True)
    for r in inp.reports:
        (root / "daily" / "geopolitics" / f"{r['date']}.json").write_text(json.dumps(r), encoding="utf-8")
    (root / "briefs").mkdir()
    for b in inp.briefs:
        (root / "briefs" / f"{b['slug']}.json").write_text(json.dumps(b), encoding="utf-8")
    (root / "boards").mkdir()
    (root / "boards" / "2026-10-01.json").write_text(json.dumps(next(iter(inp.boards))), encoding="utf-8")
    (root / "theaters.json").write_text(json.dumps(inp.registry), encoding="utf-8")
    (root / "primers").mkdir()
    (root / "primers" / f"{TID}.json").write_text(json.dumps(
        {"theater_id": TID, "text": "Background.", "built_at": "2026-10-03T00:00:00+00:00"}), encoding="utf-8")


def _pulse_store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "pulses")
    store.save_situation(Situation(id="sit_a", title="Alpha situation", status="active"))
    store.create_pulse(Pulse(id="pls_a", situation_id="sit_a", name="Strike Intensity",
                             definitions=[PulseDefinition(question="q", low_end="lo", high_end="hi")]))
    store.append(Influence(pulse_id="pls_a", at="2026-10-02T10:00:00+00:00", mode="article", definition_version=1,
                           proposed_position=62, absolute_position=99, decision="applied", rationale="r", key="k"))
    return store


def test_write_intel_writes_dossiers_to_content_and_public_data(tmp_path) -> None:
    intel = tmp_path / "intel"
    _write_store(intel)
    store = _pulse_store(tmp_path)
    snap = intel_page.build_snapshot(store, intel, now=NOW)
    site = tmp_path / "site"
    intel_page.write_intel(site, snap, intel, store)
    for base in (site / "content" / "intel" / "theaters", site / "public" / "data" / "theaters"):
        d = json.loads((base / f"{TID}.json").read_text(encoding="utf-8"))
        assert d["schema"] == "ohmega.dossier/1" and d["primer"]["text"] == "Background."
        assert d["pulses"][0]["id"] == "pls_a" and d["pulses"][0]["position"] == 62.0
        assert (base / f"{OTHER}.json").is_file()
    index = json.loads((site / "content" / "intel" / "theaters" / "index.json").read_text(encoding="utf-8"))
    assert index["schema"] == "ohmega.dossier.index/1" and {t["theater_id"] for t in index["theaters"]} == {TID, OTHER}
    stamps = {p: p.stat().st_mtime_ns for p in site.rglob("*.json") if "theaters" in p.parts}
    intel_page.write_intel(site, snap, intel, store)
    assert stamps == {p: p.stat().st_mtime_ns for p in stamps}                      # unchanged dossiers are not rewritten


def test_a_dossier_fault_never_costs_the_rest_of_the_publish(tmp_path, monkeypatch) -> None:
    intel = tmp_path / "intel"
    _write_store(intel)
    monkeypatch.setattr(dossier_store, "build", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = intel_page.build_snapshot(_pulse_store(tmp_path), intel, now=NOW)
    path = intel_page.write_intel(tmp_path / "site", snap, intel)
    assert path.is_file() and not (tmp_path / "site" / "content" / "intel" / "theaters").exists()
