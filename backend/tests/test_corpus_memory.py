"""Corpus memory: ranking, claim selection, budget, wiring into research and the intel desk."""

from __future__ import annotations

import time

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.intel import daily
from algent_backend.agent_system.agents.intel.contracts import (
    Brief,
    ContextItem,
    Development,
    SectionDraft,
    Theater,
    TimelineItem,
)
from algent_backend.agent_system.agents.research import corpus
from algent_backend.agent_system.agents.research import loop as profile_loop
from algent_backend.agent_system.agents.research.assembly import finalize_profile
from algent_backend.agent_system.agents.research.messages import build_vector_message
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    Entity,
    SignalProfile,
    SourceArtifact,
)
from algent_backend.agent_system.agents.research.store import JsonProfileStore
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


def _profile(pid, title, *, summary="", as_of="2026-06-01", entities=(), urls=(), claims=()):
    """``claims``: (id, text, status[, salience[, published_at]])."""
    srcs = [SourceArtifact(id=f"{pid}_s{i}", url=u) for i, u in enumerate(urls)]
    cl = []
    for spec in claims:
        cid, text, status, *rest = spec
        sal = rest[0] if rest else "medium"
        pub = rest[1] if len(rest) > 1 else ""
        sid = f"{pid}_p{cid}"
        if pub:
            srcs.append(SourceArtifact(id=sid, url=f"https://pub.example/{cid}", published_at=pub))
        cl.append(Claim(id=cid, text=text, status=status, salience=sal, grounding="snapshotted",
                        supported_by=[sid] if pub else [srcs[0].id] if srcs else []))
    return SignalProfile(id=pid, title=title, summary=summary, as_of=as_of, source_ledger=srcs, claim_ledger=cl,
                         entities=[Entity(id=f"e_{n}", name=n) for n in entities])


def _store(tmp_path, *profiles):
    store = JsonProfileStore(tmp_path / "corpus_store")
    for p in profiles:
        store.save(p)
    return store


def _ids(ctx):
    return [p.id for p in ctx.profiles]


# ── ranking ────────────────────────────────────────────────────────────────────────────────────
def test_entity_overlap_outranks_unrelated_and_is_found_in_the_query_text(tmp_path) -> None:
    store = _store(tmp_path,
                   _profile("a", "Cobalt export ban", entities=["Congo", "Glencore"], claims=[("c1", "ban hits supply", "confirmed")]),
                   _profile("b", "Tulip prices", entities=["Netherlands"], claims=[("c2", "bulbs up", "confirmed")]))
    ctx = corpus.related(store, query_text="What does the Congo decree do to refining?")   # entity named in text only
    assert _ids(ctx) == ["a"] and "entities: Congo" in ctx.profiles[0].reasons[0]
    ctx = corpus.related(store, query_text="unrelated words", entities=["netherlands"])      # normalised explicit
    assert _ids(ctx)[0] == "b"


def test_shared_source_url_links_profiles_and_rare_beats_common_domain(tmp_path) -> None:
    store = _store(tmp_path,
                   _profile("a", "Alpha", urls=["https://wire.example/x1"], claims=[("c1", "alpha fact", "confirmed")]),
                   _profile("b", "Bravo", urls=["https://wire.example/y1", "https://rare.example/doc"],
                            claims=[("c2", "bravo fact", "confirmed")]),
                   _profile("c", "Charlie", urls=["https://wire.example/z1"], claims=[("c3", "charlie fact", "confirmed")]))
    ctx = corpus.related(store, query_text="zzz", sources=["https://rare.example/doc/"])   # trailing slash tolerated
    assert _ids(ctx) == ["b"] and "1 shared source(s)" in ctx.profiles[0].reasons
    ctx = corpus.related(store, query_text="zzz", sources=["https://wire.example/q"])      # same publisher only
    assert set(_ids(ctx)) == {"a", "b", "c"} and "same publishers: wire.example" in ctx.profiles[0].reasons


def test_lexical_signal_ranks_topical_neighbours(tmp_path) -> None:
    store = _store(tmp_path,
                   _profile("a", "Grid batteries", summary="lithium storage on the european grid",
                            claims=[("c1", "battery storage capacity doubled", "confirmed")]),
                   _profile("b", "Wheat harvest", summary="drought cuts yields",
                            claims=[("c2", "wheat yields fell", "confirmed")]))
    ctx = corpus.related(store, query_text="grid battery storage capacity")
    assert _ids(ctx) == ["a"]


