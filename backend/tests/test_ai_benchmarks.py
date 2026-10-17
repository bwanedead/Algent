"""AI benchmark tracker: parsers (captured-shape fixtures, no network), store, derived series, collector health, discovery (stubbed model)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from algent_backend.ai_benchmarks import collect, derive, discovery, evidence, flags, freshness, labs, store
from algent_backend.ai_benchmarks.contracts import Benchmark, Result
from algent_backend.ai_benchmarks.sources import Harvest, epoch, lmarena, swebench


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_AI_BENCHMARKS_STORE", str(tmp_path / "store"))


def R(bench="b", model="m", score=0.5, day="2026-01-01", lab="openai", weights="closed", ver="measured", model_id=None, source="epoch"):
    return Result(benchmark=bench, model=model, model_id=model_id or model, lab=lab, lab_name=lab.title(), score=score, date=day, weights=weights,
                  verification=ver, source=source)


# ── labs ──────────────────────────────────────────────────────────────────────────────────────────
def test_lab_of_folds_spellings_and_takes_the_first_organisation():
    assert labs.lab_of("Google DeepMind") == ("google", "Google")
    assert labs.lab_of("Google") == ("google", "Google")
    assert labs.lab_of("Z.ai (Zhipu AI),Tsinghua University") == ("z-ai", "Z.ai")
    assert labs.lab_of("Some Lab (A, B), Other") == ("some-lab-a-b", "Some Lab (A, B)")
    assert labs.lab_of("") == ("unknown", "Unknown")


# ── epoch ─────────────────────────────────────────────────────────────────────────────────────────
META = ("benchmark,in_eci,source_file,score_column,scale,random_baseline,score_ceiling,release_date,superseded_by\n"
        "GPQA diamond,True,gpqa.csv,Best score,1.0,0.25,1.0,2023-11-20,\n"
        "Aider polyglot,True,aider.csv,Percent correct,0.01,0.0,1.0,2024-12-21,\n"
        "METR Time Horizons,False,metr.csv,average_score,1.0,0.0,1.0,2025-03-18,\n"
        "WebDev Arena,False,,,1.0,0.0,1.0,2024-12-10,\n"
        "NoFile,False,,,1.0,0.0,1.0,2024-01-01,\n")
MODELS = ("model_version,model_group,date,display_name,organization,country,accessibility,training_compute_flop\n"
          "glm-5,GLM-5,2026-01-01,GLM 5,Z.ai (Zhipu AI),China,Open weights (unrestricted),\n"
          "claude-x,Claude X,2026-02-01,,Anthropic,US,API access,\n")
FILES = {
    "benchmark_metadata.csv": META, "model_metadata.csv": MODELS,
    "gpqa.csv": "Model version,Best score,Release date,Organization\nglm-5,0.7,2026-01-01,Z.ai (Zhipu AI)\nclaude-x,0.8,2026-02-01,Anthropic\nblank,,2026-02-01,Anthropic\n",
    "aider.csv": "Model version,Percent correct,Release date,Organization\nclaude-x,88.0,2026-02-01,Anthropic\n",
    "metr.csv": "Model version,Time horizon,average_score,Release date,Organization\nclaude-x,718.8,0.78,2026-02-01,Anthropic\n",
    "webdev_arena_external.csv": "Model version,Arena Score,Release date,Organization\nclaude-x,1820.3,2026-02-01,Anthropic\n",
    "epoch_capabilities_index/eci_scores.csv": "Model,Display name,eci,date,Organization,Accessibility group\nclaude-x,Claude X,166.8,2026-02-01,Anthropic,Closed weights\n"
                                              "glm-5,GLM 5,150.0,2026-01-01,Z.ai (Zhipu AI),Open weights\n",
}


def test_epoch_parse_scales_units_overrides_supplement_and_weights():
    h = epoch.parse(FILES, observed_on="2026-10-01")
    by = {b.id: b for b in h.benchmarks}
    assert set(by) == {"epoch-gpqa-diamond", "epoch-aider-polyglot", "epoch-metr-time-horizons", "epoch-webdev-arena", "epoch-eci"}
    assert by["epoch-gpqa-diamond"].ceiling == 1.0 and by["epoch-gpqa-diamond"].baseline == 0.25
    assert by["epoch-metr-time-horizons"].unit == "minutes" and by["epoch-metr-time-horizons"].ceiling is None
    assert by["epoch-webdev-arena"].unit == "points" and by["epoch-webdev-arena"].ceiling is None
    rows = {(r.benchmark, r.model_id): r for r in h.results}
    assert rows[("epoch-aider-polyglot", "claude-x")].score == 0.88                      # percent column * metadata scale
    assert rows[("epoch-metr-time-horizons", "claude-x")].score == 718.8                  # the override column, not the success rate
    assert rows[("epoch-gpqa-diamond", "glm-5")].weights == "open" and rows[("epoch-gpqa-diamond", "glm-5")].lab == "z-ai"
    assert rows[("epoch-gpqa-diamond", "claude-x")].weights == "closed"
    assert rows[("epoch-gpqa-diamond", "glm-5")].model == "GLM 5"
    assert ("epoch-gpqa-diamond", "blank") not in rows                                    # a row with no score is skipped
    assert rows[("epoch-eci", "glm-5")].weights == "open"
    assert all(r.observed_on == "2026-10-01" for r in h.results)


def test_epoch_format_change_is_an_error_not_a_half_read():
    with pytest.raises(ValueError):
        epoch.parse({"model_metadata.csv": MODELS}, observed_on="2026-10-01")
    broken = {**FILES, "gpqa.csv": "x,y\n1,2\n", "aider.csv": "x,y\n1,2\n", "metr.csv": "x,y\n1,2\n"}
    with pytest.raises(ValueError, match="unreadable"):
        epoch.parse(broken, observed_on="2026-10-01")


# ── swebench / lmarena ────────────────────────────────────────────────────────────────────────────
def test_swebench_parse_percent_and_open_flag_and_shape_error():
    text = json.dumps({"leaderboards": [{"name": "Verified", "results": [
        {"folder": "f1", "name": "Agent + Model", "model_display": "Model A", "model_org": "Anthropic", "agent": "Agent", "resolved": 70.4,
         "date": "2026-02-01", "os_model": False},
        {"folder": "f2", "name": "Open", "model_org": "DeepSeek", "resolved": 60.0, "date": "2026-01-01", "os_model": True},
        {"folder": "f3", "name": "NoScore", "resolved": None, "date": "2026-01-01"}]}]})
    h = swebench.parse(text, observed_on="2026-10-01")
    assert [b.id for b in h.benchmarks] == ["swebench-verified"]
    a, o = h.results
    assert a.score == 0.704 and a.weights == "closed" and a.lab == "anthropic" and "Agent" in a.note
    assert o.weights == "open" and o.model == "Open"
    with pytest.raises(ValueError):
        swebench.parse("{}", observed_on="2026-10-01")


def test_lmarena_parse_elo_and_licence():
    page = json.dumps({"num_rows_total": 2, "rows": [
        {"row": {"model_name": "A (High)", "organization": "google", "license": "Proprietary", "rating": 1532.337, "vote_count": 4904.0,
                 "leaderboard_publish_date": "2026-10-15"}},
        {"row": {"model_name": "B", "organization": "meta", "license": "Llama", "rating": 1400.0, "leaderboard_publish_date": "2026-10-15"}}]})
    h = lmarena.parse("text", "LMArena text", [page], observed_on="2026-10-17")
    assert h.benchmarks[0].id == "lmarena-text" and h.benchmarks[0].unit == "elo"
    assert [(r.weights, r.score) for r in h.results] == [("closed", 1532.34), ("open", 1400.0)]


# ── store ─────────────────────────────────────────────────────────────────────────────────────────
def test_store_appends_new_skips_unchanged_marks_revisions_and_survives_torn_lines():
    first = store.append([R(score=0.5), R(model="n", score=0.6)])
    assert (first.new, first.revised, first.unchanged) == (2, 0, 0)
    again = store.append([R(score=0.5), R(model="n", score=0.7)])
    assert (again.new, again.revised, again.unchanged) == (0, 1, 1)
    with (store.root() / "results.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    now = {r.model: r for r in store.current()}
    assert now["n"].score == 0.7 and now["n"].revised and len(store.log()) == 3


# ── derived series ────────────────────────────────────────────────────────────────────────────────
def test_frontier_is_the_record_setting_results_in_date_order():
    rs = [R(model="a", score=0.5, day="2026-01-01"), R(model="b", score=0.4, day="2026-02-01"), R(model="c", score=0.7, day="2026-03-01"),
          R(model="d", score=0.7, day="2026-04-01")]
    assert [r.model for r in derive.frontier(rs)] == ["a", "c"]                          # a tie does not reset the record


def test_view_open_vs_closed_lag_saturation_velocity_and_claims_stay_apart():
    bench = Benchmark(id="b", name="Bench", source="epoch", source_url="u", ceiling=1.0)
    rs = [R(model="c1", score=0.50, day="2025-01-01"), R(model="c2", score=0.70, day="2025-06-01"), R(model="c3", score=0.90, day="2026-05-01"),
          R(model="o1", score=0.40, day="2025-03-01", weights="open", lab="meta"), R(model="o2", score=0.70, day="2026-03-01", weights="open", lab="meta"),
          R(model="x", score=0.99, day="2026-05-02", ver="self_reported", source="self_reported")]
    v = derive.view(bench, rs, as_of=date(2026, 6, 1))
    assert v["best"]["m"] == "c3" and v["saturation"] == 0.9
    assert v["gap"] == pytest.approx(0.2) and v["open_lag_days"] == (date(2026, 3, 1) - date(2025, 6, 1)).days
    assert v["velocity"] == pytest.approx(0.9 - 0.7)                                       # the frontier a year before (2025-06-01) was 0.70
    assert [c["m"] for c in v["claimed"]] == ["x"] and all(p["m"] != "x" for p in v["frontier"])
    assert set(v["labs"]) == {"openai", "meta"}


def test_view_small_benchmark_lists_models_but_draws_no_frontier_and_future_dates_are_ignored():
    bench = Benchmark(id="b", name="Bench", source="epoch", source_url="u")
    v = derive.view(bench, [R(model="a"), R(model="b", day="2099-01-01")], as_of=date(2026, 6, 1))
    assert v["frontier"] == [] and v["n_models"] == 1 and v["saturation"] is None


def test_view_none_when_nothing_stored():
    assert derive.view(Benchmark(id="z", name="Z", source="epoch", source_url="u"), [R()], as_of=date(2026, 6, 1)) is None


# ── collector health ──────────────────────────────────────────────────────────────────────────────
def _harvest(n, day="2026-10-01"):
    return Harvest(benchmarks=[Benchmark(id="b", name="B", source="epoch", source_url="u")],
                   results=[R(model=f"m{i}", score=i / 100, day=day) for i in range(n)])


def test_collect_records_health_refuses_a_shrunken_fetch_and_isolates_failures():
    def boom():
        raise ValueError("format changed")

    rep = collect.collect(fetchers={"epoch": lambda: _harvest(50), "swebench": boom})
    by = {r["source"]: r for r in rep["sources"]}
    assert by["epoch"]["status"] == "ok" and by["epoch"]["new"] == 50 and by["swebench"]["status"] == "error"
    assert store.load_status()["swebench"]["broken"] is True
    shrunk = collect.collect(["epoch"], fetchers={"epoch": lambda: _harvest(10, day="2026-10-02")})
    assert shrunk["sources"][0]["status"] == "error" and "format changed or truncated" in shrunk["sources"][0]["error"]
    assert len(store.current()) == 50                                                      # nothing from the refused fetch was written
    assert store.load_status()["epoch"]["broken"] is True and store.load_status()["epoch"]["best_rows"] == 50


def test_freshness_flags_unfetched_not_updating_and_broken():
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    fresh = (now - timedelta(hours=3)).isoformat()
    status = {"epoch": {"last_ok": fresh, "newest_result": "2026-10-10"},
              "swebench": {"last_ok": (now - timedelta(hours=100)).isoformat(), "newest_result": "2026-10-10"},
              "lmarena": {"last_ok": fresh, "newest_result": "2026-01-01"},
              "other": {"last_ok": fresh, "newest_result": "2026-10-10", "broken": True, "last_error": "ValueError: format changed"}}
    rows = {r["source"]: r for r in freshness.source_health(now, status)}
    assert not rows["epoch"]["stale"]
    assert "not fetched" in rows["swebench"]["reasons"][0]
    assert "not updating upstream" in rows["lmarena"]["reasons"][0]
    assert rows["other"]["stale"] and "format changed" in rows["other"]["reasons"][0]


# ── discovery (stubbed search, pages and model) ───────────────────────────────────────────────────
PAGE = "word " * 100


def _search(query):
    return [{"title": "New model", "url": "https://lab.example/blog/x", "published": "2026-10-16"},
            {"title": "Old", "url": "https://old.example/y", "published": "2020-01-01"}]


def test_discovery_stores_self_reported_only_for_shown_urls_normalises_percent_and_matches_existing_benchmarks():
    store.save_benchmarks([Benchmark(id="epoch-gpqa-diamond", name="GPQA diamond", source="epoch", source_url="u", ceiling=1.0)])
    calls = []

    def ask(task):
        calls.append(task)
        return discovery.Extraction(claims=[
            discovery.Claim(model="Model Z", org="Anthropic", benchmark="GPQA Diamond", score=91.2, unit="percent", date="2026-10-16",
                            url="https://lab.example/blog/x", quote="91.2% on GPQA Diamond"),
            discovery.Claim(model="Model Z", benchmark="Brand New Bench", score=0.5, unit="fraction", url="https://lab.example/blog/x"),
            discovery.Claim(model="Ghost", benchmark="GPQA Diamond", score=99, unit="percent", url="https://not-shown.example/z")]), 0.03

    rep = discovery.run(search=_search, fetch_page=lambda u: PAGE, ask=ask, today=date(2026, 10, 17))
    assert rep["calls"] == 1 and rep["usd"] == 0.03 and rep["stored"] == 2 and rep["pages"] == ["https://lab.example/blog/x"]
    assert "old.example" not in calls[0]
    rs = {r.benchmark: r for r in store.current()}
    gp = rs["epoch-gpqa-diamond"]
    assert gp.verification == "self_reported" and gp.score == pytest.approx(0.912) and gp.lab == "anthropic" and gp.weights == "unknown"
    assert rs["claimed-brand-new-bench"].score == 0.5 and "claimed-brand-new-bench" in store.benchmarks()
    # measured frontier is untouched by claims; a second run the same day is stopped by the day limit; the status feeds the doctor
    assert derive.view(store.benchmarks()["epoch-gpqa-diamond"], store.current(), as_of=date(2026, 10, 17))["frontier"] == []
    assert discovery.run(search=_search, fetch_page=lambda u: PAGE, ask=ask, today=date(2026, 10, 17))["stopped"] == "day limit reached"
    assert store.load_status()["self_reported"]["last_ok"]


def test_discovery_makes_no_call_without_pages_when_dry_when_off_or_over_the_dollar_cap(monkeypatch):
    def never(task):
        raise AssertionError("no model call expected")

    assert "no new pages" in discovery.run(search=lambda q: [], fetch_page=lambda u: PAGE, ask=never, today=date(2026, 10, 17))["stopped"]
    assert discovery.run(search=_search, fetch_page=lambda u: PAGE, ask=never, today=date(2026, 10, 17), dry_run=True)["stopped"] == "dry run"
    store.save_discovery("2026-10-18", {"calls": 0, "usd": flags.DISCOVERY_MAX_USD_PER_DAY})
    assert discovery.run(search=_search, fetch_page=lambda u: PAGE, ask=never, today=date(2026, 10, 18))["stopped"] == "day limit reached"
    monkeypatch.setenv("ALGENT_AI_DISCOVERY", "0")
    assert "switched off" in discovery.run(search=_search, fetch_page=lambda u: PAGE, ask=never, today=date(2026, 10, 19))["stopped"]


def test_discovery_does_not_reread_pages_it_has_seen():
    store.save_discovery("2026-10-16", {"calls": 1, "usd": 0.01, "pages": ["https://lab.example/blog/x"]})
    rep = discovery.run(search=_search, fetch_page=lambda u: PAGE, ask=lambda t: (_ for _ in ()).throw(AssertionError("no call")), today=date(2026, 10, 17))
    assert rep["pages"] == [] and "no new pages" in rep["stopped"]


def test_discovery_cost_ceilings_are_well_under_ten_cents():
    assert flags.DISCOVERY_MAX_USD_PER_DAY < 0.10 and flags.DISCOVERY_MAX_CALLS_PER_DAY == 1


# ── desk evidence ─────────────────────────────────────────────────────────────────────────────────
def test_evidence_block_names_new_records_and_marks_claims_unverified():
    day = date(2026, 6, 1)
    store.save_benchmarks([Benchmark(id="b", name="Bench", source="epoch", source_url="https://epoch.ai/b", ceiling=1.0)])
    store.append([R(model=f"m{i}", score=0.1 * i, day=(day - timedelta(days=200 - 30 * i)).isoformat()) for i in range(1, 7)]
                 + [R(model="Claimed", score=0.97, day="2026-05-30", ver="self_reported", source="self_reported")])
    text, urls, n = evidence.block(as_of=day)
    assert "Bench: new measured record 60.0% by m6" in text and "https://epoch.ai/b" in urls
    assert "UNVERIFIED" in text and "Claimed" in text and n == 2
    assert evidence.block(as_of=day - timedelta(days=3000))[0] == ""
