"""Tests for the analytics_worker — the sandboxed fulfill + the harness-owned integrity checks.

The grok subprocess is faked (a ``runner`` that writes files into the scratch folder), so these
run offline and deterministically. What they pin is the HARNESS behaviour: grounding the hand-off,
the sweep, the visual figure check, copying the artifact out, and emptying the scratch folder.
"""

from __future__ import annotations

from pathlib import Path

from algent_backend.agent_system.agents.editorial import analytics_worker as aw
from algent_backend.agent_system.agents.editorial.analytics_contracts import (
    AnalyticsPlan,
    AnalyticsRequest,
)
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
    SourceSnapshot,
)
from algent_backend.agent_system.artifacts import ArtifactWriter
from algent_backend.agent_system.runs.context import AgentRunContext


def _profile() -> SignalProfile:
    return SignalProfile(
        id="prof_x", title="Fed path", as_of="2026-06-30",
        source_ledger=[SourceArtifact(
            id="s1", url="u", title="CPI report", publisher="BLS",
            snapshot=SourceSnapshot(excerpt="core PCE rose to 3.4% in May from 3.1% in April"))],
        claim_ledger=[
            Claim(id="c1", text="core PCE rose 3.4% in May", supported_by=["s1"]),
            Claim(id="c2", text="it was 3.1% in April", supported_by=["s1"]),
        ],
    )


def _request() -> AnalyticsRequest:
    return AnalyticsRequest(id="anx_01", kind="chart", title="PCE trend",
                            question="how is inflation moving?", spec="line chart of PCE y/y",
                            data_refs=["c1", "c2"], rationale="shows the trend")


def _ctx(tmp_path: Path, events: list) -> AgentRunContext:
    writer = ArtifactWriter(tmp_path / "artifacts", run_id="t")
    return AgentRunContext(
        run_id="t", model_resolver=None,  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
        artifacts=writer,
    )


def _good_runner(chart="x,y\nApril,3.1\nMay,3.4\n"):
    """A fake grok that draws a faithful chart from the given data."""
    def run(_prompt: str, folder: Path) -> tuple[bool, str]:
        (folder / "chart.svg").write_text("<svg>PCE</svg>", encoding="utf-8")
        (folder / "data.csv").write_text(chart, encoding="utf-8")
        (folder / "caption.md").write_text("Core PCE ticked up from April to May.", encoding="utf-8")
        return True, "{}"
    return run


def test_produces_artifact_copies_it_out_and_empties_scratch(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ctx = _ctx(tmp_path, [])
    art = aw.fulfill_request(_request(), _profile(), workspace=ws, context=ctx, runner=_good_runner())

    assert art.status == "produced"
    assert art.figure_check["verified"] is True and art.figure_check["unverified"] == []
    # Human-readable provenance only — claim ids stay out of the reader-facing caption.
    assert art.ai_label and "cited claims" not in art.caption and "clm_" not in art.caption
    assert "BLS" in art.caption and "2026-06-30" in art.caption
    # Cold-reader explainer: question (what is measured) appears in the caption.
    assert "how is inflation moving" in art.caption.lower()
    # the artifact + its data were copied into the run's artifact store
    assert (tmp_path / "artifacts" / art.artifact_name).exists()
    assert (tmp_path / "artifacts" / art.data_name).exists()
    # the scratch folder is emptied after — the workspace does not accumulate
    assert not (ws / "anx_01").exists()
    # SVG-only: no raster to copy. X posts need a PNG the drawer did not write.
    assert art.raster_name == ""


def test_a_png_beside_the_svg_is_copied_for_social(tmp_path: Path) -> None:
    """X cannot take SVG. When the drawer wrote chart.png, the harness keeps it."""
    def run(_prompt: str, folder: Path) -> tuple[bool, str]:
        (folder / "chart.svg").write_text("<svg>PCE</svg>", encoding="utf-8")
        (folder / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (folder / "data.csv").write_text("x,y\nApril,3.1\nMay,3.4\n", encoding="utf-8")
        (folder / "caption.md").write_text("Core PCE ticked up.", encoding="utf-8")
        return True, "{}"

    ctx = _ctx(tmp_path, [])
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             context=ctx, runner=run)
    assert art.status == "produced"
    assert art.raster_name.endswith(".png")
    assert (tmp_path / "artifacts" / art.raster_name).is_file()
    assert art.artifact_name.endswith(".svg")


def test_table_kind_carries_body_md_for_inlining(tmp_path: Path) -> None:
    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "table.md").write_text("| Outcome | P |\n|--|--|\n| Hold | 3.4 |", encoding="utf-8")
        (folder / "data.csv").write_text("outcome,p\nHold,3.4\n", encoding="utf-8")
        (folder / "caption.md").write_text("the odds", encoding="utf-8")
        return True, "{}"
    req = _request().model_copy(update={"kind": "table"})
    art = aw.fulfill_request(req, _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "produced" and art.artifact_name.endswith(".md")
    assert "| Outcome | P |" in art.body_md          # the markdown body travels for the publish view


def test_figure_check_flags_a_number_not_in_the_evidence(tmp_path: Path) -> None:
    # 9.9 is nowhere in the claims/snapshot — the visual analog of unverified_prose_figures.
    # Failed integrity must not ship as produced.
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             runner=_good_runner("x,y\nApril,3.1\nMay,9.9\n"))
    assert art.status == "integrity_check_failed"
    assert art.figure_check["verified"] is False and "9.9" in art.figure_check["unverified"]
    assert "9.9" in art.note
    assert not art.artifact_name


