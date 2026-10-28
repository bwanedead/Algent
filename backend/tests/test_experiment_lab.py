"""Experiment lab, phase 1: the machinery (stubbed models, temp stores). Six properties from docs/architecture/experiment-framework.md."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from algent_backend.experiment import access, branches, policies, runner, score, sources, store
from algent_backend.experiment.contracts import Evidence, Observation, Question

CUTOFF = "2026-03-10T12:00:00+00:00"


def ev(i: str, pub: str, body: str = "", acq: str = "", title: str = "") -> Evidence:
    return Evidence(id=i, kind="article", source="test", title=title, body=body, publish_time=pub, event_time=pub, acquired_at=acq or pub)


DOCS = [
    ev("d1", "2026-03-01", "Talks between Aldoria and Brevia on a ceasefire stalled", title="ceasefire talks"),
    ev("d2", "2026-03-09", "Oil prices drifted lower on weak demand", title="oil"),
    ev("d3", "2026-03-05", "Aldoria ceasefire monitors deployed along the border", title="ceasefire monitors"),
    ev("late-pub", "2026-03-20", "Ceasefire signed between Aldoria and Brevia", title="ceasefire signed"),
    ev("late-acq", "2026-03-02", "Ceasefire background", acq="2026-03-25T00:00:00+00:00", title="ceasefire background"),
    Evidence(id="no-date", body="ceasefire aldoria", acquired_at="2026-03-01T00:00:00+00:00"),
]
Q = Question(id="q1", text="Will Aldoria and Brevia sign a ceasefire by 2026-03-31?", rules="Resolves YES if a ceasefire agreement is signed.",
             cutoff=CUTOFF, closes_at="2026-03-31T00:00:00+00:00", source="market:m1", reference={"market_p": 0.4, "base_rate": 0.2})


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))


def stub(p: float, cited_first: bool = True):
    seen: list[str] = []

    def ask(task: str, role: str):
        seen.append(task)
        ids = [t.split("]")[0][1:] for t in task.splitlines() if t.startswith("[")]
        return SimpleNamespace(probability=p, rationale="because", cited=ids[:1] if cited_first else []), 0.01

    ask.seen = seen  # type: ignore[attr-defined]
    return ask


def setup_pair():
    p0 = policies.freeze_blind_forecaster()
    p1 = policies.replace_policy(p0, policies.evidence_policy("keyword-overlap", k=2), "p1")
    return branches.ensure("p0", p0), branches.ensure("p1", p1)


def run_pair(asks=None):
    b0, b1 = setup_pair()
    a0, a1 = asks or (stub(0.3), stub(0.6))
    table = {b0.protocol_id: a0, b1.protocol_id: a1}
    return b0, b1, runner.run_controlled(Q, [b0, b1], sources.ListSource(DOCS), lambda proto: table[proto.id])


def test_1_what_each_protocol_saw_is_reconstructable():
    b0, b1, recs = run_pair()
    for r in recs:
        man = store.read_json(f"runs/{r.run_id}/manifest.json")
        prompt = store.path(f"runs/{r.run_id}/prompt.txt").read_text(encoding="utf-8")
        assert man["cutoff"] == CUTOFF and man["snapshot"] == r.snapshot and man["time_bounds"]["cutoff"] == CUTOFF
        assert [s["id"] for s in man["shown"]] and all(f"[{s['id']}]" in prompt for s in man["shown"])
        assert all(s["content_hash"] and s["publish_time"] for s in man["shown"])
        assert not runner.verify(r.run_id)
    shown = {r.branch_id: [s["id"] for s in store.read_json(f"runs/{r.run_id}/manifest.json")["shown"]] for r in recs}
    assert shown[b0.id] != shown[b1.id]                           # the one changed policy changed what was shown
    assert recs[0].snapshot == recs[1].snapshot                   # ... over the same evidence snapshot


def test_2_branches_cannot_read_each_others_private_state():
    b0, b1, _ = run_pair()
    assert branches.read_memory(b0.id, caller=b0.id)
    with pytest.raises(access.AccessDenied):
        branches.read_memory(b0.id, caller=b1.id)
    with pytest.raises(access.AccessDenied):
        branches.append_memory(b0.id, Observation(id="x", source_ids=["d1"], method="m", method_version="1", text="t", derived_at=CUTOFF, branch=b0.id), caller=b1.id)
    # even handed another branch's note, the reader refuses it
    note = branches.read_memory(b0.id, caller=b0.id)[0]
    rd = access.Reader(DOCS, [], [note], cutoff="2030-01-01T00:00:00+00:00", branch=b1.id)
    assert rd.memory() == []
    # and p0's conclusion never appears in p1's prompt
    assert "->" not in store.path(f"runs/{store.listing('runs')[0]}/prompt.txt").read_text(encoding="utf-8")


def test_3_every_derived_object_names_source_and_method():
    b0, b1, recs = run_pair()
    for b, r in zip((b0, b1), recs):
        shown = {s["id"] for s in store.read_json(f"runs/{r.run_id}/manifest.json")["shown"]}
        notes = branches.read_memory(b.id, caller=b.id)
        assert notes
        for n in notes:
            assert n.source_ids and set(n.source_ids) <= shown and n.method and n.method_version and n.derived_at and n.as_of == CUTOFF
        out = store.read_json(f"runs/{r.run_id}/output.json")
        assert set(out["cited"]) <= shown and out["trace"]["policies"]["prompts"].startswith("prompts/")
    bad = Observation(id="orphan", source_ids=[], method="", method_version="", text="x", derived_at="2026-01-01T00:00:00+00:00")
    assert access.observation_ok(bad, CUTOFF, "", set())              # a derived object without provenance is refused


def test_4_branching_and_changing_a_policy_preserves_the_original():
    b0, _ = setup_pair()
    runner.run_controlled(Q, [b0], sources.ListSource(DOCS), lambda proto: stub(0.3))
    proto_before = store.path(f"protocols/{b0.protocol_id}.json").read_bytes()
    mem_before = store.path(f"branches/{b0.id}/memory.jsonl").read_bytes()
    child = branches.fork(b0, "p0-fork", policies.replace_policy(policies.load_protocol(b0.protocol_id), policies.evidence_policy("keyword-overlap", k=3), "fork"))
    assert child.parent == b0.id and child.protocol_id != b0.protocol_id
    assert child.forked_memory_digest == store.digest(mem_before.decode()) == branches.memory_digest(b0.id)
    q2 = Q.model_copy(update={"id": "q2", "text": "Will oil fall below 50?"})
    runner.run_controlled(q2, [child], sources.ListSource(DOCS), lambda proto: stub(0.7))
    assert len(branches.read_memory(child.id, caller=child.id)) == 2   # the fork moved on ...
    assert store.path(f"protocols/{b0.protocol_id}.json").read_bytes() == proto_before   # ... the original did not
    assert store.path(f"branches/{b0.id}/memory.jsonl").read_bytes() == mem_before
    assert policies.load_protocol(b0.protocol_id).policies["evidence"].name == "recent-k"
    with pytest.raises(store.Immutable):
        store.write_once(f"protocols/{b0.protocol_id}.json", {"changed": True})


def test_5_nothing_after_the_cutoff_leaks_including_derived_objects():
    snap, items, meta = runner.build_snapshot(sources.ListSource(DOCS), Q)
    ids = {e.id for e in items}
    assert ids == {"d1", "d2", "d3"}
    assert dict(meta["excluded"]) == {"late-pub": "published after cutoff", "late-acq": "acquired after cutoff", "no-date": "publish time unknown"}
    # derived objects: made after the cutoff (even about old things), or built on a hidden source, or private to someone else
    good = Observation(id="ok", source_ids=["d1"], method="summarise", method_version="1", text="s", derived_at="2026-03-09T00:00:00+00:00")
    after = good.model_copy(update={"id": "after", "derived_at": "2026-04-01T00:00:00+00:00"})
    hidden = good.model_copy(update={"id": "hidden", "source_ids": ["late-pub"]})
    chained = good.model_copy(update={"id": "chained", "source_ids": ["ok"]})
    chained_bad = good.model_copy(update={"id": "cbad", "source_ids": ["hidden"]})
    mine = good.model_copy(update={"id": "mine", "branch": "b", "as_of": "2026-03-01T00:00:00+00:00"})
    future_mine = mine.model_copy(update={"id": "fmine", "as_of": "2026-04-01T00:00:00+00:00"})
    rd = access.Reader(DOCS, [good, after, hidden, chained, chained_bad], [mine, future_mine], cutoff=CUTOFF, branch="b")
    assert {o.id for o in rd.observations()} == {"ok", "chained"} and [m.id for m in rd.memory()] == ["mine"]
    # a policy that tries to return something outside what it was allowed is clipped; no late document reaches the prompt
    b0, _ = setup_pair()
    greedy = policies.RETRIEVERS[("recent-k", 1)]
    policies.RETRIEVERS[("recent-k", 1)] = lambda it, q, p: [*greedy(it, q, p), DOCS[3]]
    try:
        rec = runner.run_controlled(Q, [b0], sources.ListSource(DOCS), lambda proto: stub(0.3))[0]
    finally:
        policies.RETRIEVERS[("recent-k", 1)] = greedy
    assert "late-pub" not in store.path(f"runs/{rec.run_id}/prompt.txt").read_text(encoding="utf-8")
    assert not {s["id"] for s in store.read_json(f"runs/{rec.run_id}/manifest.json")["shown"]} & {"late-pub", "late-acq", "no-date"}


def test_6_the_experiment_stays_auditable_after_code_changes(monkeypatch):
    from algent_backend.markets import forecast as fc

    b0, b1, recs = run_pair()
    before = {r.run_id: (store.path(f"runs/{r.run_id}/prompt.txt").read_text(encoding="utf-8"), store.read_json(f"runs/{r.run_id}/output.json")) for r in recs}
    # production's prompt and the lab's own retrievers change afterwards
    monkeypatch.setattr(fc, "ROLE", "A completely different role.")
    monkeypatch.setitem(policies.RETRIEVERS, ("recent-k", 1), lambda it, q, p: [])
    monkeypatch.setitem(policies.RETRIEVERS, ("keyword-overlap", 1), lambda it, q, p: [])
    assert policies.freeze_blind_forecaster().id == b0.protocol_id             # P0 is the stored capture, not today's code
    assert policies.load_protocol(b0.protocol_id).policies["prompts"].params["role"].startswith("You are a forecaster")
    for r in recs:
        assert not runner.verify(r.run_id)
        assert (store.path(f"runs/{r.run_id}/prompt.txt").read_text(encoding="utf-8"), store.read_json(f"runs/{r.run_id}/output.json")) == before[r.run_id]
    def boom(task, role):
        raise AssertionError("paid work redone")

    again = runner.run_controlled(Q, [b0, b1], sources.ListSource(DOCS), lambda proto: boom)     # same (question, protocol, snapshot): never redone
    assert {a.p for a in again} == {0.3, 0.6}
    # tamper detection: an edited output no longer matches its record
    p = store.path(f"runs/{recs[0].run_id}/output.json")
    p.write_text(p.read_text(encoding="utf-8").replace('"p": 0.3', '"p": 0.9'), encoding="utf-8")
    assert runner.verify(recs[0].run_id)


def test_scoring_one_rule_for_both_and_abstentions_counted(monkeypatch):
    from algent_backend.markets import store as ms
    from algent_backend.markets.contracts import Market

    b0, b1 = setup_pair()
    recs = runner.run_controlled(Q, [b0, b1], sources.ListSource(DOCS), lambda proto: stub(0.3 if proto.id == b0.protocol_id else 0.8))
    assert score.scoreboard()["unresolved"] == ["q1"]
    ms.save_markets([Market(id="m1", question=Q.text, status="resolved", outcome="yes", resolved_at="2026-03-25T00:00:00+00:00")])
    board = score.scoreboard()
    per = board["modes"]["controlled"]["protocols"]
    assert per[b0.protocol_id]["brier"] == pytest.approx(0.49) and per[b1.protocol_id]["brier"] == pytest.approx(0.04)
    assert per[b1.protocol_id]["brier_minus_market"] == pytest.approx(0.04 - 0.36)
    assert per[b0.protocol_id]["usd"] == 0.01 and board["unresolved"] == []
    diff = next(iter(board["modes"]["controlled"]["differences"].values()))
    assert diff["n_shared"] == 1 and diff["se"] is None                         # one question: no uncertainty claim
    assert store.read_json("resolutions/q1.json")["rule"] == score.RULE
    # an unusable answer is stored as an abstention and shows in the board
    q3 = Q.model_copy(update={"id": "q3"})
    runner.run_controlled(q3, [b0], sources.ListSource(DOCS), lambda proto: lambda t, r: (SimpleNamespace(probability=None), 0.0))
    ms.save_markets([Market(id="m1", question=Q.text, status="resolved", outcome="yes", resolved_at="2026-03-25T00:00:00+00:00", description="x")])
    assert score.scoreboard()["modes"]["controlled"]["protocols"][b0.protocol_id]["abstained"] == 1
    assert recs


def test_question_from_market_keeps_price_as_reference_and_requires_precutoff(monkeypatch):
    from algent_backend.markets import store as ms
    from algent_backend.markets.contracts import Market, Snapshot

    ms.save_markets([Market(id="m9", question="Will X happen?", description="rules", status="resolved", outcome="no", resolved_at="2026-03-20T00:00:00+00:00",
                            end_date="2026-03-19T00:00:00+00:00")])
    ms.append_snapshots([Snapshot(market_id="m9", at="2026-03-10T06:00:00+00:00", p=0.37)])
    q = sources.question_from_market("m9", CUTOFF)
    assert q.reference["market_p"] == 0.37 and "0.37" not in q.text + q.rules
    with pytest.raises(ValueError):
        sources.question_from_market("m9", "2026-03-21T00:00:00+00:00")


def test_frozen_task_format_matches_production_today():
    """Drift detector: the transcribed task template must render like markets.forecast.task_for (if this fails, production's prompt changed since capture)."""
    from algent_backend.markets import evidence as evmod
    from algent_backend.markets import forecast as fc
    from algent_backend.markets.contracts import Market

    p0 = policies.freeze_blind_forecaster()
    q = Question(id="x", text="Will X?", rules="rules text", cutoff="2026-03-10T12:00:00+00:00", closes_at="2026-03-31T00:00:00+00:00")
    m = Market(id="x", question="Will X?", description="rules text", end_date="2026-03-31T00:00:00+00:00")
    got = policies.render_task(p0, q, [])
    want = fc.task_for(m, evmod.Evidence(text="", ids=[], n_blocks=0), date(2026, 3, 10))
    assert got.split("ENDS:")[0] == want.split("ENDS:")[0]
    assert got.split("RESOLUTION RULES")[1] == want.split("RESOLUTION RULES")[1]


def test_corpus_source_maps_documents_and_declares_acquisition_unreliable(tmp_path):
    import sqlite3

    db = tmp_path / "corpus.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE documents (id TEXT, kind TEXT, product TEXT, title TEXT, body TEXT, date TEXT, ingested_at TEXT)")
    con.executemany("INSERT INTO documents VALUES (?,?,?,?,?,?,?)", [("a", "daily", "dailies", "t", "ceasefire", "2026-03-09", "2026-03-09T05:00:00+00:00"),
                                                                    ("b", "daily", "dailies", "t", "later", "2026-03-30", "2026-03-30T05:00:00+00:00")])
    con.commit()
    con.close()
    src = sources.CorpusSource(db)
    assert src.acquired_known is False
    sid, items, meta = runner.build_snapshot(src, Q)
    assert [e.id for e in items] == ["a"] and meta["acquired_known"] is False


def test_a_percent_answer_is_read_as_a_fraction_not_dropped():
    from algent_backend.markets.forecast import as_probability
    assert as_probability(0.3) == 0.3 and as_probability(2.0) == 0.02 and as_probability(55) == 0.55
    assert as_probability(150) is None and as_probability(-1) is None and as_probability(None) is None and as_probability(True) is None