def test_recency_discounts_but_never_discards(tmp_path) -> None:
    same = dict(summary="shipping lane insurance", claims=[("c1", "premiums rose", "confirmed")])
    store = _store(tmp_path, _profile("old", "Shipping insurance", as_of="2024-01-01", **same),
                   _profile("new", "Shipping insurance", as_of="2026-09-01", **{**same, "claims": [("c2", "premiums rose", "confirmed")]}))
    ctx = corpus.related(store, query_text="shipping lane insurance", as_of="2026-09-30")
    assert _ids(ctx) == ["new", "old"] and ctx.profiles[0].score > ctx.profiles[1].score > 0


def test_as_of_hides_the_future_and_exclude_ids_skips_profiles(tmp_path) -> None:
    store = _store(tmp_path,
                   _profile("early", "Hormuz transits", as_of="2026-03-01", claims=[("c1", "transits normal", "confirmed")]),
                   _profile("late", "Hormuz transits", as_of="2026-09-01", claims=[("c2", "transits halved", "confirmed")]))
    assert _ids(corpus.related(store, query_text="hormuz transits", as_of="2026-04-01")) == ["early"]
    assert _ids(corpus.related(store, query_text="hormuz transits", exclude_ids=["early"])) == ["late"]


def test_older_than_keeps_only_older_claims(tmp_path) -> None:
    store = _store(tmp_path, _profile("a", "Strait", claims=[("c1", "strait closed", "confirmed", "high", "2026-01-05"),
                                                              ("c2", "strait reopened", "confirmed", "high", "2026-09-28")]))
    ctx = corpus.related(store, query_text="strait", older_than="2026-09-01")
    assert [c.claim_id for c in ctx.claims] == ["c1"] and ctx.claims[0].date == "2026-01-05"
    assert ctx.claims[0].date_basis == "source"


# ── claims ─────────────────────────────────────────────────────────────────────────────────────
def test_claim_selection_prefers_stronger_grades_and_salience(tmp_path) -> None:
    store = _store(tmp_path, _profile("a", "Refinery fire", claims=[
        ("weak", "refinery fire rumour", "speculative", "low"),
        ("good", "refinery fire confirmed by operator", "confirmed", "high"),
        ("mid", "refinery fire likely arson", "likely", "medium")]))
    ctx = corpus.related(store, query_text="refinery fire")
    assert [c.claim_id for c in ctx.claims] == ["good", "mid", "weak"]


def test_budget_caps_rendered_claims_and_is_deterministic(tmp_path) -> None:
    claims = [(f"c{i:02d}", f"port strike development number {i} " + "x" * 80, "confirmed") for i in range(12)]
    store = _store(tmp_path, _profile("a", "Port strike", claims=claims))
    small = corpus.related(store, query_text="port strike", budget_chars=500)
    assert 0 < len(small.claims) < 12 and len(small.render()) <= 500
    again = corpus.related(store, query_text="port strike", budget_chars=500)
    assert small == again
    full = corpus.related(store, query_text="port strike", budget_chars=100_000)
    assert len(full.claims) == corpus.MAX_CLAIMS_PER_PROFILE      # one profile cannot be the only voice


def test_claim_carries_source_urls_and_context_exports(tmp_path) -> None:
    store = _store(tmp_path, _profile("a", "Tariff", claims=[("c1", "tariff set at 25 percent", "confirmed", "high", "2026-05-02")]))
    ctx = corpus.related(store, query_text="tariff")
    assert ctx.source_urls == {"https://pub.example/c1"} and ctx.claim_ids == {"c1"}
    assert "[c1] (confirmed, 2026-05-02)" in ctx.render() and ctx.summaries()[0].startswith("c1 [confirmed]")
    assert corpus.related(store, query_text="nothing matches qqq").empty