def test_may_source_without_profile_data_refs_produces(tmp_path: Path) -> None:
    # Profile and analytics are separate: worker may fulfill a sourced series that the profile
    # never held as claims. Provenance requires a data table AND a publisher URL in caption.md.
    req = AnalyticsRequest(
        id="anx_src", kind="chart", title="Weekly cases",
        question="Is the outbreak accelerating?",
        spec="line of weekly confirmed cases",
        data_refs=[], may_source=True,
        source_hint="WHO weekly Ebola case counts DRC last 8 weeks",
        rationale="trajectory",
    )

    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "chart.svg").write_text("<svg>cases</svg>", encoding="utf-8")
        (folder / "data.csv").write_text("week,cases\n1,10\n2,25\n3,40\n", encoding="utf-8")
        (folder / "caption.md").write_text(
            "Weekly cases rose. Source: WHO https://www.who.int/ebola", encoding="utf-8",
        )
        return True, "{}"

    art = aw.fulfill_request(req, _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "produced"
    assert art.figure_check.get("mode") == "sourced"
    assert art.figure_check["verified"] is True
    assert "sourced" in art.ai_label.lower() or "Sourced" in art.caption


def test_may_source_without_publisher_url_fails_integrity(tmp_path: Path) -> None:
    req = AnalyticsRequest(
        id="anx_src", kind="chart", title="Weekly cases",
        question="Is the outbreak accelerating?",
        spec="line of weekly confirmed cases",
        data_refs=[], may_source=True,
        source_hint="WHO weekly Ebola case counts",
        rationale="trajectory",
    )
    art = aw.fulfill_request(
        req, _profile(), workspace=tmp_path / "ws",
        runner=_good_runner("week,cases\n1,10\n2,25\n"),
    )
    assert art.status == "integrity_check_failed"
    assert "publisher URL" in " ".join(art.figure_check.get("unverified") or [])


def test_may_source_without_hint_fails(tmp_path: Path) -> None:
    req = AnalyticsRequest(id="anx_bad", kind="chart", data_refs=[], may_source=False)
    art = aw.fulfill_request(req, _profile(), workspace=tmp_path / "ws", runner=_good_runner())
    assert art.status == "failed"
    assert "data_refs" in art.note


def test_skipped_when_worker_declines(tmp_path: Path) -> None:
    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "SKIPPED.md").write_text("data too thin to plot honestly", encoding="utf-8")
        return True, "{}"
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "skipped" and "too thin" in art.note


