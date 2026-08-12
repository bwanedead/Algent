"""Tests for the full newsroom rail — discovery -> routing -> profile -> gauntlet -> editorial.

Every stage is a proven sub-graph elsewhere; here they are faked (a graph that emits an optional
cost event and returns a fixed output), so these pin the ORCHESTRATION: the chaining, the cost tee,
the backfeed intake, and the each-stage-can-be-the-end short-circuits — offline, no LLM, no network.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.newsroom import rail as rl
from algent_backend.agent_system.agents.research.profile import DerivedLead
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.runs.context import AgentRunContext


class _EmittingGraph:
    def __init__(self, out, ctx, usd):
        self._out, self._ctx, self._usd = out, ctx, usd

    def invoke(self, _state, _config=None):
        if self._usd:  # charge the article meter the way live stages do (cost.add / spent_usd)
            cost.add(float(self._usd))
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


def test_rail_publishes_itself_when_the_piece_is_publishable(monkeypatch) -> None:
    # The point: a piece that earns `publishable` ships BY VIRTUE OF THE PIPELINE. Nobody runs a
    # command. (Publishing was previously a manual CLI step — that friction is what this removes.)
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _full(monkeypatch)
    seen = {}
    monkeypatch.setattr(rl, "find_run_root", lambda _rid: __import__("pathlib").Path("/runs/x"))
    monkeypatch.setattr(rl.site_git, "publish_enabled", lambda: False)   # switch off -> stage, no git
    monkeypatch.setattr(rl.site_git, "repo_root", lambda _p: __import__("pathlib").Path("/repo"))
    monkeypatch.setattr(rl.site_git, "site_dir", lambda _r: __import__("pathlib").Path("/repo/site"))
    monkeypatch.setattr(rl.pb, "publish_run", lambda run_dir, **kw: seen.update(kw) or
                        type("R", (), {"action": "staged", "slug": "fed-holds-abc123",
                                       "status": "publishable", "digest": "d", "reasons": []})())
    events: list = []
    r = rl.build_newsroom_rail_graph(_ctx(events)).invoke({"pool": {"items": [], "item_count": 1}})["rail"]

    assert r["publish_action"] == "staged" and r["published_slug"] == "fed-holds-abc123"
    assert seen["push"] is False                      # kill switch off -> staged, never pushed
    assert any(et == rl.RAIL_PUBLISHED for et, _ in events)


def test_a_publish_failure_never_fails_the_article(monkeypatch) -> None:
    # Distribution is downstream of the newsroom: if the push breaks, the piece was still produced
    # honestly and the run must say so rather than retroactively "fail".
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _full(monkeypatch)
    monkeypatch.setattr(rl, "find_run_root", lambda _rid: __import__("pathlib").Path("/runs/x"))
    monkeypatch.setattr(rl.site_git, "publish_enabled", lambda: False)
    monkeypatch.setattr(rl.site_git, "repo_root", lambda _p: (_ for _ in ()).throw(OSError("git gone")))

    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 1}})["rail"]
    assert r["stage_reached"] == "complete" and r["article_status"] == "publishable"   # article intact
    assert r["publish_action"].startswith("error") and r["published"] is False


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


def test_immature_profile_still_enters_editorial(monkeypatch) -> None:
    """Soft diagnose: disposition recorded, editorial still runs (site = review surface)."""
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    editorial_calls: list = []
    _wire(
        monkeypatch,
        portfolio={"vectors": [{"id": "vec_1", "title": "Amazon earthworks"}], "total_considered": 10},
        route={"selected_vector": {"id": "vec_1", "title": "Amazon earthworks"}},
        profile={"id": "prof_1", "profile_status": "needs_verification"},
        gauntlet={
            "profile": {"id": "prof_1", "profile_status": "needs_verification"},
            "gauntlet": {"final_verdict": "needs_verification", "remaining_blockers": 3},
        },
        pipeline={"status": "thin_spine", "article_title": "Honest thin piece", "analytics_produced": 0},
    )
    monkeypatch.setattr(
        rl, "build_editorial",
        lambda ctx: editorial_calls.append(1) or _EmittingGraph(
            {"pipeline": {"status": "thin_spine", "article_title": "Honest thin piece",
                          "analytics_produced": 0}},
            ctx, 0.0,
        ),
    )
    monkeypatch.setattr(rl, "find_run_root", lambda _rid: None)
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 1}})["rail"]
    assert editorial_calls == [1]
    assert r["stage_reached"] == "complete"
    assert r["disposition"] == "needs_verification"
    assert "soft-warn" in r["note"]
    assert r["article_status"] == "thin_spine"


def test_needs_enrichment_still_enters_editorial(monkeypatch) -> None:
    """Soft enrichment leftovers (Centaur path) may still draft; spine gate handles thin stubs."""
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _wire(
        monkeypatch,
        portfolio={"vectors": [{"id": "vec_1", "title": "Centaur"}], "total_considered": 10},
        route={"selected_vector": {"id": "vec_1", "title": "Centaur"}},
        profile={"id": "prof_1"},
        gauntlet={
            "profile": {"id": "prof_1"},
            "gauntlet": {"final_verdict": "needs_enrichment", "remaining_blockers": 6},
        },
        pipeline={"status": "publishable", "article_title": "Centaur piece", "analytics_produced": 0},
    )
    monkeypatch.setattr(rl, "find_run_root", lambda _rid: None)  # skip publish path
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 1}})["rail"]
    assert r["stage_reached"] == "complete"
    assert r["gauntlet_verdict"] == "needs_enrichment"
    assert r["disposition"] == ""


def test_rail_sums_per_stage_cost(monkeypatch) -> None:
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _full(monkeypatch, costs={"syn": 0.02, "prof": 0.5, "ed": 0.25})   # router/gauntlet report none
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 1}})["rail"]
    assert abs(r["total_usd"] - 0.77) < 1e-9   # every surfaced estimated_usd, summed
    assert r["cost_by_stage"]["synthesis"] == 0.02
    assert r["cost_by_stage"]["profile"] == 0.5
    assert r["cost_by_stage"]["editorial"] == 0.25


def test_rail_writes_report_before_publish(monkeypatch) -> None:
    """Publisher reads newsroom_rail_report.json — it must already carry disposition/cost."""
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _full(monkeypatch, costs={"syn": 0.01, "ed": 0.02})
    written: list[dict] = []

    class _Arts:
        def write_json(self, name, data):
            if name == "newsroom_rail_report.json":
                written.append(dict(data))

        def write_text(self, *a, **k):
            return None

    seen_digest_fields: dict = {}

    def fake_publish(run_dir, **kw):
        # Simulate publish reading the on-disk report (what converter/digest use).
        snap = written[-1] if written else {}
        seen_digest_fields.update({
            "total_usd": snap.get("total_usd"),
            "cost_by_stage": snap.get("cost_by_stage"),
            "disposition": snap.get("disposition", ""),
        })
        return type("R", (), {
            "action": "staged", "slug": "x", "status": "publishable",
            "digest": "d", "reasons": [],
        })()

    monkeypatch.setattr(rl, "find_run_root", lambda _rid: __import__("pathlib").Path("/runs/x"))
    monkeypatch.setattr(rl.site_git, "publish_enabled", lambda: False)
    monkeypatch.setattr(rl.site_git, "repo_root", lambda _p: __import__("pathlib").Path("/repo"))
    monkeypatch.setattr(rl.site_git, "site_dir", lambda _r: __import__("pathlib").Path("/repo/site"))
    monkeypatch.setattr(rl.pb, "publish_run", fake_publish)

    ctx = _ctx([])
    ctx = __import__("dataclasses").replace(ctx, artifacts=_Arts())
    rl.build_newsroom_rail_graph(ctx).invoke({"pool": {"items": [], "item_count": 1}})

    assert written, "report must be written before publish"
    assert seen_digest_fields["total_usd"] == 0.03
    assert seen_digest_fields["cost_by_stage"]["synthesis"] == 0.01
    assert "editorial" in seen_digest_fields["cost_by_stage"]


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


def test_rail_counts_x_searches(monkeypatch) -> None:
    # Measure X adoption rather than inferring it from artifacts — two doctrine passes tried to
    # raise usage while we could only guess whether it moved.
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")

    class _XGraph:
        def __init__(self, out, ctx):
            self._out, self._ctx = out, ctx

        def invoke(self, _s, _c=None):
            from algent_backend.agent_system.runs import events as ev
            self._ctx.emit(ev.TOOL_RESULT, {"content": '{"action": "search", "kind": "x", "results": []}'})
            self._ctx.emit(ev.TOOL_RESULT, {"content": '{"action": "search", "kind": "keyword"}'})
            return self._out

    _full(monkeypatch)
    monkeypatch.setattr(rl, "build_profile", lambda ctx: _XGraph({"profile": {"id": "prof_1"}}, ctx))
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": {"items": [], "item_count": 1}})["rail"]
    assert r["x_searches"] == 1   # the X call counted, the keyword one didn't


def test_rail_reports_channel_provenance(monkeypatch) -> None:
    """Pool share alone says nothing — the ratio of 'share of pool' to 'share of what got promoted'
    is the overfit signal. A live run had X supply a quarter of the pool and ALL of the promoted
    story, while a constitutional crisis from gkg lost; that steer is invisible without both."""
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    _wire(
        monkeypatch,
        portfolio={"vectors": [{"id": "v1", "title": "T"}], "total_considered": 4},
        route={"selected_vector": {"id": "v1", "title": "T", "supporting_hits": ["x:1", "x:2"]}},
        profile={"id": "p"},
        gauntlet={"profile": {"id": "p"}, "gauntlet": {"final_verdict": "mature"}},
        pipeline={"status": "publishable", "article_title": "T"},
    )
    pool = {"items": [{"id": "x:1", "channel": "x"}, {"id": "x:2", "channel": "x"},
                      {"id": "g:1", "channel": "gkg"}, {"id": "g:2", "channel": "gkg"}],
            "item_count": 4}
    r = rl.build_newsroom_rail_graph(_ctx([])).invoke({"pool": pool})["rail"]

    assert r["pool_by_channel"] == {"x": 2, "gkg": 2}    # X is half the pool...
    assert r["promoted_from"] == {"x": 2}                # ...and all of what we ran: the steer


def test_rail_reuses_portfolio_skips_synthesis_and_still_routes(monkeypatch) -> None:
    """Post-t0 launch: supply a prior portfolio, skip discovery spend; routing still runs (cooldown elsewhere)."""
    monkeypatch.setenv(rl._BACKFEED_ENV, "1")  # even with backfeed on, reuse must not touch it
    synthesis_calls: list = []

    def _syn(_ctx):
        synthesis_calls.append(1)
        return _EmittingGraph({"portfolio": {"vectors": []}}, _ctx, 0.0)

    _wire(
        monkeypatch,
        portfolio={"vectors": [], "total_considered": 0},  # unused — we supply portfolio in state
        route={"selected_vector": {"id": "v02", "title": "Second ranked hit"}},
        profile={"id": "prof_2"},
        gauntlet={"profile": {"id": "prof_2"}, "gauntlet": {"final_verdict": "mature"}},
        pipeline={"status": "publishable", "article_title": "Second story", "analytics_produced": 0},
    )
    monkeypatch.setattr(rl, "build_synthesis", _syn)
    events: list = []
    prior = {
        "vectors": [
            {"id": "v01", "title": "Already published beat"},
            {"id": "v02", "title": "Second ranked hit"},
        ],
        "total_considered": 80,
    }
    out = rl.build_newsroom_rail_graph(_ctx(events)).invoke({
        "portfolio": prior, "source_run_id": "prev-run-uuid",
    })
    r = out["rail"]
    assert synthesis_calls == []                         # t0+synthesis never ran
    assert r["portfolio_source"] == "reused"
    assert r["source_run_id"] == "prev-run-uuid"
    assert r["vector_count"] == 2
    assert r["selected_vector_id"] == "v02"
    assert r["stage_reached"] == "complete"
    assert r["backfeed_leads_injected"] == 0
    assert any(
        et == rl.RAIL_STAGE and (p or {}).get("skipped") is True
        for et, p in events
    )


def test_rail_reuses_profile_skips_routing_and_profile(monkeypatch) -> None:
    """Resume from a researched profile: do not re-route or re-research."""
    monkeypatch.setenv(rl._BACKFEED_ENV, "0")
    route_calls: list = []
    profile_calls: list = []
    gauntlet_calls: list = []

    def _route(_ctx):
        route_calls.append(1)
        return _EmittingGraph({"selected_vector": {"id": "v99"}}, _ctx, 0.0)

    def _prof(_ctx):
        profile_calls.append(1)
        return _EmittingGraph({"profile": {"id": "prof_new"}}, _ctx, 0.0)

    def _gaunt(_ctx):
        gauntlet_calls.append(1)
        return _EmittingGraph(
            {"profile": {"id": "prof_kept"}, "gauntlet": {"final_verdict": "mature"}},
            _ctx, 0.0,
        )

    _wire(
        monkeypatch,
        portfolio={"vectors": [{"id": "v01", "title": "Kept"}], "total_considered": 10},
        route={"selected_vector": {"id": "v99"}},
        profile={"id": "prof_new"},
        gauntlet={"profile": {"id": "prof_kept"}, "gauntlet": {"final_verdict": "mature"}},
        pipeline={"status": "publishable", "article_title": "Kept story", "analytics_produced": 0},
    )
    monkeypatch.setattr(rl, "build_router", _route)
    monkeypatch.setattr(rl, "build_profile", _prof)
    monkeypatch.setattr(rl, "build_profile_gauntlet", _gaunt)
    events: list = []
    out = rl.build_newsroom_rail_graph(_ctx(events)).invoke({
        "portfolio": {"vectors": [{"id": "v01", "title": "Kept"}], "total_considered": 10},
        "selected_vector": {"id": "v01", "title": "Kept"},
        "profile": {"id": "prof_kept"},
        "gauntlet": {"final_verdict": "mature"},
        "source_run_id": "same-run",
    })
    r = out["rail"]
    assert route_calls == [] and profile_calls == [] and gauntlet_calls == []
    assert r["profile_id"] == "prof_kept"
    assert r["selected_vector_id"] == "v01"
    assert r["stage_reached"] == "complete"
    skipped = [p.get("stage") for et, p in events
               if et == rl.RAIL_STAGE and (p or {}).get("skipped")]
    assert "routing" in skipped and "profile" in skipped and "gauntlet" in skipped


def test_stage_clock_times_stages_and_slow_legs() -> None:
    """Wall time per stage, the counterpart to cost_by_stage.

    A run went ten minutes with no model calls and looked dead from outside; it was a figure
    timing out in a subprocess. Cost was attributed by stage from the start, time was not, so
    that could only be diagnosed by reading raw event timestamps afterwards.
    """
    from algent_backend.agent_system.agents.newsroom.rail import StageClock, _hms

    clock = StageClock()
    clock.enter("profile")
    clock.enter("editorial")
    clock.mark("analytics_worker.artifact", {"request_id": "req_map", "note": "timed out"})
    summary = clock.summary()

    # Every stage closes, including the last one — which only ends when the run does.
    assert set(summary["by_stage"]) == {"profile", "editorial"}
    assert all(v is not None for v in summary["by_stage"].values())
    assert summary["total_seconds"] >= 0

    # Legs carry what identifies the slow thing, ranked slowest first, private fields dropped.
    leg = summary["slow_legs"][0]
    assert leg["event"] == "analytics_worker.artifact" and leg["detail"] == "req_map"
    assert not any(k.startswith("_") for k in leg)

    # Durations read as durations, not float seconds.
    assert _hms(5) == "5s" and _hms(65) == "1m05s" and _hms(600) == "10m00s"
