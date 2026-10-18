"""Retrieval over the desk's corpus: lexical ranking across dates and sources, the optional dense side (off by default, import-guarded), and its use in blind evidence."""

from __future__ import annotations

import json
from datetime import date

import pytest

from algent_backend.agent_system.agents.intel.daily import daily_dir
from algent_backend.agent_system.agents.statements import store as st
from algent_backend.agent_system.agents.statements.contracts import Statement
from algent_backend.markets import evidence
from algent_backend.markets.contracts import Market
from algent_backend.retrieval import embed, flags
from algent_backend.retrieval.search import Index

TODAY = date(2026, 10, 17)


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    for env, name in (("ALGENT_INTEL_STORE", "intel"), ("ALGENT_STATEMENTS_STORE", "st"), ("ALGENT_SANCTIONS_STORE", "sx"), ("ALGENT_CALENDAR_STORE", "cal"),
                      ("ALGENT_GEOLEDGER_STORE", "geo"), ("ALGENT_PROFILE_STORE", "prof"), ("ALGENT_RETRIEVAL_STORE", "ret")):
        monkeypatch.setenv(env, str(tmp_path / name))


def write_daily(day: str, theater: str, name: str, bottom: str) -> None:
    folder = daily_dir("geopolitics")
    folder.mkdir(parents=True, exist_ok=True)
    rec = {"date": day, "theaters": [{"theater_id": theater, "name": name, "bottom_line": bottom, "developments": [{"headline": "A headline"}]}],
           "market_view": {"lines": [{"text": "the market prices it at 61%"}]}}
    (folder / f"{day}.json").write_text(json.dumps(rec), encoding="utf-8")


def add_statement(sid: str, speaker: str, day: str, text: str) -> None:
    st.append_statements([Statement(id=sid, speaker=speaker, date=day, paraphrase=text, source_url=f"https://x/{sid}", transcript_id="t")])


def test_search_ranks_across_dates_and_sources_by_the_questions_words():
    write_daily("2026-10-10", "thr_gulf", "Iran and the Gulf", "Hormuz tanker traffic is normal while Oman mediation stalls.")
    write_daily("2026-10-16", "thr_ukr", "Ukraine front", "Artillery duels continue near Pokrovsk.")
    add_statement("st_1", "Abbas Araghchi", "2026-10-12", "Iran will not accept limits on enrichment during the Oman talks.")
    add_statement("st_2", "Someone Else", "2026-10-12", "Grain exports resume from Odesa.")
    idx = Index.build(TODAY, claims=False)
    hits = idx.search("Will Iran and the US sign a deal in Oman talks?", k=3)
    ids = [h.id for h in hits]
    assert "daily:2026-10-10:thr_gulf" in ids and "statement:st_1" in ids
    assert "statement:st_2" not in ids and "daily:2026-10-16:thr_ukr" not in ids
    assert hits[0].block().startswith("[") and "Oman" in hits[0].block()


def test_nothing_dated_after_today_is_returned_and_the_market_view_is_never_indexed():
    write_daily("2026-10-20", "thr_gulf", "Iran and the Gulf", "Future text about Oman.")
    write_daily("2026-10-10", "thr_gulf", "Iran and the Gulf", "Talks about Oman.")
    idx = Index.build(TODAY, claims=False)
    assert [h.id for h in idx.search("Oman")] == ["daily:2026-10-10:thr_gulf"]
    assert idx.search("market prices 61%") == []                                         # the daily's market line is not corpus: forecasts stay blind


def test_embeddings_are_off_by_default_and_import_guarded(monkeypatch):
    assert flags.EMBEDDINGS_ENABLED is False and embed.load() is None
    monkeypatch.setattr(flags, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", None)       # not installed: ImportError inside load()
    assert embed.load() is None
    assert Index.build(TODAY, claims=False).search("anything") == []                      # still works, lexical only


def test_a_dense_side_is_fused_and_its_vectors_are_cached(tmp_path):
    write_daily("2026-10-10", "a", "Alpha", "wheat harvest outlook")
    write_daily("2026-10-11", "b", "Beta", "bread supply and farm output")

    class Fake:
        name, calls = "fake", 0

        def encode(self, texts, *, query=False):
            Fake.calls += 0 if query else len(texts)
            return [[1.0, 0.0] if ("bread" in t or "grain" in t) else [0.0, 1.0] for t in texts]

    cached = embed.CachedEmbedder(Fake(), tmp_path / "e.jsonl")
    idx = Index.build(TODAY, embedder=cached, claims=False)
    assert idx.search("grain", k=1)[0].id == "daily:2026-10-11:b"                        # no shared word with the doc: only the dense side finds it
    Index.build(TODAY, embedder=embed.CachedEmbedder(Fake(), tmp_path / "e.jsonl"), claims=False)
    assert Fake.calls == 2                                                               # the second build re-encoded nothing


def test_evidence_with_an_index_adds_wider_record_without_repeating_what_is_shown():
    write_daily("2026-10-17", "thr_gulf", "Iran and the Gulf", "Oman mediation continues.")
    write_daily("2026-10-05", "thr_gulf", "Iran and the Gulf", "Earlier: Oman mediation round one.")
    idx = Index.build(TODAY, claims=False)
    m = Market(id="m", question="Will the Oman mediation succeed?", theaters=["thr_gulf"], countries=[])
    record = json.loads((daily_dir("geopolitics") / "2026-10-17.json").read_text(encoding="utf-8"))
    base = evidence.build(m, today=TODAY, record=record)
    more = evidence.build(m, today=TODAY, record=record, index=idx)
    assert base.ids == ["theater:thr_gulf"]
    assert more.ids == ["theater:thr_gulf", "daily:2026-10-05:thr_gulf"] and "WIDER RECORD" in more.text
    assert "daily:2026-10-17:thr_gulf" not in more.ids                                   # the section already shown is not repeated
