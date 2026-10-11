"""A targeted daily rerun rewrites only the named section; --repair reuses the saved profile."""

from __future__ import annotations

import json

import pytest

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.intel import daily
from algent_backend.agent_system.agents.pulse import update as pulse_update
from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile, SourceArtifact
from algent_backend.agent_system.agents.research.relink import ClaimLinks, Relink
from algent_backend.agent_system.agents.research.store import JsonProfileStore

from test_intel_daily import AS_OF, SUMMARY, _board, _draft, _store

TAG = AS_OF.replace("-", "")


class _Model:
    def __init__(self, drafts):
        self.drafts, self.schema, self.relinks = drafts, None, 0

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages, **_k):
        if self.schema is Relink:
            self.relinks += 1
            text = messages[1].content
            claim = text.split("CLAIMS:\n[", 1)[1].split("]", 1)[0]
            src = text.split("SOURCES:\n[", 1)[1].split("]", 1)[0]
            return Relink(links=[ClaimLinks(claim_id=claim, source_ids=[src, "src_invented"])])
        if self.schema is daily.DaySummary:
            return SUMMARY
        return next(d for n, d in self.drafts.items() if f"THEATER: {n}" in messages[1].content)


def _ctx(drafts):
    model = _Model(drafts)
    ctx = type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()
    return ctx, model


@pytest.fixture
def day(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(pulse_update, "update_quietly", lambda *a, **k: {})
    calls: list[str] = []
    monkeypatch.setattr(br, "commission_research", lambda _c, _cf, t, **k: calls.append(t.id))
    return calls


def _profile(pid: str, *, linked: bool) -> SignalProfile:
    return SignalProfile(id=pid, title=pid, generated_at=f"{AS_OF}T10:00:00+00:00",
                         source_ledger=[SourceArtifact(id="src_1", url="https://x.example/a")],
                         claim_ledger=[Claim(id="clm_1", text="a claim", supported_by=["src_1"] if linked else [])])


def _first_day() -> dict:
    ctx, _ = _ctx({"Alpha": _draft(), "Bravo": _draft(bottom_line="first take")})
    return daily.produce_daily(ctx, domain="geopolitics", top=5, research=False, model_spec=None, as_of=AS_OF,
                               board=_board())["report"]


def _rerun(drafts, **kw):
    ctx, model = _ctx(drafts)
    res = daily.produce_daily(ctx, domain="geopolitics", research=True, model_spec=None, as_of=AS_OF,
                              board=_board(), **kw)
    return res, model


def _by_id(record: dict) -> dict:
    return {s["theater_id"]: s for s in record["theaters"]}


def test_rerun_rewrites_only_the_named_section(day) -> None:
    before = _first_day()
    res, _ = _rerun({"Bravo": _draft(bottom_line="second take")}, only_theaters=["bravo"])
    with open(res["path"], encoding="utf-8") as fh:
        after = json.load(fh)
    assert _by_id(after)["thr_a"] == _by_id(before)["thr_a"]
    assert _by_id(after)["thr_b"]["bottom_line"] == "second take"
    assert after["corrections"][0]["theater_id"] == "thr_b"
    assert after.get("sweep") == before.get("sweep")


def test_unknown_theater_errors_clearly_and_changes_nothing(day) -> None:
    _first_day()
    res, _ = _rerun({}, only_theaters=["nope"])
    assert "not a theater on the board" in res["error"] and "thr_a" in res["error"] and res["report"] is None


def test_repair_makes_one_repair_call_and_no_research(day) -> None:
    _first_day()
    JsonProfileStore().save(_profile(f"prof_intel_b_daily_{TAG}", linked=False))
    res, model = _rerun({"Bravo": _draft(bottom_line="repaired take")}, only_theaters=["thr_b"], repair=True)
    assert day == [] and model.relinks == 1                                  # zero research, one repair call
    row = res["theaters"][0]
    assert row["researched"] and row["research_reused"] and row["research_link_audit"]["claims_relinked"] == 1
    assert JsonProfileStore().get(f"prof_intel_b_daily_{TAG}").is_complete
    assert "relinked" in res["report"]["corrections"][0]["why"]