def test_sweep_deletes_disallowed_files(tmp_path: Path) -> None:
    def run(_p: str, folder: Path) -> tuple[bool, str]:
        (folder / "chart.svg").write_text("<svg/>", encoding="utf-8")
        (folder / "data.csv").write_text("x,y\nMay,3.4\n", encoding="utf-8")
        (folder / "caption.md").write_text("cap", encoding="utf-8")
        (folder / "sneaky.exe").write_bytes(b"MZ\x00\x00")   # not on the allowlist
        return True, "{}"
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws", runner=run)
    assert art.status == "produced"
    assert any("sneaky.exe" in s for s in art.swept)


def test_no_output_is_a_clean_failure(tmp_path: Path) -> None:
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             runner=lambda _p, _f: (False, "grok error"))
    assert art.status == "failed" and art.artifact_name == ""


def test_new_escapes_diffs_against_baseline() -> None:
    # only paths that appear DURING the run count — the user's pre-existing dirt is ignored.
    assert aw._new_escapes({"a"}, {"a", "backend/evil.py"}) == ["backend/evil.py"]
    assert aw._new_escapes({"a"}, {"a"}) == []
    assert aw._new_escapes(None, {"x"}) == []   # git unavailable -> tripwire simply doesn't arm


def test_escape_tripwire_fails_loudly_even_on_a_good_chart(tmp_path: Path, monkeypatch) -> None:
    # A good-looking chart from a lane-breaking run is NOT trustworthy: hard fail + loud event.
    seen = iter([set(), {"backend/secrets.py"}])   # before -> after: a new write outside the lane
    monkeypatch.setattr(aw, "_git_status", lambda _root: next(seen))
    events: list = []
    ctx = _ctx(tmp_path, events)
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             context=ctx, runner=_good_runner())
    assert art.status == "failed" and art.escaped_writes == ["backend/secrets.py"]
    assert any(et == aw.ANALYTICS_WORKER_ESCAPE for et, _ in events)
    assert not (tmp_path / "ws" / "anx_01").exists()   # scratch still emptied


def test_store_escapes_catches_new_and_resized_files() -> None:
    # git status can't see gitignored stores; this fingerprint diff is the complement.
    # mtime-only bumps (scanners / concurrent touch) must NOT trip — size or new path must.
    before = {"p/prof_a.json": (100, 10), "p/prof_c.json": (50, 8)}
    after = {"p/prof_a.json": (200, 10),   # same size, newer mtime -> ignore
             "p/prof_b.json": (50, 5),     # brand-new file
             "p/prof_c.json": (90, 12)}    # resized -> escape
    assert aw._store_escapes(before, after) == ["p/prof_b.json", "p/prof_c.json"]
    assert aw._store_escapes(before, before) == []   # unchanged -> nothing


def test_pct_supported_by_corpus_allows_derived_ratios() -> None:
    corpus = "About 60,000 people crossed into a city of 85,000 residents."
    assert aw._pct_supported_by_corpus("71%", corpus)  # 60000/85000
    assert not aw._pct_supported_by_corpus("164%", corpus)  # not a ratio of cited counts
    assert aw._pct_supported_by_corpus("50%", "growth hit 50% year over year")


def test_store_fingerprint_covers_stores_and_env(tmp_path: Path) -> None:
    (tmp_path / "backend" / "profile_store").mkdir(parents=True)
    (tmp_path / "backend" / "profile_store" / "p.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")   # the classic escape target
    fp = aw._store_fingerprint(tmp_path)
    assert any("p.json" in k for k in fp)
    assert any(k.endswith(".env") for k in fp)   # .env is fingerprinted (metadata only, never read)


def test_tripwire_catches_a_poisoned_store_json(tmp_path: Path, monkeypatch) -> None:
    # A worker that overwrites a gitignored profile JSON must be caught even though git is clean.
    monkeypatch.setattr(aw, "_git_status", lambda _root: set())   # git sees nothing (ignored path)
    fps = iter([{}, {"backend/profile_store/prof_x.json": (1, 2)}])   # before -> after: a new write
    monkeypatch.setattr(aw, "_store_fingerprint", lambda _root: next(fps))
    events: list = []
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             context=_ctx(tmp_path, events), runner=_good_runner())
    assert art.status == "failed" and "prof_x.json" in art.escaped_writes[0]
    assert any(et == aw.ANALYTICS_WORKER_ESCAPE for et, _ in events)


