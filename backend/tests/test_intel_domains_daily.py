"""`intel daily --domain ai` end to end with a stub model: the same recipe over the AI board."""

from __future__ import annotations

import json

from test_intel_daily import AS_OF, SRC_A, SUMMARY, _ctx, _draft, _store

from algent_backend.agent_system.agents.intel import daily
from algent_backend.ai_benchmarks import store as ai_store
from algent_backend.ai_benchmarks.contracts import Benchmark, Result


def test_an_ai_daily_end_to_end_with_a_stub_model(tmp_path, monkeypatch):
    """AI theaters are picked from the AI board, the section writer is shown the benchmark block, no sweep runs, and the record is stored under
    daily/ai/ (the path the site and API read by domain)."""
    _store(tmp_path, monkeypatch)
    monkeypatch.setenv("ALGENT_AI_BENCHMARKS_STORE", str(tmp_path / "aib"))
    ai_store.save_benchmarks([Benchmark(id="b", name="Bench", source="epoch", source_url="https://epoch.ai/b", ceiling=1.0)])
    ai_store.append([Result(benchmark="b", model=f"m{i}", model_id=f"m{i}", lab="openai", lab_name="OpenAI", score=0.1 * i,
                            date=f"2026-09-{20 + i:02d}", source="epoch") for i in range(1, 8)])
    member = {"edition": "2026-09-29-ai_sources", "n": 1, "title": "Frontier model ships", "thesis": "t", "sources": [SRC_A], "kind": "ai_sources"}
    board = {"as_of": AS_OF, "domain": "ai",
             "theaters": [{"id": "thr_race", "name": "The frontier race", "domain": "ai", "why": "w", "members": [member]},
                          {"id": "thr_war", "name": "A war", "domain": "geopolitics", "why": "w", "members": [member]}],
             "heat": [{"theater_id": "thr_race", "name": "The frontier race", "heat": 9.0, "trend": "heating", "recent_share": 0.2, "prior_share": 0.1},
                      {"theater_id": "thr_war", "name": "A war", "heat": 30.0, "trend": "heating"}]}
    tasks: list[str] = []
    res = daily.produce_daily(_ctx({"The frontier race": _draft(pulses=[])}, SUMMARY, tasks), domain="ai", top=3, research=False, model_spec=None,
                              as_of=AS_OF, board=board, out=tmp_path)
    rec = json.loads((tmp_path / "intel" / "daily" / "ai" / f"{AS_OF}.json").read_text(encoding="utf-8"))
    assert rec == res["report"] and rec["domain"] == "ai" and [t["theater_id"] for t in rec["theaters"]] == ["thr_race"]
    assert any("OHMEGA AI BENCHMARKS" in t for t in tasks) and not any("A war" in t for t in tasks)
    assert not rec.get("sweep")
