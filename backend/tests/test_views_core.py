"""The view builders over a small published record: the graph, country, situation, event, home, HUD and daily-hub views, their shapes, caps and budgets."""

from __future__ import annotations

import json

from views_fixture import TODAY, context, daily, section

from algent_backend.views import build, country, daily_hub, event, flags, graph, home, hud, situation, themes
from algent_backend.views.base import View, make


def one(views: list[View], key: str) -> dict:
    return next(v.body for v in views if v.key == key)


def test_the_graph_ties_states_to_theaters_and_flags_what_has_a_page():
    g = graph.shared(context())
    assert g["refs"]["thr_hormuz"] == {"id": "thr_hormuz", "name": "Hormuz crisis", "direction": "rising", "band": "severe", "linked": True}
    assert "thr_old" not in g["refs"]                                      # a merged theater is its target now
    assert g["ties"]["thr_hormuz"]["IR"] == 9 + 3 * 2                      # 9 mentions on the actor page, +1 for its Pulse and +1 for its numbers in each of the 3 sections the 2 dailies hold
    assert g["names"]["IR"] == "Iran"
    v = graph.build(context())[0].body
    assert set(v["linkable"]) >= {"IR", "US", "CN"} and v["ties"]["thr_taiwan"]["CN"] >= 7


def test_themes_are_the_one_rule():
    assert themes.theme_of("Hormuz crisis", "Iran closes the strait to tankers") == ("energy", 1.0)
    assert themes.theme_of("Cyber war", "ransomware hits ministries") == ("tech", 1.0)
    assert themes.theme_of("Flood relief", "refugees displaced") == ("disaster", 1.0)
    assert themes.theme_of("Talks", "ministers meet in Geneva") == ("politics", 1.0)
    assert themes.theme_of("Something", "unrelated words only") == ("politics", 0.5)       # fell to the default: half weight
    assert themes.dominant({"economy": 1.0, "energy": 1.0}) == "economy"                  # ties go to THEMES order
    assert abs(themes.decay(7) - 0.5) < 1e-9 and themes.decay(-3) == 1.0


def test_country_panel_stats_counts_briefs_and_context():
    views = country.build(context())
    iran = one(views, "country/IR")
    assert iran["schema"] == "ohmega.view.country/1" and iran["as_of"] == "2026-10-23" and iran["profiled"] is True
    panel = iran["panel"]
    gdp = next(s for s in panel["stats"] if s["id"] == "gdp")
    assert gdp["value"] == 4e11 and gdp["unit"] == "usd" and 0 <= gdp["pos"] <= 1 and gdp["median"] is not None and panel["profiled"] == 6
    assert panel["counts"]["theaters"] == 1 and panel["counts"]["sanctions"] == 1 and panel["counts"]["calendar"] == 1 and panel["counts"]["anomalies"] == 1
    assert panel["grid"] == {"line": "Grid down 12% in 30 days.", "asOf": TODAY}
    assert panel["leaders"]["head_of_state"] == "Iran Leader"
    briefs = panel["briefs"]
    assert briefs[0]["date"] == "2026-10-23" and {b["kind"] for b in briefs} == {"section", "development"}
    assert all(b["theme"] in themes.THEMES and b["href"].startswith("/daily/geopolitics") for b in briefs)
    assert len({(b["date"], b["text"]) for b in briefs}) == len(briefs)                     # one line per text per day
    ctx = iran["context"]
    assert [t["id"] for t in ctx["theaters"]] == ["thr_hormuz"] and ctx["saidAbout"] == 1 and len(ctx["said"]) == 2
    assert ctx["developments"][0]["event"].startswith("/intel/events/2026-10-23/thr_hormuz/")
    assert {r["iso2"] for r in ctx["related"]} >= {"US", "SA"}
    assert iran["calendar"][0]["title"] == "Gulf summit" and iran["sanctions"][0]["name"] == "MAR AZUL" and iran["snapshot"]["situations"][0]["pulses"][0]["id"] == "pls_thr_hormuz"
    assert not iran["panel"]["briefs"] or iran["panel"]["briefsTotal"] >= len(iran["panel"]["briefs"])


def test_a_country_with_nothing_but_a_mention_still_gets_a_small_view():
    france = one(country.build(context()), "country/FR")
    assert france["profiled"] is True and france["panel"]["briefs"] == [] and france["context"]["theaters"] == []


