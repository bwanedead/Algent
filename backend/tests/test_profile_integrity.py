"""The corpus is the asset: a failed (empty) research result never replaces a complete profile, reuse
finds the newest complete version, empty research is reported as a failure, and `corpus repair` heals
what the old behaviour broke."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.intel import daily
from algent_backend.agent_system.agents.intel.contracts import Theater
from algent_backend.agent_system.agents.research import repair, spec
from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile, SourceArtifact
from algent_backend.agent_system.agents.research.store import JsonProfileStore
from algent_backend.cli.newsroom import corpus as cli

from test_intel_daily import AS_OF, SUMMARY, _board, _ctx, _draft, _store

THEATER = Theater(id="thr_a", name="Alpha")


def _good(pid: str = "prof_x", *, claims: int = 3, at: str = "2026-10-03T12:27:00+00:00", rev: int = 1) -> SignalProfile:
    return SignalProfile(
        id=pid, title="Hormuz", revision=rev, generated_at=at,
        source_ledger=[SourceArtifact(id="src_1", url="https://x.example/a")],
        claim_ledger=[Claim(id=f"clm_{i}", text=f"claim {i}", supported_by=["src_1"]) for i in range(claims)])


def _empty(pid: str = "prof_x", at: str = "2026-10-03T20:41:00+00:00") -> SignalProfile:
    return SignalProfile(id=pid, title="Hormuz", generated_at=at, profile_status="insufficient_evidence")


def _history_file(store: JsonProfileStore, profile: SignalProfile, stamp: str) -> Path:
    d = store.root / "_history" / profile.id
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"r{profile.revision:03d}__{stamp}.json"
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path


def _incident(store: JsonProfileStore, pid: str = "prof_x") -> None:
    """What the old store did: a complete profile, then an empty one saved over it as current."""
    store.save(_good(pid))
    store._write(_empty(pid))  # noqa: SLF001 - bypasses the guard that now prevents this


# ── the definition ────────────────────────────────────────────────────────────────────────────
def test_complete_means_a_sourced_claim_and_a_source_ledger() -> None:
    assert _good().is_complete
    assert not _empty().is_complete
    unsourced = SignalProfile(id="p", title="t", claim_ledger=[Claim(id="c", text="x")],
                              source_ledger=[SourceArtifact(id="s", url="u")])
    assert not unsourced.is_complete                                   # claims, none traced to a source
    assert not SignalProfile(id="p", title="t", claim_ledger=[Claim(id="c", text="x", supported_by=["s"])]).is_complete


# ── the store never lets a failed attempt replace a complete profile ──────────────────────────
def test_an_empty_result_never_replaces_a_complete_profile(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_good())
    path = store.save(_empty())

    assert store.get("prof_x").is_complete and len(store.get("prof_x").claim_ledger) == 3
    assert path == str(tmp_path / "prof_x.json")                       # the kept file is still the current one
    assert len(store.history("prof_x")) == 1                           # history is the record of what was current
    aside = list((tmp_path / "_rejected" / "prof_x").glob("*.json"))
    assert len(aside) == 1                                             # the failed attempt is kept, inspectable
    entry = json.loads((tmp_path / "_rejections.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert entry["id"] == "prof_x" and "not complete" in entry["reason"]
    assert entry["incoming"]["claims"] == 0 and entry["kept"]["claims"] == 3


def test_an_empty_first_result_is_still_saved_and_complete_over_anything_replaces(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_empty())                                               # nothing to protect yet
    assert store.get("prof_x") is not None and not store.get("prof_x").is_complete
    store.save(_empty(at="2026-10-03T21:00:00+00:00"))                 # empty over empty: ordinary save
    assert len(store.history("prof_x")) == 2
    store.save(_good(claims=5))                                        # complete over incomplete
    store.save(_good(claims=7, rev=2))                                 # complete over complete: a new revision
    assert len(store.get("prof_x").claim_ledger) == 7
    assert not (tmp_path / "_rejected").exists()


# ── reuse finds the newest complete version ───────────────────────────────────────────────────
def test_current_complete_restores_the_newest_complete_version_by_time_not_revision(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_good(claims=2, rev=3))                                 # an old, higher revision number
    _history_file(store, _good(claims=9, at="2026-10-03T15:00:00+00:00", rev=1), "99991231T000000000000Z")
    store._write(_empty())  # noqa: SLF001

    found = store.current_complete("prof_x")

    assert found is not None and len(found.claim_ledger) == 9          # newest save, though revision 1
    assert len(store.get("prof_x").claim_ledger) == 9                  # and it is current again
    restored = json.loads((tmp_path / "_restorations.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert restored["id"] == "prof_x" and restored["replaced"]["claims"] == 0 and restored["restored"]["claims"] == 9


def test_current_complete_is_none_when_nothing_complete_exists(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_empty())
    assert store.current_complete("prof_x") is None
    assert store.current_complete("prof_missing") is None
    assert not (tmp_path / "_restorations.jsonl").exists()


def test_the_intel_reuse_check_restores_history_instead_of_rebuying(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    pid = f"prof_{br.research_vector_id(THEATER, id_tag='daily_20261003')}"
    _incident(store, pid)
    found = br.reusable_research(THEATER, id_tag="daily_20261003", on_date="2026-10-03", store=store)
    assert found is not None and found["id"] == pid and len(found["claim_ledger"]) == 3
    assert store.get(pid).is_complete                                  # restored as current, and recorded
    assert (tmp_path / "_restorations.jsonl").exists()
    # the day check still applies to what was found
    assert br.reusable_research(THEATER, id_tag="daily_20261003", on_date="2026-10-04", store=store) is None


# ── empty research is a failure upstream ──────────────────────────────────────────────────────
class _FakeResearch:
    """Stands in for the paid agent, saving what it returns the way the real loop does."""

    def __init__(self, profile: SignalProfile) -> None:
        self.profile = profile

    def __call__(self, _context):
        outer = self

        class _Graph:
            def invoke(self, state, _config):
                prof = outer.profile.model_copy(update={"id": f"prof_{state['vector']['id']}"})
                JsonProfileStore().save(prof)
                return {"profile": prof.model_dump(mode="json")}

        return _Graph()


def test_commission_raises_when_research_comes_back_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path / "ps"))
    monkeypatch.setattr(spec, "build_graph", _FakeResearch(_empty()))
    with pytest.raises(br.EmptyResearch, match="no sourced claims"):
        br.commission_research(object(), None, THEATER)
    monkeypatch.setattr(spec, "build_graph", _FakeResearch(_good()))
    assert br.commission_research(object(), None, THEATER)["id"].startswith("prof_intel_")


def test_a_daily_with_empty_research_says_research_failed_and_keeps_the_good_profile(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path / "ps"))
    day = AS_OF.replace("-", "")
    store = JsonProfileStore()
    for tid in ("thr_a", "thr_b"):
        store.save(_good(f"prof_intel_{tid.removeprefix('thr_')}_daily_{day}"))
    monkeypatch.setattr(spec, "build_graph", _FakeResearch(_empty()))
    ctx = _ctx({"Alpha": _draft(), "Bravo": _draft(pulses=[])}, SUMMARY)

    res = daily.produce_daily(ctx, domain="geopolitics", top=5, research=True, model_spec=None, as_of=AS_OF,
                              board=_board(), fresh_research=True)

    for row in res["theaters"]:
        assert row["researched"] is False and "EmptyResearch" in row["research_error"]
    assert res["report"]["researched"] is False                        # written from headlines, and says so
    for tid in ("a", "b"):
        assert store.get(f"prof_intel_{tid}_daily_{day}").is_complete  # the corpus was not degraded


# ── repair ────────────────────────────────────────────────────────────────────────────────────
def test_repair_plans_without_writing_and_apply_restores(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    _incident(store, "prof_hurt")
    store.save(_good("prof_fine"))
    store.save(_empty("prof_hopeless"))                                # empty, and nothing better ever existed

    plan = repair.plan(store)
    assert [r.profile_id for r in plan] == ["prof_hurt"]
    assert plan[0].current["claims"] == 0 and plan[0].restored["claims"] == 3
    assert not store.get("prof_hurt").is_complete and not (tmp_path / "_restorations.jsonl").exists()

    repair.apply(store, plan)
    assert store.get("prof_hurt").is_complete and repair.plan(store) == []
    assert (tmp_path / "_restorations.jsonl").exists()


def test_the_cli_repair_verb_is_a_dry_run_unless_applied(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    store = JsonProfileStore()
    _incident(store)

    assert cli.run_corpus(Namespace(verb="repair", apply=False, json=False)) == 0
    out = capsys.readouterr().out
    assert "WOULD RESTORE  prof_x" in out and "dry run" in out
    assert not store.get("prof_x").is_complete

    assert cli.run_corpus(Namespace(verb="repair", apply=True, json=False)) == 0
    assert "RESTORED  prof_x" in capsys.readouterr().out
    assert store.get("prof_x").is_complete
    assert cli.summarize(store)["integrity"]["restorations"] == 1


def test_history_is_truly_append_only_even_within_one_clock_tick(tmp_path: Path) -> None:
    # Windows' clock ticks ~15 ms: rapid saves once shared a history filename and the later one erased
    # the earlier — the very version repair and reuse depend on. Every save must leave its own file.
    store = JsonProfileStore(tmp_path)
    for _ in range(25):
        store._write(_good("prof_burst"))  # noqa: SLF001 - the raw write path every save goes through
    assert len(store.history("prof_burst")) == 25
