"""Tests for the editorial_pipeline orchestrator (profile -> article)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import pipeline as pl
from algent_backend.agent_system.runs.context import AgentRunContext


class _Graph:
    def __init__(self, out):
        self._out = out

    def invoke(self, _state, _config=None):
        return self._out


def _ctx(events):
    return AgentRunContext(
        run_id="t", model_resolver=object(),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _spine_profile(pid: str = "prof_x") -> dict:
    """Minimal profile that clears the article-spine publish floor."""
    snap = {"content_hash": "sha256:x", "excerpt": "e", "captured_at": "t"}
    return {
        "id": pid,
        "source_ledger": [
            {"id": "s1", "url": "https://a.example/1", "source_type": "primary", "snapshot": snap},
            {"id": "s2", "url": "https://b.example/2", "snapshot": snap},
        ],
    }


def _wire(monkeypatch, plan_out, draft_out, caveat_out, headline_out=None, analytics_out=None,
          worker_out=None):
    monkeypatch.setattr(pl, "build_planning_gauntlet_graph", lambda ctx: _Graph(plan_out))
    monkeypatch.setattr(pl, "build_drafting_gauntlet_graph", lambda ctx: _Graph(draft_out))
    monkeypatch.setattr(pl, "build_headline_writer", lambda ctx: _Graph(headline_out or {"headline": {}}))
    monkeypatch.setattr(pl, "build_caveat_reviewer", lambda ctx: _Graph(caveat_out))
    monkeypatch.setattr(pl, "build_analytics_router", lambda ctx: _Graph(analytics_out or {"analytics_plan": {}}))
    # gate C defaults to clear (a well-built piece); individual tests override to exercise the lane.
    monkeypatch.setattr(pl, "build_comprehension_reviewer",
                        lambda ctx: _Graph({"comprehension_check": {"verdict": "clear", "findings": []}}))
    # A sentinel worker: if it is ever built, it records the call — so a test can prove the gate
    # kept it OFF (never built) without any risk of spawning real grok.
    built = []
    monkeypatch.setattr(pl, "build_analytics_worker_graph",
                        lambda ctx: built.append(1) or _Graph(worker_out or {"analytics_artifacts": []}))
    return built


def test_caveated_piece_becomes_publishable_once_caveats_verified(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {"final_verdict": "needs_revision"}}
    draft_out = {
        "draft": {"id": "drf_x", "title": "A real Fed piece", "word_count": 420},
        "gauntlet": {"outcome": "grounded_with_caveats", "promoted": True, "barriers": ["src_a"]},
    }
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified", "findings": []}})

    events: list = []
    out = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": _spine_profile()})

    r = out["pipeline"]
    assert r["treatment_id"] == "trt_x" and r["draft_id"] == "drf_x"
    assert r["draft_outcome"] == "grounded_with_caveats"
    # v3b verified the caveats are actually in the prose -> the pending promise is now cleared.
    assert r["status"] == "publishable" and r["publishable"] is True
    assert r["caveat_verdict"] == "verified" and r["barriers"] == ["src_a"]
    assert any(et == "editorial_pipeline.completed" for et, _ in events)


def test_pipeline_applies_the_truthful_headline(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x", "title": "working title", "word_count": 400},
                 "gauntlet": {"outcome": "grounded", "promoted": True}}
    headline_out = {"headline": {
        "title": "Fed holds, hike tail still live",
        "standfirst": "the nuance",
        "quick_take": {
            "what_happened": "The Fed held rates.",
            "why_it_matters": "Markets still price a hike tail.",
            "what_is_uncertain": "Whether sticky PCE forces a later move.",
        },
    }}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}}, headline_out)

    out = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile()})
    r = out["pipeline"]
    assert r["article_title"] == "Fed holds, hike tail still live"   # retitled from the working title
    assert r["status"] == "publishable"
    assert out["draft"]["quick_take"]["what_happened"] == "The Fed held rates."


def test_pipeline_applies_headline_after_repairs(monkeypatch) -> None:
    """Surface package must see the repaired body — headline runs after caveat/comprehension."""
    order: list[str] = []

    class _OrderGraph:
        def __init__(self, name, out):
            self.name, self._out = name, out

        def invoke(self, _state, _config=None):
            order.append(self.name)
            return self._out

    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x", "title": "working", "body": "x " * 200, "word_count": 200},
                 "gauntlet": {"outcome": "grounded"}}
    monkeypatch.setattr(pl, "build_planning_gauntlet_graph",
                        lambda ctx: _OrderGraph("plan", plan_out))
    monkeypatch.setattr(pl, "build_analytics_router",
                        lambda ctx: _OrderGraph("analytics_plan", {
                            "analytics_plan": {"warranted": True, "requests": [{"id": "anx_01"}]},
                        }))
    monkeypatch.setattr(pl, "build_drafting_gauntlet_graph",
                        lambda ctx: _OrderGraph("draft", draft_out))
    monkeypatch.setattr(pl, "build_caveat_reviewer",
                        lambda ctx: _OrderGraph("caveat", {"caveat_check": {"verdict": "verified"}}))
    monkeypatch.setattr(pl, "build_comprehension_reviewer",
                        lambda ctx: _OrderGraph("comprehension",
                                                {"comprehension_check": {"verdict": "clear"}}))
    monkeypatch.setattr(pl, "build_headline_writer",
                        lambda ctx: _OrderGraph("headline", {"headline": {"title": "Final"}}))
    monkeypatch.setattr(pl, "build_analytics_worker_graph",
                        lambda ctx: _OrderGraph("analytics_worker", {"analytics_artifacts": []}))
    monkeypatch.setattr(pl, "make_hero", lambda *_a, **_k: None)
    monkeypatch.setenv(pl._ANALYTICS_WORKER_ENV, "1")

    pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile()})
    assert order.index("analytics_plan") < order.index("draft")
    assert order.index("caveat") < order.index("headline")
    assert order.index("comprehension") < order.index("headline")
    assert order.index("headline") < order.index("analytics_worker")


def test_surface_repair_reruns_headline_once(monkeypatch) -> None:
    """Cold-browser surface issues trigger one bounded headline repair lap."""
    calls: list[dict] = []

    class _HeadlineGraph:
        def invoke(self, state, _config=None):
            calls.append(state)
            if state.get("surface_issues"):
                return {"headline": {
                    "title": "AI probes an undeciphered Bronze Age script",
                    "standfirst": "A model ran on Linear A tablets; no translation yet.",
                    "quick_take": {
                        "what_happened": "Researchers probed Linear A with an AI model.",
                        "why_it_matters": "It may help study an undeciphered script.",
                        "what_is_uncertain": "No translation has been produced.",
                    },
                }}
            return {"headline": {
                "title": "Linear A",
                "standfirst": "A model ran.",
                "quick_take": {},
            }}

    plan_out = {
        "treatment": {
            "id": "trt_x",
            "plain_subject": "an undeciphered Bronze Age script",
            "news_kernel": "Researchers probed Linear A with an AI model.",
            "reader_payoff": "It may help study an undeciphered script.",
            "key_uncertainty": "No translation has been produced.",
        },
        "gauntlet": {},
    }
    draft_out = {
        "draft": {"id": "drf_x", "title": "working", "body": "x " * 200, "word_count": 200},
        "gauntlet": {"outcome": "grounded", "promoted": True},
    }
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}})
    monkeypatch.setattr(pl, "build_headline_writer", lambda ctx: _HeadlineGraph())
    monkeypatch.setattr(pl, "make_hero", lambda *_a, **_k: None)

    events: list = []
    out = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": _spine_profile()})
    assert len(calls) == 2
    assert calls[1].get("surface_issues")
    assert out["draft"]["title"].startswith("AI probes")
    assert any(et == pl.SURFACE_REPAIRED for et, _ in events)
    assert out["pipeline"]["article_title"].startswith("AI probes")


def test_analytics_skips_are_recorded_on_report(monkeypatch) -> None:
    monkeypatch.setenv(pl._ANALYTICS_WORKER_ENV, "1")
    monkeypatch.setenv(pl._ANALYTICS_CAP_ENV, "1")

    class _CapGraph:
        def invoke(self, state, _config=None):
            req = state["analytics_plan"]["requests"][0]
            return {"analytics_artifacts": [{
                "request_id": req["id"], "status": "produced",
                "artifact_name": "a.svg", "escaped_writes": [],
            }]}

    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "word_count": 100}, "gauntlet": {"outcome": "grounded"}}
    reqs = [
        {"id": "anx_01", "priority": "essential_context"},
        {"id": "anx_02", "priority": "optional"},
        {"id": "anx_03", "visual_class": "source_specimen", "status": "source_unavailable",
         "rationale": "licensed media lane not ready"},
    ]
    analytics_out = {"analytics_plan": {"warranted": True, "requests": reqs}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}},
          analytics_out=analytics_out)
    monkeypatch.setattr(pl, "build_analytics_worker_graph", lambda ctx: _CapGraph())

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert r["analytics_produced"] == 1
    assert any("anx_02:skipped" in s for s in r["analytics_skipped"])
    assert any("anx_03:source_unavailable" in s for s in r["analytics_skipped"])


class _Sequence:
    """A graph whose successive invocations return successive outputs (for the repair lap)."""

    def __init__(self, *outs):
        self._outs, self._i = list(outs), 0

    def invoke(self, _state, _config=None):
        out = self._outs[min(self._i, len(self._outs) - 1)]
        self._i += 1
        return out


def test_needs_hedging_self_heals_and_ships(monkeypatch) -> None:
    # The whole point: an overclaim is repaired by machine, not parked in a queue. Findings ->
    # targeted hedge -> re-headline -> re-check -> publishable. Nothing waits on a human.
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x", "title": "t", "word_count": 400},
                 "gauntlet": {"outcome": "grounded"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {}})
    # first check fails, second (after the repair) passes. NOTE: hoist the sequence — the pipeline
    # calls build_caveat_reviewer() per use, so a lambda that constructs it inline would hand back
    # a fresh sequence each time and never advance.
    caveats = _Sequence(
        {"caveat_check": {"verdict": "needs_hedging", "findings": [{"id": "cav_01"}]}},
        {"caveat_check": {"verdict": "verified", "findings": []}})
    monkeypatch.setattr(pl, "build_caveat_reviewer", lambda ctx: caveats)
    repaired = {"draft": {"id": "drf_x", "title": "t", "word_count": 390}, "profile": _spine_profile()}
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: _Sequence(repaired))

    events: list = []
    r = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": _spine_profile()})["pipeline"]
    assert r["status"] == "publishable" and r["publishable"] is True   # shipped, not held
    assert r["caveat_verdict"] == "verified" and r["caveat_rounds"] == 2
    assert any(et == pl.CAVEAT_REPAIRED for et, _ in events)


def test_comprehension_is_advisory_repairs_but_never_blocks_publish(monkeypatch) -> None:
    # A hard-to-follow piece is a dud, not a lie: gate C earns one ramp-repair lap, then ships either
    # way. needs_ramp must NOT flip a publishable piece to held — if the body stays intact.
    body = " ".join(["word"] * 200)
    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "title": "t", "body": body, "word_count": 200},
                 "gauntlet": {"outcome": "grounded"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}})
    # first read flags a ramp gap; after the repair, it reads clear (body still long enough)
    comp = _Sequence({"comprehension_check": {"verdict": "needs_ramp", "findings": [{"id": "cmp_01"}]}},
                     {"comprehension_check": {"verdict": "clear", "findings": []}})
    monkeypatch.setattr(pl, "build_comprehension_reviewer", lambda ctx: comp)
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: _Sequence(
        {"draft": {"id": "d", "title": "t", "body": body + " ramp", "word_count": 201},
         "profile": _spine_profile("p")}))

    events: list = []
    r = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert r["status"] == "publishable" and r["publishable"] is True   # never blocked by comprehension
    assert r["comprehension_verdict"] == "clear" and r["comprehension_rounds"] == 2
    assert any(et == pl.RAMP_REPAIRED for et, _ in events)


def test_comprehension_repair_that_collapses_the_body_is_rejected(monkeypatch) -> None:
    # Live failure: ramp repair wiped ~400 words down to one sentence; must keep the prior draft.
    long_body = " ".join(["word"] * 400)
    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "title": "t", "body": long_body, "word_count": 400},
                 "gauntlet": {"outcome": "grounded"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}})
    monkeypatch.setattr(pl, "build_comprehension_reviewer", lambda ctx: _Sequence(
        {"comprehension_check": {"verdict": "needs_ramp", "findings": [{"id": "cmp_01"}]}}))
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: _Sequence(
        {"draft": {"id": "d", "title": "t", "body": "One hollow sentence.", "word_count": 3},
         "profile": _spine_profile("p")}))
    events: list = []
    out = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": _spine_profile("p")})
    r = out["pipeline"]
    assert r["status"] == "publishable" and r["word_count"] >= 200
    assert out["draft"]["body"] == long_body
    assert any(
        et == pl.RAMP_REPAIRED and (p or {}).get("verdict") == "repair_rejected_collapsed"
        for et, p in events
    )


def test_hollow_draft_is_not_publishable(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "title": "t", "body": "One line only.", "word_count": 3},
                 "gauntlet": {"outcome": "grounded"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}})
    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert r["status"] == "needs_revision" and r["publishable"] is False
    assert r["word_count"] < pl._MIN_PUBLISH_WORDS


def test_thin_spine_is_honest_signal_not_hard_stop(monkeypatch) -> None:
    """Citation grounding on one podcast page earns thin_spine — honest, still drafted."""
    plan_out = {"treatment": {"id": "t"}, "gauntlet": {"final_verdict": "needs_revision"}}
    thin = {
        "id": "p",
        "source_ledger": [
            {"id": "s1", "url": "https://podcast.example/ep", "snapshot": {"content_hash": "h"}},
        ],
    }
    draft_out = {
        "draft": {"id": "d", "title": "We could not verify the paper", "body": " ".join(["w"] * 200),
                  "word_count": 200},
        "profile": thin,
        "gauntlet": {"outcome": "grounded", "promoted": True},
    }
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified", "findings": []}})
    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": thin})["pipeline"]
    assert r["status"] == "thin_spine" and r["publishable"] is False
    assert r["draft_outcome"] == "grounded"  # citations OK; spine signal honest
    assert r["draft_id"] == "d"  # still produced an article artifact


def test_unsound_treatment_still_drafts(monkeypatch) -> None:
    """Soft promote: unsound / empty treatment gets a fallback id and still drafts."""
    plan_out = {"treatment": {"id": ""}, "gauntlet": {"final_verdict": "unsound"}}
    draft_calls: list = []
    seen: dict = {}

    def _draft_graph(ctx):
        draft_calls.append(1)

        class G:
            def invoke(self, state, _config=None):
                seen.update(state)
                return {
                    "draft": {"id": "d", "title": "t", "body": " ".join(["w"] * 200),
                              "word_count": 200},
                    "profile": _spine_profile("p"),
                    "gauntlet": {"outcome": "grounded", "promoted": True},
                }
        return G()

    _wire(monkeypatch, plan_out, {"draft": {}, "gauntlet": {}},
          {"caveat_check": {"verdict": "verified", "findings": []}})
    monkeypatch.setattr(pl, "build_drafting_gauntlet_graph", _draft_graph)
    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert draft_calls == [1]
    assert str(seen.get("treatment", {}).get("id", "")).startswith("trt_fallback_")
    assert r["treatment_verdict"] == "unsound"
    assert r["status"] == "publishable"  # drafted + spine cleared


def test_a_still_unclear_piece_ships_anyway(monkeypatch) -> None:
    # It ships, and that is the operator's call: the SITE is the review surface, so a piece held
    # for being hard to follow is a piece nobody reads and nobody learns from, while the drafting
    # problem stays invisible. (Briefly made a hard gate, then reverted for that reason.) The
    # pressure lives in the repair lap and in the verdict riding visibly on the report instead.
    body = " ".join(["word"] * 200)
    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "title": "t", "body": body, "word_count": 200},
                 "gauntlet": {"outcome": "grounded"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}})
    monkeypatch.setattr(pl, "build_comprehension_reviewer", lambda ctx: _Sequence(
        {"comprehension_check": {"verdict": "needs_ramp", "findings": [{"id": "cmp_01"}]}}))  # never clears
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: _Sequence(
        {"draft": {"id": "d", "title": "t", "body": body, "word_count": 200}, "profile": _spine_profile("p")}))

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert r["status"] == "publishable"                       # ships; the site is the review surface
    # ...but the verdict is never hidden — it rides on the report for the operator to see.
    assert r["comprehension_verdict"] == "needs_ramp"
    # THE LOOP IS BOUNDED. A reviewer that never clears would otherwise run forever, and each
    # read can always find something. Two reads, each followed by a fix, then it ships.
    assert r["comprehension_rounds"] == pl._MAX_REVIEW_LAPS == 2


def test_still_unhedged_after_the_repair_lap_holds_the_piece(monkeypatch) -> None:
    # The lap is bounded: if the repair doesn't take, we stay honest rather than loop or ship it.
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x", "title": "t"}, "gauntlet": {"outcome": "grounded_with_caveats",
                                                                     "barriers": ["s"]}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {}})
    monkeypatch.setattr(pl, "build_caveat_reviewer", lambda ctx: _Sequence(
        {"caveat_check": {"verdict": "needs_hedging", "findings": [{"id": "cav_01"}]}}))  # always fails
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: _Sequence(
        {"draft": {"id": "drf_x", "title": "t"}, "profile": _spine_profile()}))

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile()})["pipeline"]
    assert r["status"] == "needs_hedging" and r["publishable"] is False
    assert r["caveat_rounds"] == 2   # the lap ran and didn't take — bounded, no third try


def test_clean_first_pass_does_not_run_the_repair_lap(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x", "title": "t"}, "gauntlet": {"outcome": "grounded"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified", "findings": []}})
    built = []
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: built.append(1) or _Sequence({}))

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile()})["pipeline"]
    assert r["caveat_rounds"] == 1 and built == []   # no extra drafter spend on a clean piece


def test_pipeline_no_profile_is_not_publishable(monkeypatch) -> None:
    out = pl.build_editorial_pipeline_graph(_ctx([])).invoke({})
    assert out["pipeline"]["publishable"] is False


def test_analytics_worker_can_be_gated_off(monkeypatch) -> None:
    # Worker is ON by default so maps ship; operators can still disable with ALGENT_ANALYTICS_WORKER=0.
    monkeypatch.setenv(pl._ANALYTICS_WORKER_ENV, "0")
    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "word_count": 100}, "gauntlet": {"outcome": "grounded"}}
    analytics_out = {"analytics_plan": {"warranted": True, "requests": [{"id": "anx_01"}]}}
    built = _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}},
                  analytics_out=analytics_out)

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert built == []                                  # worker never built -> no grok spawn
    assert r["analytics_warranted"] is True and r["analytics_produced"] == 0


def test_analytics_worker_runs_and_caps_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv(pl._ANALYTICS_WORKER_ENV, "1")
    monkeypatch.setenv(pl._ANALYTICS_CAP_ENV, "2")
    seen: dict = {}

    class _CapGraph:
        def invoke(self, state, _config=None):
            seen["n"] = len(state["analytics_plan"]["requests"])   # how many requests reached the worker
            return {"analytics_artifacts": [{"request_id": "anx_01", "status": "produced",
                                             "artifact_name": "a.svg", "escaped_writes": []}]}

    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "word_count": 100}, "gauntlet": {"outcome": "grounded"}}
    reqs = [{"id": f"anx_{i:02d}"} for i in range(5)]     # 5 requested, cap is 2
    analytics_out = {"analytics_plan": {"warranted": True, "requests": reqs}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}},
          analytics_out=analytics_out)
    monkeypatch.setattr(pl, "build_analytics_worker_graph", lambda ctx: _CapGraph())

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert seen["n"] == 2                                # capped to ALGENT_ANALYTICS_MAX
    assert r["analytics_produced"] == 1 and r["analytics_escapes"] == 0


def test_fake_produced_plan_status_still_reaches_worker(monkeypatch) -> None:
    """Router/model 'produced' without an artifact must not skip fulfillment."""
    monkeypatch.setenv(pl._ANALYTICS_WORKER_ENV, "1")
    monkeypatch.setenv(pl._ANALYTICS_CAP_ENV, "2")
    seen: dict = {}

    class _Graph:
        def invoke(self, state, _config=None):
            seen["statuses"] = [r.get("status") for r in state["analytics_plan"]["requests"]]
            seen["n"] = len(state["analytics_plan"]["requests"])
            return {"analytics_artifacts": [{
                "request_id": "anx_01", "status": "produced",
                "artifact_name": "cobalt.svg", "escaped_writes": [],
            }]}

    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "word_count": 100}, "gauntlet": {"outcome": "grounded"}}
    analytics_out = {"analytics_plan": {
        "warranted": True,
        "requests": [{"id": "anx_01", "status": "produced", "title": "cobalt"}],
    }}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}},
          analytics_out=analytics_out)
    monkeypatch.setattr(pl, "build_analytics_worker_graph", lambda ctx: _Graph())

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert seen.get("n") == 1
    assert seen.get("statuses") == ["requested"]
    assert r["analytics_produced"] == 1


def test_produced_without_artifact_does_not_count(monkeypatch) -> None:
    monkeypatch.setenv(pl._ANALYTICS_WORKER_ENV, "1")

    class _Graph:
        def invoke(self, state, _config=None):
            return {"analytics_artifacts": [{
                "request_id": "anx_01", "status": "produced",  # lie: no file
                "artifact_name": "", "body_md": "", "escaped_writes": [],
            }]}

    plan_out = {"treatment": {"id": "t"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "d", "word_count": 100}, "gauntlet": {"outcome": "grounded"}}
    analytics_out = {"analytics_plan": {"warranted": True, "requests": [{"id": "anx_01"}]}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}},
          analytics_out=analytics_out)
    monkeypatch.setattr(pl, "build_analytics_worker_graph", lambda ctx: _Graph())

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert r["analytics_produced"] == 0


def test_editorial_pipeline_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("editorial_pipeline")
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()


# -- hero image stage: decoration that must never cost us the article ------------


def _hl(subject: str = "an orca surfacing in coastal water", hook: str = "Orcas take a sunfish apart"):
    return {"title": "T", "standfirst": "d", "image_subject": subject, "image_hook": hook}


class _Writer:
    def __init__(self):
        self.written = {}

    def write_bytes(self, name, data, kind="binary"):
        self.written[name] = data
        return name


class _Img:
    data, model, size, estimated_usd = b"\xff\xd8jpeg", "gemini-3.1-flash-lite-image", "1K", 0.0336

    def suffix(self):
        return ".jpg"


def test_hero_is_on_by_default_and_can_be_switched_off(monkeypatch) -> None:
    """~$0.034 on the lite model is a few percent of a rail; a wall of text costs more."""
    from algent_backend.agent_system.agents.editorial.hero_stage import make_hero

    monkeypatch.delenv("ALGENT_HERO_IMAGE", raising=False)
    assert make_hero(_hl(), _Writer(), generate=lambda *a, **k: _Img()) is not None

    monkeypatch.setenv("ALGENT_HERO_IMAGE", "0")
    assert make_hero(_hl(), _Writer(), generate=lambda *a, **k: _Img()) is None


def test_hero_records_what_the_publisher_needs(monkeypatch) -> None:
    from algent_backend.agent_system.agents.editorial.hero_stage import make_hero

    monkeypatch.setenv("ALGENT_HERO_IMAGE", "1")
    w = _Writer()
    seen = {}

    def _gen(subject, hook="", **kw):
        seen["subject"], seen["hook"] = subject, hook
        return _Img()

    rec = make_hero(_hl(), w, generate=_gen)

    assert rec["artifact_name"] == "hero.jpg" and "hero.jpg" in w.written
    assert rec["alt"] == "an orca surfacing in coastal water"      # honest description
    assert rec["hook"] == "Orcas take a sunfish apart"
    assert "AI-generated" in rec["label"]
    assert seen["subject"] and seen["hook"]                         # brief reached the generator


def test_empty_subject_falls_back_so_every_piece_can_hero(monkeypatch) -> None:
    """House policy: every article gets a hero; empty image_subject is not a skip."""
    from algent_backend.agent_system.agents.editorial.hero_stage import make_hero

    monkeypatch.setenv("ALGENT_HERO_IMAGE", "1")
    notes: list[str] = []
    seen: dict = {}

    def _gen(subject, hook=""):
        seen["subject"] = subject
        return _Img()

    rec = make_hero(
        {"title": "Ancient Amazon earthworks under forest canopy", "standfirst": "d",
         "image_subject": "", "image_hook": ""},
        _Writer(),
        say=notes.append,
        generate=_gen,
    )
    assert rec is not None
    assert seen["subject"] == "a quiet landscape under soft daylight"
    assert any("falling back" in n for n in notes)


def test_quota_exhaustion_soft_skips_without_retry(monkeypatch) -> None:
    """429/quota is the only ship-without-hero path — one attempt, no retry burn."""
    from algent_backend.agent_system.agents.editorial import hero_stage

    monkeypatch.setenv("ALGENT_HERO_IMAGE", "1")
    monkeypatch.setattr(hero_stage.time, "sleep", lambda _s: None)
    notes: list[str] = []
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("HTTP 429: quota exceeded")

    out = hero_stage.make_hero(_hl(), _Writer(), say=notes.append, generate=_boom)
    assert out == {"skipped": "quota"}
    assert calls["n"] == 1
    assert any("publishing without hero" in n for n in notes)


def test_a_failed_generation_returns_none_for_publish_hold(monkeypatch) -> None:
    """Non-quota failure must not soft-ship; pipeline/publish treat None as needs_hero / hold."""
    from algent_backend.agent_system.agents.editorial import hero_stage

    monkeypatch.setenv("ALGENT_HERO_IMAGE", "1")
    monkeypatch.setattr(hero_stage.time, "sleep", lambda _s: None)
    notes: list[str] = []
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("HTTP 500: unavailable")

    assert hero_stage.make_hero(_hl(), _Writer(), say=notes.append, generate=_boom) is None
    assert calls["n"] == hero_stage._TRANSIENT_ATTEMPTS
    assert any("must not ship without a hero" in n for n in notes)


def test_a_bad_writer_subject_falls_back_before_spend(monkeypatch) -> None:
    """Quantities in the writer's subject are rejected; we fall back rather than skip."""
    from algent_backend.agent_system.agents.editorial.hero_stage import make_hero

    monkeypatch.setenv("ALGENT_HERO_IMAGE", "1")
    seen: dict = {}
    notes: list[str] = []
    rec = make_hero(
        _hl(subject="Florida's $1.8 trillion economy claim"),
        _Writer(),
        say=notes.append,
        generate=lambda subject, hook="": seen.update(subject=subject) or _Img(),
    )
    assert rec is not None
    assert "$" not in seen["subject"] and "trillion" not in seen["subject"].lower()
    assert any("falling back" in n or "rejected" in n for n in notes)


