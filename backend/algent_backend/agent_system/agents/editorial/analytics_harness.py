"""
The coding harness the analytics worker drives — grok-build or codex, behind one seam.

The worker shells out to an agentic coding CLI to actually draw a figure inside a pinned
scratch folder. Which CLI that is should not be a property of the worker: they are
interchangeable for this job, they have different quotas, and being able to switch when
one runs dry is the difference between an article with a chart and one without.

Two implementations, same contract:

- **codex** (``codex exec``) — the fallback when grok quota is gone. Web access is OFF
  unless ``--search`` is passed, which matches what we want: a chart built from
  profile-held numbers must not be able to wander onto the internet, and only a
  ``may_source`` request earns that.
- **grok** (``grok -p``) — the default while quota lasts. Web is ON by default there, so
  it has to be switched off explicitly with ``--disable-web-search``; the asymmetry is
  why each harness builds its own argv rather than sharing a flag list.

Both run with the working directory pinned to the request's scratch folder and with
approvals pre-granted, because the integrity guarantee lives in the *harness* around the
subprocess (pinned cwd, artifact allow-list, cleanup, tree-kill on timeout) rather than
in anything the subprocess promises. Neither is trusted; both are contained.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from algent_backend.agent_system.runs.control_plane.process_tree import run_capturing


@lru_cache(maxsize=8)
def executable(name: str) -> str | None:
    """Absolute path to a CLI, or None when it isn't installed.

    Resolved with ``shutil.which`` rather than passed to ``subprocess`` as a bare name,
    because on Windows these ship as npm ``.cmd`` shims and ``CreateProcess`` does not
    apply PATHEXT — ``subprocess.run(["codex", ...])`` raises FileNotFoundError for a CLI
    the shell finds fine. That failure mode is invisible: the harness just looks absent.
    """
    return shutil.which(name)

# grok is the default while quota lasts; flip to codex (Luna) via
# ``ALGENT_ANALYTICS_HARNESS=codex`` when grok-build runs dry. Codex stays the
# offline-by-default safer posture for that fallback.
DEFAULT_HARNESS = "grok"
_ENV_HARNESS = "ALGENT_ANALYTICS_HARNESS"   # "codex" | "grok"
# Codex fallback model — luna; terra is the heavier sibling to try if luna draws poorly.
DEFAULT_CODEX_MODEL = "gpt-5.6-luna"
_ENV_CODEX_MODEL = "ALGENT_CODEX_MODEL"

HARNESSES = ("codex", "grok")


@dataclass(frozen=True)
class HarnessResult:
    ok: bool
    tail: str


class Harness:
    """One agentic CLI, driven headless with its cwd pinned to a scratch folder."""

    name = "harness"

    def argv(self, prompt: str, folder: Path, *, allow_web: bool) -> list[str]:
        raise NotImplementedError

    def run(
        self, prompt: str, folder: Path, *, timeout: float, allow_web: bool = False,
    ) -> tuple[bool, str]:
        """Returns ``(ok, tail-of-output)``. Never raises — a dead CLI is a missing figure."""
        argv = self.argv(prompt, folder, allow_web=allow_web)
        exe = executable(argv[0])
        if exe is None:
            return False, f"{self.name} CLI not found on PATH"
        try:
            proc = run_capturing(
                [exe, *argv[1:]],
                timeout=timeout,
                # These CLIs emit UTF-8 (smart quotes / emoji); decode as such so a Windows
                # cp1252 locale cannot crash the decode. errors='replace' keeps a garbled
                # tail from ever raising.
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return False, f"{self.name} CLI not found on PATH"
        except subprocess.TimeoutExpired:
            return False, f"{self.name} timed out after {timeout}s"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"{self.name} failed to start: {str(exc)[:120]}"
        out = (proc.stdout or "")[-600:] + (("\n" + proc.stderr[-300:]) if proc.stderr else "")
        return proc.returncode == 0, out

    def version(self) -> str:
        """Exact harness version — stamped on every artifact so a shift in analytics quality
        can be correlated to a tool version from the ledger instead of guessed."""
        return _capture([self.name, "--version"]) or "unknown"

    def update(self) -> str:
        """Update AT A RUN BOUNDARY only (never mid-run — one tool version per article)."""
        return "no update path"


class CodexHarness(Harness):
    name = "codex"

    def model(self) -> str:
        return os.environ.get(_ENV_CODEX_MODEL, DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL

    def argv(self, prompt: str, folder: Path, *, allow_web: bool) -> list[str]:
        cmd = [
            "codex", "exec", prompt,
            "-C", str(folder),
            "-m", self.model(),
            # Sandboxed auto-execution with write access to the pinned folder.
            "--full-auto",
            # The scratch folder is not a git repo, and must not be treated as one.
            "--skip-git-repo-check",
            # Don't leave session files behind for a throwaway one-shot.
            "--ephemeral",
            "--color", "never",
        ]
        if allow_web:
            # Off unless asked: only a may_source request may reach the network.
            #
            # NOT ``--search``: that flag exists on the top-level ``codex`` command but not on
            # ``codex exec``, which rejects it outright ("unexpected argument '--search'
            # found"). Passing it failed every web-allowed analytic on this harness while
            # offline ones kept working — a partial failure that reads like the request being
            # unbuildable rather than the flag being wrong.
            cmd += ["-c", "tools.web_search=true"]
        return cmd

    def version(self) -> str:
        raw = _capture(["codex", "--version"]) or "unknown"
        return f"{raw} ({self.model()})" if raw != "unknown" else raw

    def update(self) -> str:
        # Installed via npm, so there is no self-update subcommand to call. Saying so beats
        # shelling out to a package manager mid-pipeline.
        return "codex: npm-managed, no in-CLI update"


class GrokHarness(Harness):
    name = "grok"

    def argv(self, prompt: str, folder: Path, *, allow_web: bool) -> list[str]:
        cmd = [
            "grok", "-p", prompt, "--cwd", str(folder), "--output-format", "json",
            "--always-approve", "--no-memory",
        ]
        if not allow_web:
            # Inverse of codex: grok searches unless told not to.
            cmd.append("--disable-web-search")
        return cmd

    def update(self) -> str:
        """The harness's improvement curve IS the analytics quality curve, so we take the
        newest build every run rather than pinning. Affordable precisely because analytics
        degrade gracefully: a bad release costs one missing visual, never a broken article
        (contrast the drafter's model, where the same policy would be reckless)."""
        out = _capture(["grok", "update"], timeout=180)
        if out is None:
            return "update skipped (grok not available)"
        lines = out.splitlines()
        return lines[-1][:160] if lines else "updated"


_REGISTRY: dict[str, type[Harness]] = {"codex": CodexHarness, "grok": GrokHarness}


def resolve_harness(name: str | None = None) -> Harness:
    """Pick the harness: explicit argument → ``ALGENT_ANALYTICS_HARNESS`` → default."""
    chosen = (name or os.environ.get(_ENV_HARNESS, "") or DEFAULT_HARNESS).strip().lower()
    return _REGISTRY.get(chosen, _REGISTRY[DEFAULT_HARNESS])()


def fallback_for(harness: Harness) -> Harness | None:
    """The other installed harness, or None when there isn't one."""
    for other in HARNESSES:
        if other != harness.name and executable(other) is not None:
            return _REGISTRY[other]()
    return None


def run_with_fallback(
    prompt: str, folder: Path, *, timeout: float, allow_web: bool = False,
    harness: Harness | None = None, on_note: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Run the chosen harness; on failure, try the other one before giving up.

    These CLIs fail for reasons that have nothing to do with the request — a quota wall, a
    model the installed version is too old to run (codex 0.125 cannot run the 5.6 family),
    an auth expiry. Any of those costs the article every one of its figures, silently,
    because a failed analytic degrades to no analytic. Trying the sibling is nearly free and
    turns a whole-run loss into a log line.
    """
    primary = harness or resolve_harness()
    ok, tail = primary.run(prompt, folder, timeout=timeout, allow_web=allow_web)
    if ok:
        return True, tail

    other = fallback_for(primary)
    if other is None:
        return False, tail
    if on_note is not None:
        on_note(f"analytics: {primary.name} failed ({tail.strip()[-120:]}); retrying on {other.name}")
    ok2, tail2 = other.run(prompt, folder, timeout=timeout, allow_web=allow_web)
    return ok2, (tail2 if ok2 else f"{primary.name}: {tail}\n{other.name}: {tail2}")


def _capture(cmd: list[str], *, timeout: float = 30.0) -> str | None:
    exe = executable(cmd[0])
    if exe is None:
        return None
    try:
        proc = run_capturing(
            [exe, *cmd[1:]], timeout=timeout, encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return ((proc.stdout or "") + (proc.stderr or "")).strip()