def test_worker_graph_loops_warranted_requests(tmp_path: Path) -> None:
    events: list = []
    plan = AnalyticsPlan(id="analytics_prof_x", profile_id="prof_x", warranted=True, requests=[_request()])
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, events), runner=_good_runner(), refresh=False)
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})

    arts = out["analytics_artifacts"]
    assert len(arts) == 1 and arts[0]["status"] == "produced"
    done = next(p for et, p in events if et == aw.ANALYTICS_WORKER_COMPLETED)
    assert done["produced"] == 1


def test_sweep_removes_orphaned_scratch_but_spares_a_live_one(tmp_path: Path) -> None:
    # A killed run can't empty its own scratch (the finally never runs), so the workspace
    # accumulates dead folders. Age-gating is what makes the sweep safe under concurrency.
    import os
    import time as _t

    ws = tmp_path / "ws"
    (ws / "req_dead").mkdir(parents=True)
    (ws / "req_dead" / "chart.svg").write_text("<svg/>", encoding="utf-8")
    (ws / "req_live").mkdir()
    old = _t.time() - (5 * 60 * 60)
    os.utime(ws / "req_dead", (old, old))          # hours old -> its run is gone

    cleaned = aw.sweep_stale_scratch(ws)
    assert cleaned == ["req_dead"] and not (ws / "req_dead").exists()
    assert (ws / "req_live").exists()               # a concurrent run's live scratch is untouched


def test_sweep_never_deletes_weight_bearing_stack_dirs(tmp_path: Path) -> None:
    """Regression: age-sweep used to rmtree *any* old dir, including lib/scripts/data.

    That silently deleted the chart/map helpers after ~2h idle and zeroed every visual.
    """
    import os
    import time as _t

    ws = tmp_path / "ws"
    for name in ("lib", "scripts", "data", "anx_01", "req_dead", "_canary"):
        (ws / name).mkdir(parents=True)
        (ws / name / "marker.txt").write_text("x", encoding="utf-8")
    old = _t.time() - (5 * 60 * 60)
    for name in ("lib", "scripts", "data", "anx_01", "req_dead", "_canary"):
        os.utime(ws / name, (old, old))

    cleaned = aw.sweep_stale_scratch(ws)
    assert set(cleaned) == {"anx_01", "req_dead", "_canary"}
    assert (ws / "lib" / "marker.txt").exists()
    assert (ws / "scripts" / "marker.txt").exists()
    assert (ws / "data" / "marker.txt").exists()
    assert not (ws / "anx_01").exists()
    assert not (ws / "req_dead").exists()
    assert not (ws / "_canary").exists()


def test_sweep_is_a_noop_on_a_clean_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("doctrine", encoding="utf-8")
    assert aw.sweep_stale_scratch(ws) == [] and (ws / "AGENTS.md").exists()   # files are never touched


def test_canary_passes_when_the_harness_draws(tmp_path: Path) -> None:
    ok, note = aw.canary(tmp_path / "ws", runner=_good_runner())
    assert ok and note == "canary ok"
    assert not (tmp_path / "ws" / "_canary").exists()   # scratch cleaned even on the canary


def test_canary_fails_when_the_harness_draws_nothing(tmp_path: Path) -> None:
    ok, note = aw.canary(tmp_path / "ws", runner=lambda _p, _f: (True, "{}"))   # ran, drew nothing
    assert not ok and "no chart" in note


def test_a_failed_canary_skips_analytics_without_breaking_the_article(tmp_path: Path, monkeypatch) -> None:
    # The property that makes always-updating affordable: a bad harness release costs this run's
    # visuals and SAYS SO — it never blocks the piece.
    monkeypatch.setattr(aw, "update_grok", lambda: "updated to 9.9.9")
    monkeypatch.setattr(aw, "grok_version", lambda: "grok 9.9.9")
    monkeypatch.setattr(aw, "canary", lambda _ws, runner=None: (False, "canary produced no chart"))
    events: list = []
    plan = AnalyticsPlan(id="x", profile_id="prof_x", warranted=True, requests=[_request()])
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, events), runner=_good_runner(), refresh=True)
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})

    # Degraded, not crashed — each planned request is an explicit skip (never "forgotten").
    arts = out["analytics_artifacts"]
    assert len(arts) == 1 and arts[0]["status"] == "skipped"
    assert "canary" in arts[0]["note"]
    done = next(p for et, p in events if et == aw.ANALYTICS_WORKER_COMPLETED)
    assert "canary failed" in done["note"] and "9.9.9" in done["note"]
    ready = next(p for et, p in events if et == aw.ANALYTICS_WORKER_READY)
    assert ready["version"] == "grok 9.9.9"            # version stamped even on the failure path


