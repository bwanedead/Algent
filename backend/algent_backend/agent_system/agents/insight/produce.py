"""Warrant → critique → draw (once more if the picture is salvageable) → files on disk."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from algent_backend.agent_system.agents.insight.contracts import (
    InsightSpec,
    apply_critique,
    draw_payload,
)
from algent_backend.agent_system.agents.insight.copy import format_copy
from algent_backend.agent_system.agents.insight.critique import critique, mechanical_ok
from algent_backend.agent_system.agents.insight.seeds import discovery_brief
from algent_backend.agent_system.agents.insight.warrant import warrant
from algent_backend.agent_system.foundation.models.resolver import ModelResolver

_DRAW = "scripts/draw_insight.py"


def default_workspace() -> Path:
    """Repo-root ``analytics_workspace/`` (insight → agents → agent_system → algent_backend → backend → root)."""
    return Path(__file__).resolve().parents[5] / "analytics_workspace"


def workspace_python(workspace: Path | None = None) -> Path | None:
    root = workspace or default_workspace()
    win = root / ".venv" / "Scripts" / "python.exe"
    unix = root / ".venv" / "bin" / "python"
    if win.is_file():
        return win
    if unix.is_file():
        return unix
    return None


def already_said(posts: list) -> list[str]:
    out = []
    for p in posts:
        text = getattr(p, "text", "") or ""
        if text:
            out.append(text.split("\n", 1)[0][:180])
    return out


def produce(
    *,
    dest: Path,
    already: list[str] | None = None,
    resolver: ModelResolver | None = None,
    python: Path | None = None,
    workspace: Path | None = None,
) -> tuple[InsightSpec, str, str]:
    """Returns (spec, copy, media_path). media_path empty means skip."""
    spec = warrant(already=already, seeds=discovery_brief(), resolver=resolver)
    gate = mechanical_ok(spec)
    if gate:
        spec.note = spec.note or gate
        spec.warranted = False
        return spec, "", ""

    review = critique(spec, resolver=resolver)
    if review.verdict == "abandon":
        spec.warranted = False
        spec.note = review.reason
        return spec, "", ""
    if review.verdict == "fix":
        spec = apply_critique(spec, review)
        again = critique(spec, resolver=resolver)
        if again.verdict == "abandon":
            spec.warranted = False
            spec.note = again.reason
            return spec, "", ""
        if again.verdict == "fix":
            spec = apply_critique(spec, again)

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    suffix = ".gif" if spec.form == "growing_line_gif" else ".png"
    media = dest / f"chart{suffix}"
    spec_path = dest / "spec.json"
    spec_path.write_text(json.dumps(draw_payload(spec, str(media)), indent=2), encoding="utf-8")
    err = draw_spec(spec_path, python=python, workspace=workspace)
    if err:
        spec.warranted = False
        spec.note = err
        return spec, "", ""
    if not media.is_file():
        spec.warranted = False
        spec.note = "draw produced no file"
        return spec, "", ""
    return spec, format_copy(spec), str(media)


def draw_spec(
    spec_path: Path,
    *,
    python: Path | None = None,
    workspace: Path | None = None,
) -> str:
    """Empty on success; otherwise a skip reason. Never raises."""
    root = workspace or default_workspace()
    py = python or workspace_python(root)
    if py is None:
        return "analytics_workspace venv missing — insight draw needs that interpreter"
    script = root / _DRAW
    if not script.is_file():
        return "draw_insight.py missing"
    try:
        proc = subprocess.run(
            [str(py), str(script), str(spec_path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"draw failed: {str(exc)[:140]}"
    if proc.returncode != 0:
        return f"draw failed: {(proc.stderr or proc.stdout or '')[:160]}"
    return ""