def test_retrieval_on_a_hundred_profiles_is_fast(tmp_path) -> None:
    profiles = [_profile(f"p{i:03d}", f"Topic {i} story", summary=f"theme{i % 9} widget{i % 13}",
                         entities=[f"Entity{i % 17}"], urls=[f"https://site{i % 11}.example/{i}"],
                         claims=[(f"c{i}_{j}", f"fact {j} about theme{i % 9} widget{i % 13}", "confirmed") for j in range(30)])
                for i in range(100)]
    store = _store(tmp_path, *profiles)
    list(store.iter_profiles())      # first read of freshly written files is Windows file-system noise, not retrieval
    t0 = time.perf_counter()
    first = corpus.related(store, query_text="theme3 widget5 Entity4 story")     # builds the index
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    second = corpus.related(store, query_text="theme3 widget5 Entity4 story")    # cache hit
    warm = time.perf_counter() - t0
    assert first == second and first.claims and cold < 1.0 and warm < cold
    store.save(_profile("p_new", "Brand new theme3 widget5", claims=[("cn", "theme3 widget5 news", "confirmed")]))
    assert "p_new" in _ids(corpus.related(store, query_text="theme3 widget5 brand new"))   # cache invalidated


# ── research wiring ──────────────────────────────────────────────────────────────────────────────
class _Resolver:
    def resolve(self, _spec):
        return type("R", (), {"client": object()})()


def _ctx(events):
    return AgentRunContext(run_id="t", model_resolver=_Resolver(), tools={"web_search": object()},  # type: ignore[arg-type]
                           emit=lambda et, p=None: events.append((et, p or {})))


def _graph(context, monkeypatch, produced, seen):
    monkeypatch.setattr(profile_loop, "build_react_loop", lambda *a, **k: object())

    def fake_stream(agent, payload, **_k):
        seen.append(payload["messages"][0].content)
        return produced
    monkeypatch.setattr(profile_loop, "stream_react_loop", fake_stream)
    return profile_loop.build_profile_graph(
        context, model_spec=ModelSpec(provider="openai", model="gpt-5.4-mini"), tool_ids=("web_search",),
        system_prompt="sys", search_channels=("keyword",), paid_budget=1, cost_cap_usd=1.0)