def test_produced_artifact_is_version_stamped(tmp_path: Path) -> None:
    art = aw.fulfill_request(_request(), _profile(), workspace=tmp_path / "ws",
                             runner=_good_runner(), version="grok 0.2.63 (2ade4617f)")
    assert art.model == "grok 0.2.63 (2ade4617f)"      # provenance: which tool drew this


def test_worker_graph_does_nothing_when_not_warranted(tmp_path: Path) -> None:
    plan = AnalyticsPlan(id="x", warranted=False)
    graph = aw.build_analytics_worker_graph(_ctx(tmp_path, []), runner=_good_runner(), refresh=False)
    out = graph.invoke({"analytics_plan": plan.model_dump(), "profile": _profile().model_dump()})
    assert out["analytics_artifacts"] == []


# -- the coding harness seam: grok by default, codex when quota runs out ----------


def test_grok_is_the_default_harness(monkeypatch) -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.editorial.analytics_harness import resolve_harness

    monkeypatch.delenv("ALGENT_ANALYTICS_HARNESS", raising=False)
    h = resolve_harness()
    assert h.name == "grok"
    assert "--disable-web-search" in h.argv("draw it", Path("/scratch"), allow_web=False)
    assert "--disable-web-search" not in h.argv("draw it", Path("/scratch"), allow_web=True)


def test_codex_stays_offline_unless_asked(monkeypatch) -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.editorial.analytics_harness import resolve_harness

    monkeypatch.setenv("ALGENT_ANALYTICS_HARNESS", "codex")
    h = resolve_harness()
    assert h.name == "codex"

    offline = h.argv("draw it", Path("/scratch"), allow_web=False)
    assert offline[:2] == ["codex", "exec"]
    assert "--search" not in offline          # a profile-held chart must not reach the network
    assert "--full-auto" in offline and "--skip-git-repo-check" in offline
    assert offline[offline.index("-C") + 1] == str(Path("/scratch"))   # cwd pinned to the folder

    online = h.argv("draw it", Path("/scratch"), allow_web=True)
    # `codex exec` rejects --search ("unexpected argument"); the equivalent is a config
    # override. Getting this wrong failed every web-allowed analytic while offline ones
    # kept working, which reads like an unbuildable request rather than a bad flag.
    assert "--search" not in online
    assert "tools.web_search=true" in online   # only a may_source request earns it


def test_grok_inverts_the_web_flag(monkeypatch) -> None:
    """grok searches unless told not to; codex only when told to. Hence per-harness argv."""
    from pathlib import Path

    from algent_backend.agent_system.agents.editorial.analytics_harness import resolve_harness

    monkeypatch.setenv("ALGENT_ANALYTICS_HARNESS", "grok")
    g = resolve_harness()
    assert g.name == "grok"
    assert "--disable-web-search" in g.argv("d", Path("/s"), allow_web=False)
    assert "--disable-web-search" not in g.argv("d", Path("/s"), allow_web=True)


def test_harness_model_is_selectable(monkeypatch) -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.editorial.analytics_harness import resolve_harness

    monkeypatch.setenv("ALGENT_ANALYTICS_HARNESS", "codex")
    monkeypatch.setenv("ALGENT_CODEX_MODEL", "gpt-5.6-terra")
    argv = resolve_harness().argv("d", Path("/s"), allow_web=False)
    assert "gpt-5.6-terra" in argv


def test_a_missing_cli_is_a_missing_figure_not_a_crash(monkeypatch) -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.editorial import analytics_harness as ah

    monkeypatch.setattr(ah, "executable", lambda _n: None)
    ok, tail = ah.CodexHarness().run("d", Path("/s"), timeout=1.0)
    assert ok is False and "not found on PATH" in tail


