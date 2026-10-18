"""The AI domain: the same daily recipe over its own sources, board, topic areas and numbers (no model, no network)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from algent_backend.agent_system.agents.intel import base, desk, domains, focus, heat, refresh, sensing
from algent_backend.agent_system.agents.intel.contracts import Theater
from algent_backend.ai_benchmarks import store as ai_store
from algent_backend.ai_benchmarks.contracts import Benchmark, Result
from algent_backend.library.ai_sources import AI_SOURCE_IDS, AI_SOURCES
from algent_backend.library.sources import SOURCES, all_sources

TODAY = date(2026, 10, 17)


class _Recorder:
    def __init__(self, plan):
        self.plan, self.tasks = plan, []

    def with_structured_output(self, _s):
        return self

    def invoke(self, messages, **_k):
        self.tasks.append([m.content for m in messages])
        return self.plan


def _ctx(rec):
    return type("X", (), {"model_resolver": type("R", (), {"resolve": lambda _s, _spec: type("C", (), {"client": rec})()})()})()


def _ai_heads(days, today):
    return [{"id": f"ai-{i}", "day": "2026-10-16", "kind": base.AI_SOURCES, "edition": "2026-10-16-ai_sources", "n": i,
             "title": t, "thesis": "", "sources": [f"https://lab.example/{i}"], "group": "ai_openai"}
            for i, t in enumerate(("Lab ships a new frontier model", "Frontier model tops the benchmarks", "Export rules tighten on accelerators",
                                   "Chip export curbs widen"), 1)]


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))
    monkeypatch.setenv("ALGENT_AI_BENCHMARKS_STORE", str(tmp_path / "aib"))


def test_domain_registry_owns_and_board_locations(tmp_path):
    assert domains.get("AI").id == "ai" and not domains.get("ai").uses_radar and not domains.get("ai").sweep
    assert len(domains.AI.topics) >= 6 and "THIS BOARD IS THE ARTIFICIAL INTELLIGENCE DESK'S" in domains.AI.note()
    assert domains.GEO.note() == "" and domains.get("economics").label == "Economics"       # unknown ids get the default recipe
    assert domains.owns("ai", "ai") and not domains.owns("ai", "geopolitics")
    assert domains.owns("geopolitics", "politics") and domains.owns("geopolitics", "") and not domains.owns("geopolitics", "ai")
    assert domains.boards_dir(tmp_path, "geopolitics") == tmp_path / "boards" and domains.boards_dir(tmp_path, "ai") == tmp_path / "boards" / "ai"


def test_ai_sources_are_a_separate_crawlable_catalog():
    ids = [s.id for s in AI_SOURCES]
    assert len(ids) == len(set(ids)) >= 10 and not AI_SOURCE_IDS & {s.id for s in SOURCES}
    assert all(f.beat == "ai" and f.type == "rss" for s in AI_SOURCES for f in s.feeds)
    assert AI_SOURCE_IDS <= {s.id for s in all_sources()}


def test_ai_board_clusters_only_ai_headlines_files_theaters_under_ai_and_keeps_boards_apart(tmp_path):
    heat._save_registry({"thr_ukraine": {"name": "Ukraine war", "description": "d", "domain": "geopolitics"},
                         "thr_chips": {"name": "Chip export controls", "description": "accelerators", "domain": "ai"}})
    plan = heat.TheaterPlan(theaters=[
        heat.ProposedTheater(name="The frontier race", domain="geopolitics", headline_ids=["ai-1", "ai-2"]),
        heat.ProposedTheater(existing_id="thr_chips", name="Chip export controls", domain="technology", headline_ids=["ai-3", "ai-4"])])
    rec = _Recorder(plan)
    board = heat.run(_ctx(rec), None, [{"slug": "2026-10-16-0800", "leads": [{"n": 1, "title": "Geopolitics radar item"}]}], model_spec=None, days=7,
                     today=TODAY, loaders={base.AI_SOURCES: _ai_heads}, domain="ai")
    system, task = rec.tasks[0]
    assert "Frontier labs race" in system and "Set `domain` to `ai`" in system
    assert "thr_chips" in task and "Ukraine" not in task and "Geopolitics radar item" not in task        # only its own domain's theaters and sources
    assert {t["domain"] for t in board["theaters"]} == {"ai"} and board["domain"] == "ai"
    assert (tmp_path / "intel" / "boards" / "ai" / "2026-10-17.json").exists() and not (tmp_path / "intel" / "boards" / "2026-10-17.json").exists()
    assert desk.latest_board("ai")["as_of"] == "2026-10-17" and desk.latest_board() is None
    # the focus for `--domain ai` finds these theaters; the registry carries both domains
    plan_ = focus.plan(board, 5, ["ai"])
    assert set(plan_.focus) <= {t["id"] for t in board["theaters"]} and plan_.focus
    assert heat.registry()["thr_ukraine"]["domain"] == "geopolitics"
    assert [r["base"] for r in [board]][0].get("ai_sources", {}).get("shown") == 4


def test_hacker_news_class_keeps_engaged_ai_stories_once(monkeypatch):
    page = json.dumps({"hits": [{"objectID": "1", "title": "New open model beats rivals", "created_at": "2026-10-16T10:00:00Z", "points": 300, "url": "https://x.example/a"},
                                {"objectID": "2", "title": "Ask HN: LLM tooling", "created_at": "2026-10-15T10:00:00Z", "points": 90, "url": None}]})
    monkeypatch.setattr("algent_backend.polite_http.get", lambda url, params=None, **k: page)
    heads = base.ai_community_heads(7, TODAY)
    assert [h["id"] for h in heads] == ["hn-1", "hn-2"] and heads[1]["sources"] == ["https://news.ycombinator.com/item?id=2"]
    assert heads[0]["kind"] == base.AI_COMMUNITY and heads[0]["thesis"] == "300 points"


def test_benchmark_evidence_reaches_only_ai_theaters():
    ai_store.save_benchmarks([Benchmark(id="b", name="Bench", source="epoch", source_url="https://epoch.ai/b", ceiling=1.0)])
    ai_store.append([Result(benchmark="b", model=f"m{i}", model_id=f"m{i}", lab="openai", lab_name="OpenAI", score=0.1 * i,
                            date=f"2026-10-{i:02d}", source="epoch") for i in range(1, 8)])
    ai = sensing.for_theater(Theater(id="t", name="Frontier race", domain="ai"), as_of=TODAY)
    geo = sensing.for_theater(Theater(id="g", name="Frontier race", domain="geopolitics"), as_of=TODAY)
    assert "OHMEGA AI BENCHMARKS" in ai.render() and "https://epoch.ai/b" in ai.primary_urls and ai.n_benchmarks
    assert "OHMEGA AI BENCHMARKS" not in geo.render() and not geo.benchmark_urls
    assert "OHMEGA AI BENCHMARKS" in sensing.across_theaters(as_of=TODAY, domain="ai").render()


def test_ai_refresh_uses_its_own_layers_not_statements_or_instruments():
    def boom(*_a):
        raise AssertionError("geopolitics layer called for the AI domain")

    rep = refresh.refresh(None, None, instruments=boom, statements=boom, library=lambda: {"crawled": 3}, domain="ai")
    assert rep["library"] == {"crawled": 3} and "ai_benchmarks" in rep and "instruments" not in rep and "statements" not in rep


def test_ai_daily_is_a_paid_job_only_when_the_operator_flips_the_flag(monkeypatch):
    from algent_backend.agent_system.agents.intel import flags
    from algent_backend.ops import schedule

    assert "ai-daily" not in schedule.jobs()
    monkeypatch.setattr(flags, "AI_DAILY_SCHEDULED", True)
    job = schedule.jobs()["ai-daily"]
    assert job.argv == ("intel", "daily", "--domain", "ai", "--research") and job.utc == flags.AI_DAILY_UTC