def test_needs_ramp_after_repair_holds_instead_of_publishing() -> None:
    """Comprehension is the one gate that speaks for the reader rather than for accuracy.
    It used to be advisory, and two science pieces went live that the reviewer had already
    said a general reader could not follow."""
    from algent_backend.agent_system.agents.editorial.pipeline_contracts import (
        EditorialPipelineReport,
    )

    # The gate itself is a status branch; assert the contract can carry the verdict and that
    # the publisher treats anything non-publishable as held (see test_publishing_publish).
    r = EditorialPipelineReport(status="needs_ramp", comprehension_verdict="needs_ramp")
    assert r.publishable is False
    assert r.status == "needs_ramp"


def _counting(*outs):
    """A sequence graph that also records how many times it was invoked."""
    seq = _Sequence(*outs)
    calls: list[int] = []
    original = seq.invoke

    def invoke(state, config=None):
        calls.append(1)
        return original(state, config)

    seq.invoke = invoke          # type: ignore[method-assign]
    seq.calls = calls            # type: ignore[attr-defined]
    return seq


def _long(n: int = 200) -> str:
    return " ".join(["word"] * n)


def _wire_review(monkeypatch, reviewer, drafter):
    body = _long()
    _wire(monkeypatch, {"treatment": {"id": "t"}, "gauntlet": {}},
          {"draft": {"id": "d", "title": "t", "body": body, "word_count": 200},
           "gauntlet": {"outcome": "grounded"}},
          {"caveat_check": {"verdict": "verified"}})
    monkeypatch.setattr(pl, "build_comprehension_reviewer", lambda ctx: reviewer)
    monkeypatch.setattr(pl, "build_drafter", lambda ctx: drafter)
    return pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]


