"""Never waste work already done: the daily and briefs reuse saved research, never double-apply it to the
Pulses, and a run that wrote nothing persists and publishes nothing."""

from __future__ import annotations

import json

import pytest

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.intel import daily, desk
from algent_backend.agent_system.agents.intel.contracts import Brief, Escalation, Theater
from algent_backend.agent_system.agents.pulse import PulseStore, repository
from algent_backend.agent_system.agents.pulse import update as pulse_update
from algent_backend.agent_system.agents.pulse.contracts import Influence, Pulse, PulseDefinition, Situation, Source
from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile, SourceArtifact
from algent_backend.agent_system.agents.research.store import JsonProfileStore

from test_intel_daily import AS_OF, SUMMARY, _board, _ctx, _draft, _store

DAY_TAG = AS_OF.replace("-", "")


def _profile(pid: str, *, claims: bool = True, generated_at: str = f"{AS_OF}T10:00:00+00:00") -> SignalProfile:
    return SignalProfile(id=pid, title=pid, generated_at=generated_at,
                         source_ledger=[SourceArtifact(id="src_1", url="https://x.example/a")] if claims else [],
                         claim_ledger=[Claim(id="clm_1", text="a claim", supported_by=["src_1"])] if claims else [])


def _daily_ids() -> dict[str, str]:
    return {"thr_a": f"prof_intel_a_daily_{DAY_TAG}", "thr_b": f"prof_intel_b_daily_{DAY_TAG}"}