def test_country_lists_are_capped_and_stay_inside_the_budget():
    ctx = context()
    rows = [{"id": f"s{i}", "source": "ofac", "action": "designated", "on_date": "2026-10-20", "observed_on": "2026-10-21", "name": f"VESSEL {i}", "type": "vessel", "countries": ["IR"]} for i in range(400)]
    ctx.tables._docs["sanctions/country/IR.json"] = {"rows": rows}
    iran = one(country.build(ctx), "country/IR")
    assert len(iran["sanctions"]) == flags.COUNTRY_SANCTIONS and iran["sanctionsTotal"] == 400
    assert [v for v in country.build(ctx) if v.over_budget()] == []


def test_situation_stream_splits_full_days_from_index_rows():
    ctx = context()
    for d in ("2026-10-20", "2026-10-21"):
        ctx.staged.docs[f"daily/geopolitics/{d}.json"] = daily("geopolitics", d, [section("thr_hormuz", "Hormuz crisis")])
    ctx.staged._cache.clear()
    views = situation.build(ctx)
    v = one(views, "situation/thr_hormuz")
    st = v["stream"]
    assert st["days_total"] == 4 and [e["date"] for e in st["full"]] == ["2026-10-23", "2026-10-22", "2026-10-21"][: flags.STREAM_FULL_DAYS]
    assert all("section" in e for e in st["full"]) and st["index"][0]["date"] == "2026-10-20" and "section" not in st["index"][0]
    assert st["index"][0]["href"] == "/daily/geopolitics/2026-10-20#theater-0-thr-hormuz" and st["index"][0]["visuals"][0]["kind"] == "chart"
    assert st["full"][0]["events"] is True                                                    # the theater appears once as a section that day
    assert v["desk"] == "geopolitics" and {s["iso2"] for s in v["states"]} >= {"IR", "US"} and v["related"][0]["id"] == "thr_taiwan"
    assert v["snapshot"]["situations"][0]["pulses"][0]["id"] == "pls_thr_hormuz" and v["snapshot"]["theaters"] == []
    assert [a["iso2"] for a in v["involved"]] == ["IR", "US", "SA"] and v["involved"][0]["headline"][0]["id"] == "gdp"


def test_a_situation_view_over_budget_sheds_full_days_until_it_fits(monkeypatch):
    ctx = context()
    for d in ("2026-10-21", "2026-10-22", "2026-10-23"):
        ctx.staged.docs[f"daily/geopolitics/{d}.json"] = daily("geopolitics", d, [section("thr_hormuz", "Hormuz crisis", map_bytes=200_000)])
    ctx.staged._cache.clear()
    monkeypatch.setitem(flags.BUDGET_BYTES, "situation", 500_000)
    v = next(v for v in situation.build(ctx) if v.key == "situation/thr_hormuz")
    assert not v.over_budget() and len(v.body["stream"]["full"]) == 2 and v.notes and v.body["stream"]["index_total"] == 1


def test_the_situations_index_groups_by_desk_and_holds_slim_rows():
    body = one(situation.build(context()), "situations")
    by = {d["desk"]: d for d in body["desks"]}
    assert [r["item"]["theater_id"] for r in by["geopolitics"]["active"]] == ["thr_hormuz"]
    assert [r["item"]["theater_id"] for r in by["geopolitics"]["quiet"]] == ["thr_taiwan"] and [r["item"]["theater_id"] for r in by["geopolitics"]["merged"]] == ["thr_old"]
    assert [r["item"]["theater_id"] for r in by["ai"]["active"]] == ["thr_chips"]                    # the one-day Spotlight is not listed
    row = by["geopolitics"]["active"][0]
    assert set(row["dossier"]) == {"escalation_history", "coverage_series"} and len(row["dossier"]["coverage_series"]) == 21


def test_daily_hub_and_home_carry_digests_not_reports():
    hub = daily_hub.build(context())[0].body
    d = {x["desk"]: x for x in hub["desks"]}
    assert d["geopolitics"]["date"] == "2026-10-23" and d["geopolitics"]["dates_total"] == 2 and d["geopolitics"]["recent"] == ["2026-10-22"]
    report = d["geopolitics"]["report"]
    assert report["summary"]["headline"] == "Hormuz stays shut" and "map" not in report["theaters"][0] and "developments" not in report["theaters"][0]
    assert report["theaters"][0]["numbers"]["trackers"][0]["spark"] == [1, 2, 3] and report["theaters"][0]["visuals"][0]["asset"].startswith("/analytics/")
    fat = context(extra={"daily/geopolitics/2026-10-23.json": daily("geopolitics", "2026-10-23", [section("thr_hormuz", "Hormuz crisis", map_bytes=100_000)])})
    assert len(json.dumps(daily_hub.build(fat)[0].body["desks"][0]["report"])) < len(json.dumps(fat.daily("geopolitics", "2026-10-23"))) / 10     # the map is not carried
    h = home.build(context())[0].body
    assert set(h["reports"]) == {"geopolitics", "ai"} and h["snapshot"]["situations"][0]["pulses"][0]["id"] == "pls_thr_hormuz"
    assert h["snapshot"]["theaters"][0]["series"][-1]["count"] == 23 and len(h["snapshot"]["theaters"][0]["series"]) == 7
    assert [m["id"] for m in h["moving"]] == ["thr_hormuz", "thr_chips"]
    f = h["facts"]
    assert f["situations"] == {"active": 2, "rising": 2, "stamp": TODAY} and f["actors"] == 6 and f["record"]["shown"] == 3 and f["pulses"] == {"total": 2, "severe": 1, "built_at": "2026-10-23T06:00:00+00:00"}
    assert f["calendar_30d"] == 1 and f["sanctions"]["additions"] == 1