# -- why figures kept failing integrity ---------------------------------------

def test_a_part_of_whole_remainder_is_not_fabrication() -> None:
    """The real rejection: claims held Korea's total ($496.3bn) and its chips ($149bn);
    the chart plotted chips against the NON-chip remainder, 496.3 - 149 = 347.3. Demanding
    every plotted value be quoted verbatim forbids arithmetic, i.e. forbids most charts."""
    from algent_backend.agent_system.agents.editorial.analytics_worker import (
        _arithmetic_supported,
    )

    nums = [496.3, 149.0, 416.6, 133.2]
    assert _arithmetic_supported(347.3, nums) is True     # 496.3 - 149
    assert _arithmetic_supported(283.4, nums) is True     # 416.6 - 133.2
    assert _arithmetic_supported(645.3, nums) is True     # 496.3 + 149
    assert _arithmetic_supported(999.9, nums) is False    # invented still fails


def test_years_written_as_floats_are_not_treated_as_figures() -> None:
    """A CSV renders its year column as 2019.0 (pandas does this), which slips past the
    bare-integer exclusion — so a decade-long trajectory was rejected for citing its decade."""
    from algent_backend.agent_system.agents.editorial.analytics_worker import (
        _visual_unverified_figures,
    )

    class _C:
        text = "Korea exported $496.3 billion in H1 2026"
        supported_by: list = []

    data = "year,korea\n2019.0,542.2\n2020.0,512.5\n"
    out = _visual_unverified_figures(data, [_C()], {})
    assert not any(y in out for y in ("2019.0", "2020.0")), out


def test_a_sourced_request_is_not_held_to_the_profile_standard() -> None:
    """may_source exists so a figure can fetch what the profile lacks. Gating on
    'may_source AND no claims' meant a grounded+sourced request could only ever fail:
    anything fetched was by definition absent from the ledger."""
    import inspect

    from algent_backend.agent_system.agents.editorial import analytics_worker as aw

    src = inspect.getsource(aw.fulfill_request)
    assert "if request.may_source and not cited_claims:" not in src
    assert "if request.may_source:" in src


def test_sourced_rows_become_claim_shaped_evidence() -> None:
    from algent_backend.agent_system.agents.editorial.analytics_contracts import (
        AnalyticsRequest,
    )
    from algent_backend.agent_system.agents.editorial.analytics_worker import _sourced_claims

    req = AnalyticsRequest(id="r1", kind="chart", title="Exports by year", may_source=True)
    rows = _sourced_claims(
        "year,korea_bn\n2019,542.2\n2020,512.5\n",
        "Series from KITA. https://stat.kita.net/x — as of 2026",
        req,
    )
    assert len(rows) == 2
    assert rows[0]["url"] == "https://stat.kita.net/x"
    assert "2019" in rows[0]["text"] and "542.2" in rows[0]["text"]


def test_default_runner_falls_back_when_the_primary_harness_dies(monkeypatch, tmp_path: Path) -> None:
    """Poland: grok canary timed out and both warranted figures were skipped.

    ``run_with_fallback`` already existed; the worker never called it. Pin the
    ``_grok_runner`` seam — a revert to ``resolve_harness().run`` must fail this test.
    """
    called: dict[str, bool] = {}

    def fake_fallback(*_a, **_k):
        called["yes"] = True
        return True, "drew"

    monkeypatch.setattr(aw, "run_with_fallback", fake_fallback)
    ok, tail = aw._grok_runner("p", tmp_path, timeout=1)
    assert ok and tail == "drew" and called.get("yes")


def test_unattributed_data_never_becomes_a_claim() -> None:
    """No publisher URL, no claim — an unattributed number is not evidence."""
    from algent_backend.agent_system.agents.editorial.analytics_contracts import (
        AnalyticsRequest,
    )
    from algent_backend.agent_system.agents.editorial.analytics_worker import _sourced_claims

    req = AnalyticsRequest(id="r1", kind="chart", may_source=True)
    assert _sourced_claims("year,v\n2019,1\n", "no url here", req) == []