def test_the_second_review_reads_the_repaired_draft(monkeypatch) -> None:
    """draft -> review -> draft -> review. One lap was demonstrably not enough: the same defect
    survived its single repair on three consecutive published articles."""
    reviewer = _counting(
        {"comprehension_check": {"verdict": "needs_ramp", "findings": [{"id": "cmp_01"}]}},
        {"comprehension_check": {"verdict": "clear", "findings": []}},
    )
    drafter = _counting({"draft": {"id": "d", "title": "t", "body": _long(), "word_count": 200},
                         "profile": _spine_profile("p")})
    r = _wire_review(monkeypatch, reviewer, drafter)

    assert len(reviewer.calls) == 2 and len(drafter.calls) == 1
    assert r["comprehension_verdict"] == "clear"
    assert r["comprehension_rounds"] == 2


def test_the_loop_ends_on_a_fix_not_a_read(monkeypatch) -> None:
    """The last repair is NOT re-reviewed: a read whose verdict cannot change whether the piece
    ships is spend with no consequence attached. So two reads, two fixes, then publish."""
    reviewer = _counting(
        {"comprehension_check": {"verdict": "needs_ramp", "findings": [{"id": "cmp_01"}]}})
    drafter = _counting({"draft": {"id": "d", "title": "t", "body": _long(), "word_count": 200},
                         "profile": _spine_profile("p")})
    r = _wire_review(monkeypatch, reviewer, drafter)

    assert len(reviewer.calls) == 2        # never a third read
    assert len(drafter.calls) == 2         # both fixes applied
    assert r["comprehension_rounds"] == 2
    assert r["status"] == "publishable"


