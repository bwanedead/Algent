"""
The coding harness the analytics worker drives — grok-build or codex, behind one seam.

The worker shells out to an agentic coding CLI to actually draw a figure inside a pinned
scratch folder. Which CLI that is should not be a property of the worker: they are
interchangeable for this job, they have different quotas, and being able to switch when
one runs dry is the difference between an article with a chart and one without.

Two implementations, same contract:

- **codex** (``codex exec``) — the default. Web access is OFF unless ``--search`` is
  passed, which matches what we want: a chart built from profile-held numbers must not be
  able to wander onto the internet, and only a ``may_source`` request earns that.
- **grok** (``grok -p``) — the original. Web is ON by default there, so it has to be
  switched off explicitly with ``--disable-web-search``; the asymmetry is why each harness
  builds its own argv rather than sharing a flag list.

Both run with the working directory pinned to the request's scratch folder and with
approvals pre-granted, because the integrity guarantee lives in the *harness* around the
subprocess (pinned cwd, artifact allow-list, cleanup) rather than in anything the
subprocess promises. Neither is trusted; both are contained.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def executable(name: str) -> str | None:
    """Absolute path to a CLI, or None when it isn't installed.

    Resolved with ``shutil.which`` rather than passed to ``subprocess`` as a bare name,
    because on Windows these ship as npm ``.cmd`` shims and ``CreateProcess`` does not
    apply PATHEXT — ``subprocess.run(["codex", ...])`` raises FileNotFoundError for a CLI
    the shell finds fine. That failure mode is invisible: the harness just looks absent.
    """
    return shutil.which(name)

# codex is the default: it is what stays available when grok-build quota runs out, and its
# offline-by-default posture is the safer of the two.
DEFAULT_HARNESS = "codex"
_ENV_HARNESS = "ALGENT_ANALYTICS_HARNESS"   # "codex" | "grok"
# Start on luna; terra is the heavier sibling to try if luna draws poorly.
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
            proc = subprocess.run(
                [exe, *argv[1:]],
                capture_output=True, text=True, timeout=timeout,
                # These CLIs emit UTF-8 (smart quotes / emoji); decode as such so a Windows
                # cp1252 locale cannot crash the decode. errors='replace' keeps a garbled
                # tail from ever raising.
                encoding="utf-8", errors="replace",
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
            cmd.append("--search")
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


def _capture(cmd: list[str], *, timeout: float = 30.0) -> str | None:
    exe = executable(cmd[0])
    if exe is None:
        return None
    try:
        proc = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return ((proc.stdout or "") + (proc.stderr or "")).strip()
