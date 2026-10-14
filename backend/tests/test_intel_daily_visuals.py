"""Daily visuals, round two: calendar fragments are not claims, the harness sandbox switch, and --visuals-only."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.editorial import analytics_harness as ah
from algent_backend.agent_system.agents.editorial import analytics_worker as w
from algent_backend.agent_system.agents.intel import daily, daily_visuals, visuals
from algent_backend.agent_system.agents.intel.visuals_grounding import ungrounded

FACTS = "Strikes hit 12.5% of berths on 2026-09-27. About 1,200 ships waited."


# -- grounding: dates are labels for WHEN, not quantities ------------------------------

@pytest.mark.parametrize("text", [
    "From 2026-10-08 to 2026-10-09", "Between 8-9 Oct", "On Oct 08 and the 09th", "the 1st, 2nd and 22nd",
    "At 14:30 UTC", "On 10 October 2026", "October 8th, 2026", "08", "09", "in 2026-10", "12/10/2026",
])
def test_calendar_fragments_are_not_ungrounded_numbers(text: str) -> None:
    assert ungrounded(text, FACTS) == []


def test_real_quantities_are_still_checked() -> None:
    assert ungrounded("hit 99.9% of berths", FACTS) == ["99.9%"]
    assert ungrounded("12-15 ships", FACTS) == ["12", "15"]            # a range is a quantity, not a date
    assert ungrounded("1200 ships and 12.50% of berths", FACTS) == []   # compared by value, not by spelling


# -- the harness sandbox switch --------------------------------------------------------

def _fake_proc(out: str, rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr="")


@pytest.fixture
def calls(monkeypatch):
    seen: list[dict] = []
    outs: list[str] = []

    def fake(argv, **kw):
        seen.append({"argv": argv, "env": kw.get("env"), "cwd": kw.get("cwd")})
        return _fake_proc(outs.pop(0) if outs else "ok")

    monkeypatch.setattr(ah, "run_capturing", fake)
    monkeypatch.setattr(ah, "executable", lambda n: n)
    monkeypatch.setattr(ah, "_relaxed_for_process", False)
    monkeypatch.delenv("ALGENT_HARNESS_SANDBOX", raising=False)
    seen_outs = outs
    return seen, seen_outs


def test_codex_argv_swaps_its_sandbox_in_workspace_mode() -> None:
    inside = ah.CodexHarness().argv("d", Path("/s"), allow_web=False, sandbox="harness")
    outside = ah.CodexHarness().argv("d", Path("/s"), allow_web=False, sandbox="workspace")
    assert "--full-auto" in inside and "-s" not in inside
    assert "--full-auto" not in outside and outside[outside.index("-s") + 1] == "danger-full-access"
    assert outside[outside.index("-C") + 1] == str(Path("/s"))


def test_workspace_mode_pins_cwd_and_strips_the_environment(calls, monkeypatch) -> None:
    seen, _ = calls
    monkeypatch.setenv("ALGENT_HARNESS_SANDBOX", "workspace")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("CODEX_HOME", "/home/o/.codex")
    ah.CodexHarness().run("d", Path("/scratch"), timeout=1.0)
    env = seen[0]["env"]
    assert seen[0]["cwd"] == str(Path("/scratch"))
    assert "SUPABASE_SERVICE_KEY" not in env and env["PATH"] == "/usr/bin" and env["CODEX_HOME"] == "/home/o/.codex"


def test_auto_falls_back_once_when_the_cli_sandbox_cannot_start(calls, monkeypatch) -> None:
    seen, outs = calls
    monkeypatch.setattr(ah.sys, "platform", "win32")          # auto starts sandboxed away from Linux
    outs += ["I couldn't generate chart.svg: bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted", "done"]
    ok, tail = ah.CodexHarness().run("d", Path("/s"), timeout=1.0)
    assert ok and tail == "done" and len(seen) == 2
    assert "--full-auto" in seen[0]["argv"] and "danger-full-access" in seen[1]["argv"]
    seen.clear()
    ah.CodexHarness().run("d", Path("/s"), timeout=1.0)        # remembered: the next run starts unsandboxed
    assert len(seen) == 1 and "danger-full-access" in seen[0]["argv"]


def test_auto_is_unsandboxed_on_linux_and_explicit_harness_never_retries(calls, monkeypatch) -> None:
    seen, outs = calls
    monkeypatch.setattr(ah.sys, "platform", "linux")
    ah.GrokHarness().run("d", Path("/s"), timeout=1.0)
    assert seen[0]["env"] is not None
    seen.clear()
    monkeypatch.setenv("ALGENT_HARNESS_SANDBOX", "harness")
    outs.append("bwrap: loopback failed")
    ok, _ = ah.CodexHarness().run("d", Path("/s"), timeout=1.0)
    assert len(seen) == 1 and "--full-auto" in seen[0]["argv"]


# -- visuals-only ----------------------------------------------------------------------

SRC = "https://wire.example/strikes"


def _record() -> dict:
    def dev(h, detail, when):
        return {"headline": h, "detail": detail, "when": when, "significance": "", "statements": [], "sources": [SRC]}
    return {"schema": 1, "domain": "geopolitics", "date": "2026-09-29", "summary": {"headline": "H", "the_day": []},
            "theaters": [{"theater_id": "thr_a", "name": "Alpha", "headline": "Alpha heats", "bottom_line": "x",
                          "developments": [dev("Port strike", "Strikes hit 12.5% of berths", "2026-09-27"),
                                           dev("Second wave", "Another 31.4% of berths were hit", "2026-09-28"),
                                           dev("Third wave", "Damage reached 58.2% of berths", "2026-09-29"),
                                           dev("Talks", "Delegations met", "2026-09-29")],
                          "key_figures": [], "numbers": {}}]}


def _runner(folder_prompt_ok=True):
    def run(prompt, folder):
        (folder / "chart.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
                                          '<rect x="10" y="10" width="50" height="50"/></svg>', encoding="utf-8")
        (folder / "data.csv").write_text("wave,share\n1,12.5%\n2,31.4%\n3,58.2%\n", encoding="utf-8")
        (folder / "caption.md").write_text("Share of berths hit.", encoding="utf-8")
        return True, "ok"
    return run


def test_visuals_only_adds_visuals_without_touching_text_or_the_writer(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(w, "default_workspace", lambda: tmp_path / "analytics_workspace")
    monkeypatch.setattr(daily, "daily_dir", lambda _d: tmp_path)
    (tmp_path / "2026-09-29.json").write_text(json.dumps(_record()), encoding="utf-8")
    plan = visuals.VisualPlan(visuals=[visuals.VisualAsk(
        theater_id="thr_a", form="chart", finding="Berth damage climbs each wave",
        caption="Share of berths hit, by wave, 2026-09-27 to 2026-09-29.", reader_question="How fast?",
        why_not_prose="three numbers over time", fact_ids=["f1.1", "f1.2", "f1.3"],
        spec="bars of 12.5, 31.4 and 58.2 percent for 08 and 09 Oct")])
    asked: list[str] = []
    uploads: list[dict] = []
    out = daily_visuals.redo(
        None, None, "geopolitics", "2026-09-29",
        ask=lambda schema, role, task: asked.append(schema.__name__) or plan,
        ready=lambda: (True, ""), runner=_runner(),
        uploader=lambda files: uploads.append(files) or {"ok": True, "failed": []})
    assert out["produced"] == 1 and asked == ["VisualPlan"], out      # one planning call, no writer
    saved = json.loads((tmp_path / "2026-09-29.json").read_text(encoding="utf-8"))
    assert saved["theaters"][0]["visuals"][0]["kind"] == "chart" and saved["visuals_run"]["produced"] == 1
    assert saved["summary"] == {"headline": "H", "the_day": []} and uploads

    again = daily_visuals.redo(None, None, "geopolitics", "2026-09-29", ask=lambda *_a: pytest.fail("replanned"),
                               ready=lambda: (True, ""), runner=_runner())
    assert again["produced"] == 0 and again["visuals_run"] == {"reused": 1}      # drawn work is kept

    fresh = daily_visuals.redo(None, None, "geopolitics", "2026-09-29", fresh=True, ask=lambda *_a: plan,
                               ready=lambda: (True, ""), runner=_runner(),
                               uploader=lambda files: {"ok": True, "failed": []})
    assert fresh["produced"] == 1


def test_visuals_only_reports_a_missing_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(daily, "daily_dir", lambda _d: tmp_path)
    assert "no daily record" in daily_visuals.redo(None, None, "geopolitics", "2030-01-01")["error"]