def test_research_prompt_has_the_block_and_the_profile_records_edges_and_contradiction(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    JsonProfileStore().save(_profile("prof_old", "Congo cobalt ban", entities=["Congo"], claims=[
        ("clm_old", "Congo banned cobalt exports", "confirmed", "high", "2026-02-01")]))
    produced = SignalProfile(
        id="x", title="Congo cobalt ban revisited",
        source_ledger=[SourceArtifact(id="s1", url="https://news.example/lift")],
        claim_ledger=[Claim(id="c1", text="Congo lifted the cobalt export ban", status="likely", supported_by=["s1"],
                            contradicts_claims=["clm_old", "clm_invented"])])
    seen: list[str] = []
    graph = _graph(_ctx([]), monkeypatch, produced, seen)
    out = graph.invoke({"vector": {"id": "vec_new", "title": "Congo cobalt ban", "thesis": "what changed"}})

    assert "WHAT WE ALREADY KNOW" in seen[0] and "[clm_old] (confirmed, 2026-02-01)" in seen[0]
    assert "STARTING POINT, NOT TRUTH" in seen[0] and "contradicts_claims" in seen[0]
    prof = out["profile"]
    assert prof["related_profiles"] == ["prof_old"]
    assert prof["corpus_context"] and prof["corpus_context"][0].startswith("clm_old [confirmed]")
    assert prof["claim_ledger"][0]["contradicts_claims"] == ["clm_old"]      # invented id dropped
    saved = JsonProfileStore().get("prof_new")
    assert saved is not None and saved.related_profiles == ["prof_old"]
    assert JsonProfileStore().get("prof_old").claim_ledger[0].contradicts_claims == []   # the old one is never touched


def test_research_with_an_empty_corpus_adds_no_block(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    seen: list[str] = []
    graph = _graph(_ctx([]), monkeypatch, SignalProfile(id="x", title="t"), seen)
    out = graph.invoke({"vector": {"id": "vec_n", "title": "Lonely topic", "thesis": "t"}})
    assert "WHAT WE ALREADY KNOW" not in seen[0] and out["profile"]["related_profiles"] == []
    assert "WHAT WE ALREADY KNOW" not in build_vector_message({"id": "v", "title": "t"})


def test_finalize_profile_without_shown_ids_clears_contradiction_pointers() -> None:
    p = SignalProfile(id="m", title="t", claim_ledger=[Claim(id="c1", text="a", contradicts_claims=["clm_x"])])
    assert finalize_profile(p, {"id": "vec_a"}, {}, model="m", generator="g", stage="s").claim_ledger[0].contradicts_claims == []


# ── intel desk wiring ────────────────────────────────────────────────────────────────────────────
SRC_OLD = "https://pub.example/clm_h"


def _theater():
    return Theater(id="thr_a", name="Hormuz", why="shipping lane", members=[
        {"edition": "2026-09-29-0800", "n": 1, "title": "Hormuz transits", "thesis": "t", "sources": ["https://w.example/a"]}])


def _desk_store(tmp_path):
    return _store(tmp_path, _profile("prof_old", "Hormuz history", claims=[
        ("clm_h", "Hormuz was mined in 1988", "confirmed", "high", "2026-01-10"),
        ("clm_recent", "Hormuz transits fell this week", "confirmed", "high", "2026-09-28")]))


def test_recall_returns_claims_older_than_the_window_and_skips_this_runs_profiles(tmp_path) -> None:
    store = _desk_store(tmp_path)
    found = br.recall(_theater(), as_of="2026-09-29", window_days=3, store=store)
    assert [c.claim_id for c in found.claims] == ["clm_h"]
    assert br.recall(_theater(), as_of="2026-09-29", window_days=3, exclude_ids=["prof_old"], store=store).empty
    assert "OUR EARLIER RESEARCH" in br.corpus_block(found) and br.corpus_block(corpus.CorpusContext()) == ""


class _Model:
    def __init__(self, result, tasks):
        self.result, self.tasks = result, tasks

    def with_structured_output(self, _schema):
        return self

    def invoke(self, messages, **_k):
        self.tasks.append(messages[1].content)
        return self.result


def _ictx(result, tasks):
    model = _Model(result, tasks)
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


def test_daily_writer_gets_corpus_block_and_its_urls_become_citable(tmp_path) -> None:
    found = br.recall(_theater(), as_of="2026-09-29", window_days=3, store=_desk_store(tmp_path))
    tasks: list[str] = []
    draft = SectionDraft(bottom_line="b", context=[ContextItem(what="mined 1988", source=SRC_OLD, verification="researched"),
                                  ContextItem(what="invented", source="https://invented.example", verification="researched"),
                                  ContextItem(what="no source", verification="researched")],
                         developments=[Development(headline="d", sources=[SRC_OLD], verification="researched")])
    out, urls = daily.write_section(_ictx(draft, tasks), None, _theater(), {}, as_of="2026-09-29", profiles=[],
                                    pulse_table={}, model_spec=None, corpus_ctx=found)
    assert "OUR EARLIER RESEARCH" in tasks[0] and "[clm_h]" in tasks[0] and SRC_OLD in urls
    clean = daily.normalise_section(out, pulse_table={}, has_previous=False, researched=not found.empty,
                                    research_urls=urls, reported_urls=set())
    assert [c.verification for c in clean.context] == ["researched", "reported", "reported"]
    assert clean.context[0].source == SRC_OLD and clean.context[1].source == ""


def test_brief_analyst_gets_corpus_block_and_timeline_researched_needs_a_known_url(tmp_path) -> None:
    found = br.recall(_theater(), as_of="2026-09-29", window_days=30, store=_desk_store(tmp_path))
    tasks: list[str] = []
    result = Brief(title="t", bottom_line="b", timeline=[
        TimelineItem(date="2026-01-10", what="mined", verification="researched", source=SRC_OLD),
        TimelineItem(date="2026-01-11", what="made up", verification="researched", source="https://nope.example")])
    brief = br.write_brief(_ictx(result, tasks), None, _theater(), {}, profiles=[], pulse_table={}, model_spec=None,
                           corpus_ctx=found)
    assert "OUR EARLIER RESEARCH" in tasks[0] and "[clm_h]" in tasks[0]
    assert [t.verification for t in brief.timeline] == ["researched", "reported"]


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────
def test_cli_related_prints_profiles_and_claims(monkeypatch, tmp_path, capsys) -> None:
    from argparse import Namespace

    from algent_backend.cli.newsroom import corpus as cli

    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    JsonProfileStore().save(_profile("prof_a", "Cobalt ban", entities=["Congo"],
                                     claims=[("clm_a", "Congo banned cobalt exports", "confirmed", "high", "2026-02-01")]))
    args = Namespace(verb="related", text="Congo cobalt", json=False, budget=None, limit=None)
    assert cli.run_corpus(args) == 0
    out = capsys.readouterr().out
    assert "prof_a" in out and "[clm_a] (confirmed, 2026-02-01)" in out
    assert cli.run_corpus(Namespace(verb="related", text="  ", json=False, budget=None, limit=None)) == 2