def test_hud_globe_rows_and_blocks():
    v = hud.build(context())[0].body
    g, h = v["globe"], v["hud"]
    iran = g["countries"]["IR"]
    assert iran["th"] == "energy" and iran["dir"] == "rising" and iran["n"] == 1 and iran["hot"] == 1 and iran["page"] is True and iran["name"] == "Iran"
    assert iran["headline"]["date"] == "2026-10-23" and iran["theaters"][0]["href"] == "/situations/thr_hormuz"
    assert g["asOf"] == "2026-10-23" and g["theaters"][0]["id"] == "thr_hormuz" and g["theaters"][0]["lon"] == 55 and g["theaters"][0]["href"].startswith("/daily/geopolitics#theater-")
    assert h["daily"]["items"][0]["kind"] == "section" and h["daily"]["items"][0]["theme"] == "energy" and len(h["daily"]["items"]) <= flags.HUD_DAILY_ITEMS
    assert h["theaters"][0]["id"] == "thr_hormuz" and h["theaters"][0]["pulses"][0]["history"][-1] == 72.0
    assert [p["id"] for p in h["pulses"]] == ["pls_thr_hormuz", "pls_thr_chips"] and h["pulses"][0]["change7d"] == 6.0
    assert h["coming"][0]["title"] == "Gulf summit" and h["sanctions"][0]["name"] == "MAR AZUL"
    assert h["trader"]["equity"] == 1010 and h["trader"]["curve"][-1] == {"day": TODAY, "flat": 1000, "trader": 1010} and h["trader"]["positions"][0]["question"] == "Q?"
    assert "live" not in h                                                                      # the live counters stay a live read on the site


def test_event_views_hold_a_sections_developments_and_resolve_their_actors():
    views = event.build(context())
    v = one(views, "event/2026-10-23/thr_hormuz")
    assert len(v["developments"]) == 2 and v["actor_isos"][0] == ["IR", "US"] and v["theater"]["linked"] is True and v["anchor"] == "theater-0-thr-hormuz"
    assert {x.key for x in views} == {"event/2026-10-22/thr_hormuz", "event/2026-10-22/thr_taiwan", "event/2026-10-23/thr_hormuz", "event/2026-10-23/thr_taiwan"}


def test_build_all_reports_a_failing_family_and_still_builds_the_rest(monkeypatch):
    monkeypatch.setitem(build.BUILDERS, "home", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))
    res = build.build_all(context(), ["home", "daily-hub"])
    assert any(e.startswith("home: RuntimeError") for e in res.errors) and [v.family for v in res.views] == ["daily-hub"]
    assert "unknown view family" in build.build_all(context(), ["nope"]).errors[0]


def test_every_view_has_the_envelope_and_a_budget():
    res = build.build_all(context())
    assert not res.errors, res.errors
    for v in res.views:
        assert v.body["schema"] == f"ohmega.view.{v.family}/1" and "built_at" in v.body and "as_of" in v.body and v.body["provenance"]["sources"], v.key
        assert v.family in flags.BUDGET_BYTES and not v.over_budget(), v.key
    assert one(res.views, "manifest")["families"]["country"]["count"] >= 5
    assert make("graph", "graph", {}, as_of="", sources=[]).path == "views/graph.json"


def test_a_build_is_deterministic_so_an_unchanged_record_hashes_the_same(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    first = {v.key: json.dumps(v.body, sort_keys=True) for v in build.build_all(context(a, with_corpus=True)).views}
    second = {v.key: json.dumps(v.body, sort_keys=True) for v in build.build_all(context(b, with_corpus=True)).views}
    assert first == second
