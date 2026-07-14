"""Tests for the full newsroom rail — discovery -> routing -> profile -> gauntlet -> editorial.

Every stage is a proven sub-graph elsewhere; here they are faked (a graph that emits an optional
cost event and returns a fixed output), so these pin the ORCHESTRATION: the chaining, the cost tee,
the backfeed intake, and the each-stage-can-be-the-end short-circuits — offline, no LLM, no network.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.newsroom import rail as rl
from algent_backend.agent_system.agents.research.profile import DerivedLead
from algent_backend.agent_system.runs.context import AgentRunContext


class _EmittingGraph:
    def __init__(self, out, ctx, usd):
        self._out, self._ctx, self._usd = out, ctx, usd

    def invoke(self, _state, _config=None):
        if self._usd:                       # surface spend the way real stages do (a *_completed event)
            self._ctx.emit("stage.completed", {"estimated_usd": self._usd})
        return self._out


def _stage(out, usd=0.0):
    return lambda ctx: _EmittingGraph(out, ctx, usd)


class _Store:
    """A fake backfeed queue: hands out open leads, records what discovery consumes."""

    def __init__(self, leads):
        self._leads = leads
        self.consumed = []

    def list_open(self):
        return list(self._leads)

    def mark_consumed(self, lead_id):
        self.consumed.append(lead_id)


def _ctx(events):
    return AgentRunContext(
        run_id="t", model_resolver=object(),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _wire(monkeypatch, *, portfolio, route, profile, gauntlet, pipeline, costs=None):
    c = costs or {}
    monkeypatch.setattr(rl, "build_synthesis", _stage({"portfolio": portfolio}, c.get("syn", 0.0)))
    monkeypatch.setattr(rl, "build_router", _stage(route, c.get("route", 0.0)))
    monkeypatch.setattr(rl, "build_profile", _stage({"profile": profile}, c.get("prof", 0.0)))
    monkeypatch.setattr(rl, "build_profile_gauntlet", _stage(gauntlet, c.get("gaunt", 0.0)))
    monkeypatch.setattr(rl, "build_editorial", _stage({"pipeline": pipeline}, c.get("ed", 0.0)))


def _lead(i, conf="high"):
    return DerivedLead(id=f"lead_{i}", title=f"Lead {i}", confidence=conf,
                       source_url=f"https://x/{i}", entities=[f"e{i}"], topics=[f"t{i}"])


def _full(monkeypatch, **over):
    _wire(
        monkeypatch,
        portfolio={"vectors": [{"id": "vec_1", "title": "Fed path"}], "total_considered": 60},
        route={"selected_vector": {"id": "vec_1", "title": "Fed path"}},
        profile={"id": "prof_1"},
        gauntlet={"profile": {"id": "prof_1"}, "gauntlet": {"final_verdict": "mature"}},
        pipeline={"status": "publishable", "article_title": "Fed holds", "analytics_produced": 1},
        costs=over.get("costs"),
    )


def test_rail_runs_end_to_end_and_reports(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")   # isolate the chain from the backfeed queue here
    _full(monkeypatch)
    events: list = []
    out = rl.build_newsroom_rail_graph(_ctx(events)).invoke({"pool": {"items": [], "item_count": 60}})

    r = out["rail"]
    assert r["stage_reached"] == "complete"
    assert r["vector_count"] == 1 and r["selected_vector_id"] == "vec_1"
    assert r["profile_id"] == "prof_1" and r["gauntlet_verdict"] == "mature"
    assert r["article_status"] == "publishable" and r["analytics_produced"] == 1
    assert out["pipeline"]["article_title"] == "Fed holds"
    assert any(et == rl.RAIL_COMPLETED for et, _ in events)


def test_rail_sums_per_stage_cost(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _full(monkeypatch, costs={"syn": 0.02, "prof": 0.5, "ed": 0.25})   # router/gauntlet report none
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 1}})["rail"]
    assert abs(r["total_usd"] - 0.77) < 1e-9   # every surfaced estimated_usd, summed


def test_backfeed_leads_are_injected_and_consumed(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "1")
    _full(monkeypatch)
    store = _Store([_lead(1), _lead(2)])
    events: list = []
    # capture the pool synthesis actually receives, to prove the leads were merged in
    seen = {}
    monkeypatch.setattr(rl, "build_synthesis",
                        lambda ctx: type("G", (), {"invoke": lambda self, s, c=None: seen.update(s) or
                                                   {"portfolio": {"vectors": [{"id": "v", "title": "T"}],
                                                                  "total_considered": 3}}})())
    out = rl.build_newsroom_rail_graph(_ctx(events), lead_store=store).invoke(
        {"pool": {"items": [{"id": "gkg:x"}], "item_count": 1}})

    r = out["rail"]
    assert r["backfeed_leads_injected"] == 2
    assert store.consumed == ["lead_1", "lead_2"]              # marked so they don't loop forever
    ids = {i["id"] for i in seen["pool"]["items"]}
    assert ids == {"gkg:x", "backfeed:lead_1", "backfeed:lead_2"}   # merged alongside fresh t0
    assert seen["pool"]["item_count"] == 3
    assert any(et == rl.BACKFEED_INJECTED for et, _ in events)


def test_backfeed_disabled_injects_nothing(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _full(monkeypatch)
    store = _Store([_lead(1)])
    r = rl.build_newsroom_rail_graph(_ctx([]), lead_store=store).invoke(
        {"pool": {"items": [], "item_count": 0}})["rail"]
    assert r["backfeed_leads_injected"] == 0 and store.consumed == []


def test_no_vectors_short_circuits_at_synthesis(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _wire(monkeypatch, portfolio={"vectors": [], "total_considered": 40},
          route={}, profile={}, gauntlet={}, pipeline={})
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 40}})["rail"]
    assert r["stage_reached"] == "synthesis" and "no vectors" in r["note"]


def test_no_promoted_vector_short_circuits_at_routing(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _wire(monkeypatch, portfolio={"vectors": [{"id": "v", "title": "T"}], "total_considered": 5},
          route={"selected_vector": None}, profile={}, gauntlet={}, pipeline={})
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 5}})["rail"]
    assert r["stage_reached"] == "routing" and "no vector" in r["note"]


def test_lead_to_item_shape() -> None:
    it = rl._lead_to_item(_lead(9, conf="med"))
    assert it["id"] == "backfeed:lead_9" and it["channel"] == "backfeed" and it["kind"] == "lead"
    assert it["signals"]["backfeed"] is True and it["signals"]["score"] == 3.0
    assert it["evidence"][0]["url"] == "https://x/9" and "e9" in it["related"]


def test_newsroom_rail_registered() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry
    spec = default_agent_registry().get("newsroom_rail")
    assert spec.default_model is None and spec.family == "newsroom"