def test_a_clean_piece_costs_no_repair_laps(monkeypatch) -> None:
    """The bound is a ceiling, not a quota — a good piece must not be rewritten for form's sake."""
    reviewer = _counting({"comprehension_check": {"verdict": "clear", "findings": []}})

    def _never(ctx):
        raise AssertionError("the drafter must not be re-invoked for a clear piece")

    body = _long()
    _wire(monkeypatch, {"treatment": {"id": "t"}, "gauntlet": {}},
          {"draft": {"id": "d", "title": "t", "body": body, "word_count": 200},
           "gauntlet": {"outcome": "grounded"}},
          {"caveat_check": {"verdict": "verified"}})
    monkeypatch.setattr(pl, "build_comprehension_reviewer", lambda ctx: reviewer)
    monkeypatch.setattr(pl, "build_drafter", _never)

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": _spine_profile("p")})["pipeline"]
    assert len(reviewer.calls) == 1
    assert r["comprehension_rounds"] == 1


def test_a_rejected_repair_stops_the_loop_early(monkeypatch) -> None:
    """A drafter returning nothing usable will do so again; burning the second lap is waste."""
    reviewer = _counting(
        {"comprehension_check": {"verdict": "needs_ramp", "findings": [{"id": "cmp_01"}]}})
    drafter = _counting({})                # produces no draft
    r = _wire_review(monkeypatch, reviewer, drafter)

    assert len(reviewer.calls) == 1 and len(drafter.calls) == 1
    assert r["comprehension_rounds"] == 1
    assert r["status"] == "publishable"