class _Commission:
    """Stands in for the paid research agent: counts calls, returns a saved-shape profile."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, _ctx, _cfg, theater, **kw):
        self.calls.append(theater.id)
        pid = f"prof_{br.research_vector_id(theater, id_tag=kw.get('id_tag', ''))}"
        return _profile(pid, generated_at="2026-09-29T23:00:00+00:00").model_dump(mode="json")


@pytest.fixture
def desk_env(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    applied: list[dict] = []
    monkeypatch.setattr(pulse_update, "update_quietly", lambda prof, **kw: applied.append({"id": prof["id"], **kw}) or {})
    commission = _Commission()
    monkeypatch.setattr(br, "commission_research", commission)
    return commission, applied


def _run(**kw) -> dict:
    ctx = _ctx({"Alpha": _draft(), "Bravo": _draft(pulses=[])}, SUMMARY)
    return daily.produce_daily(ctx, domain="geopolitics", top=5, research=True, model_spec=None, as_of=AS_OF,
                               board=_board(), **kw)


# ── reuse ─────────────────────────────────────────────────────────────────────────────────────
def test_a_rerun_reuses_saved_profiles_with_zero_research_calls(desk_env) -> None:
    commission, applied = desk_env
    store = JsonProfileStore()
    for pid in _daily_ids().values():
        store.save(_profile(pid))
    res = _run()
    assert commission.calls == []                                           # no research was commissioned
    assert all(r["research_reused"] is True and r["research_usd"] == 0.0 and r["researched"] for r in res["theaters"])
    assert res["research_usd"] == 0.0 and res["report"]["researched"] is True
    # still fed to the Pulses, but with once=True so a rerun cannot apply it twice
    assert sorted(a["id"] for a in applied) == sorted(_daily_ids().values())
    assert all(a["once"] is True and a["run_id"] == a["id"] for a in applied)


def test_a_partial_profile_with_an_empty_ledger_is_researched_again(desk_env) -> None:
    commission, _applied = desk_env
    store = JsonProfileStore()
    store.save(_profile(_daily_ids()["thr_a"]))                             # complete: reused
    store.save(_profile(_daily_ids()["thr_b"], claims=False))               # cut short by a failed run
    res = _run()
    assert commission.calls == ["thr_b"]
    by = {r["theater"]: r for r in res["theaters"]}
    assert by["thr_a"]["research_reused"] is True and by["thr_b"]["research_reused"] is False


def test_fresh_research_forces_new_research_even_when_a_profile_exists(desk_env) -> None:
    commission, _applied = desk_env
    for pid in _daily_ids().values():
        JsonProfileStore().save(_profile(pid))
    res = _run(fresh_research=True)
    assert sorted(commission.calls) == ["thr_a", "thr_b"]
    assert not any(r["research_reused"] for r in res["theaters"])


def test_a_briefs_research_is_reused_only_if_built_today() -> None:
    theater = Theater(id="thr_x", name="X")
    pid = f"prof_{br.research_vector_id(theater)}"
    JsonProfileStore().save(_profile(pid, generated_at="2026-09-20T10:00:00+00:00"))
    assert br.reusable_research(theater, on_date=AS_OF) is None            # an older brief's research is stale
    JsonProfileStore().save(_profile(pid, generated_at=f"{AS_OF}T08:00:00+00:00"))
    assert br.reusable_research(theater, on_date=AS_OF)["id"] == pid
    focused = br.research_vector_id(theater, focus="who pays?")
    assert focused != br.research_vector_id(theater)                       # a focused brief has its own id


def test_produce_reuses_todays_brief_research_and_says_so(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "store"))
    theater = Theater(id="thr_x", name="Russia vs Europe")
    JsonProfileStore().save(_profile(f"prof_{br.research_vector_id(theater)}", generated_at=f"{AS_OF}T08:00:00+00:00"))
    commission = _Commission()
    monkeypatch.setattr(br, "commission_research", commission)
    monkeypatch.setattr(pulse_update, "update_quietly", lambda *_a, **_k: {})
    from test_intel_page import _Model

    ctx = type("X", (), {"model_resolver": type("R", (), {"resolve": lambda _s, _spec: type("C", (), {"client": _Model(
        Brief(title="T", bottom_line="bl", escalation=Escalation(direction="rising", pace="fast")))})()})()})()
    row = desk.produce(ctx, theater, {}, as_of=AS_OF, research=True)
    assert commission.calls == [] and row["research_reused"] is True and row["research_usd"] == 0.0


# ── pulses are not moved twice ────────────────────────────────────────────────────────────────
def _pulse_env(tmp_path, monkeypatch) -> PulseStore:
    store = PulseStore(tmp_path / "pulses")
    store.save_situation(Situation(id="sit_a", title="Alpha", status="active"))
    store.create_pulse(Pulse(id="pls_h", situation_id="sit_a", name="H",
                             definitions=[PulseDefinition(question="q", low_end="lo", high_end="hi")]))
    monkeypatch.setattr(repository, "pulse_store", lambda: store)
    return store


def test_a_profile_already_applied_by_this_run_is_not_fed_to_the_pulses_again(tmp_path, monkeypatch) -> None:
    store = _pulse_env(tmp_path, monkeypatch)
    prof = _profile("prof_p", generated_at="2026-09-29T10:00:00+00:00").model_dump(mode="json")
    store.append(Influence(pulse_id="pls_h", at="2026-09-29T12:00:00+00:00", mode="article", definition_version=1,
                           proposed_position=40, decision="applied", rationale="r", key="k1",
                           source=Source(run_id="prof_p", stage="pulse_update", profile_id="prof_p")))
    calls: list[str] = []
    monkeypatch.setattr(pulse_update, "update_from_profile", lambda *a, **k: calls.append("ran") or {"touched": []})
    out = pulse_update.update_quietly(prof, run_id="prof_p", once=True)
    assert out["skipped"] and calls == []                                   # no model call, no influence
    assert len(store.log("pls_h")) == 1
    pulse_update.update_quietly(prof, run_id="prof_p")                      # once defaults off: article rail unchanged
    assert calls == ["ran"]


def test_freshly_redone_research_under_the_same_id_still_applies(tmp_path, monkeypatch) -> None:
    store = _pulse_env(tmp_path, monkeypatch)
    store.append(Influence(pulse_id="pls_h", at="2026-09-28T12:00:00+00:00", mode="article", definition_version=1,
                           proposed_position=40, decision="applied", rationale="r", key="k1",
                           source=Source(run_id="prof_p", stage="pulse_update", profile_id="prof_p")))
    newer = _profile("prof_p", generated_at="2026-09-29T10:00:00+00:00").model_dump(mode="json")
    assert pulse_update.already_applied(store, newer, "prof_p") is False    # influence predates this research
    assert pulse_update.already_applied(store, newer | {"generated_at": "2026-09-28T01:00:00+00:00"}, "prof_p")
    assert pulse_update.already_applied(store, newer, "some-other-run") is False


# ── a run that wrote nothing is a failed run ──────────────────────────────────────────────────
def test_a_daily_with_no_section_written_persists_nothing_and_reports_an_error(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    boom = RuntimeError("400 additionalProperties")
    ctx = _ctx({"Alpha": boom, "Bravo": boom}, SUMMARY)
    res = daily.produce_daily(ctx, domain="geopolitics", top=5, model_spec=None, as_of=AS_OF, board=_board(),
                              out=tmp_path)
    assert res["report"] is None and "no theater section was written" in res["error"]
    assert "path" not in res and "html" not in res
    assert not (tmp_path / "intel" / "daily").exists()
    assert not (tmp_path / "daily_geopolitics.html").exists()


def test_the_cli_skips_publish_and_exits_nonzero_on_a_failed_daily(tmp_path, monkeypatch, capsys) -> None:
    from algent_backend.cli.newsroom import intel as cli
    from algent_backend.cli.newsroom import pulse as cli_pulse
    from algent_backend.data_backup import sync
    from algent_backend.publishing import intel_page

    monkeypatch.setattr(cli, "_heat", lambda *_a, **_k: 0)
    monkeypatch.setattr(desk, "latest_board", lambda: {"as_of": AS_OF, "theaters": [], "heat": []})
    monkeypatch.setattr(cli, "_ctx", lambda _n: object())
    monkeypatch.setattr(cli, "_out", lambda _a: tmp_path)
    monkeypatch.setattr(daily, "produce_daily", lambda *_a, **_k: {
        "report": None, "theaters": [{"theater": "thr_a", "error": "x"}], "research_usd": 0.0, "error": "nothing"})
    forbidden = lambda *_a, **_k: pytest.fail("must not run after a failed daily")  # noqa: E731
    monkeypatch.setattr(intel_page, "publish_intel", forbidden)
    monkeypatch.setattr(sync, "backup", forbidden)
    monkeypatch.setattr(cli_pulse, "promote_ready_quietly", forbidden)
    args = type("A", (), {"domain": "geopolitics", "top": 5, "research": False, "fresh_research": False})()
    assert cli._daily(args) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "nothing"


def test_an_empty_brief_is_not_persisted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "store"))
    from test_intel_page import _Model

    empty = Brief(title="T", bottom_line="  ", escalation=Escalation(direction="rising", pace="fast"))
    ctx = type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": _Model(empty)})()})()})()
    row = desk.produce(ctx, Theater(id="thr_x", name="Russia vs Europe"), {}, as_of=AS_OF)
    assert "empty brief" in row["error"] and "slug" not in row
    assert not (tmp_path / "store" / "briefs").exists()


def test_the_brief_cli_publishes_nothing_when_no_brief_was_written(tmp_path, monkeypatch, capsys) -> None:
    from algent_backend.cli.newsroom import intel as cli
    from algent_backend.publishing import intel_page

    monkeypatch.setattr(desk, "latest_board", lambda: {"as_of": AS_OF, "theaters": [], "heat": []})
    monkeypatch.setattr(cli, "_produce_briefs", lambda *_a, **_k: [{"theater": "thr_a", "error": "brief failed"}])
    monkeypatch.setattr(intel_page, "publish_intel", lambda: pytest.fail("must not publish"))
    args = type("A", (), {"theater": "thr_a", "top": 1, "research": False, "focus": "", "fresh_research": False})()
    assert cli._brief(args) == 1
    assert "no brief was written" in json.loads(capsys.readouterr().out)["error"]
