"""Origin chains: repeats are told from independent sources, deterministically and without a model."""

from __future__ import annotations

import pytest

from algent_backend.experiment import origins, runner, sources, store
from algent_backend.experiment.contracts import Evidence, Question

WIRE = "Iran said on Tuesday that it would keep the Strait of Hormuz closed to tanker traffic until sanctions are lifted, officials in Tehran told reporters"


def doc(i: str, pub: str, body: str = "", url: str = "", title: str = "") -> Evidence:
    return Evidence(id=i, kind="article", title=title, body=body, publish_time=pub, url=url)


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))


def test_same_canonical_url_is_one_chain():
    a = doc("a", "2026-03-01", "x", "https://www.Example.com/story/1/?utm_source=tw")
    b = doc("b", "2026-03-02", "y", "http://example.com/story/1")
    c = doc("c", "2026-03-02", "z", "https://example.com/story/2")
    got = origins.chains([b, a, c])
    assert got["a"] == got["b"] == "a" and got["c"] == "c"


def test_near_duplicate_text_is_one_chain_and_the_earliest_is_the_origin():
    wire = doc("wire", "2026-03-01", WIRE)
    echo = doc("echo", "2026-03-02", WIRE + " and more")                     # a rewrite of the same wire copy, a little longer
    other = doc("other", "2026-03-02", "Oil prices drifted lower on weak demand as inventories rose across the main trading hubs this week according to traders")
    got = origins.chains([echo, other, wire])
    assert got == {"wire": "wire", "echo": "wire", "other": "other"}
    ann = {e.id: e for e in origins.annotate([echo, other, wire])}
    assert ann["wire"].origin_chain == [] and ann["echo"].origin_chain == ["wire"] and ann["other"].origin_chain == []
    assert origins.summary([ann["wire"], ann["echo"], ann["other"]]) == {"method": origins.METHOD, "n_shown": 3, "n_independent": 2}
    assert origins.summary([ann["echo"]])["n_independent"] == 1                  # a repeat shown without its origin is still one voice


def test_short_texts_never_match_by_text_and_the_result_is_deterministic():
    a, b = doc("a", "2026-03-01", "No change."), doc("b", "2026-03-02", "No change.")
    assert origins.chains([a, b]) == {"a": "a", "b": "b"}
    items = [doc(str(i), f"2026-03-0{1 + i % 5}", WIRE if i % 2 else WIRE + " extra") for i in range(8)]
    assert origins.chains(items) == origins.chains(list(reversed(items)))


def test_a_snapshot_carries_chains_and_the_manifest_counts_independent_sources():
    items = [doc("wire", "2026-03-01", WIRE, title="Hormuz"), doc("echo", "2026-03-02", WIRE + " and more", title="Hormuz again"),
             doc("solo", "2026-03-03", "Talks between the two delegations resumed in Muscat with mediators from Oman present at the table for a second day", title="Talks")]
    q = Question(id="q", text="t", cutoff="2026-03-10T12:00:00+00:00")
    sid, snap, meta = runner.build_snapshot(sources.ListSource(items), q)
    by = {e.id: e for e in snap}
    assert by["echo"].origin_chain == ["wire"] and meta["origin_method"] == origins.METHOD
    assert [e.origin_chain for e in runner.load_snapshot(sid)[0] if e.id == "echo"] == [["wire"]]       # stored and reloaded
    assert store.read_json(f"snapshots/{sid}.json")["items"][0]["id"]
