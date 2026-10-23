"""
The deploy routine's helper: wait for the Vercel preview of a commit and smoke-test it (docs/guides/deploy.md).

Vercel's GitHub integration records every deployment on the commit as a GitHub *deployment* whose status carries the preview URL (``environment_url``) and
whose state turns ``success`` when the build is live. This reads that over the plain GitHub REST API - no ``gh`` CLI. A public repository needs no token;
a private one needs ``GITHUB_TOKEN`` in the environment (read-only is enough). A preview behind Vercel's deployment protection answers 401 to the smoke
test unless ``VERCEL_AUTOMATION_BYPASS_SECRET`` is set (``fetch.py`` sends it as ``x-vercel-protection-bypass``).

Exit codes of ``newsroom site deploy-check``: 0 preview is healthy, 1 smoke test failed, 2 usage, 3 no ready preview within the wait.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from . import flags

API = "https://api.github.com"
Get = Callable[[str], tuple[int, Any]]
_FAILED = ("failure", "error", "inactive")


def repo_slug(remote_url: str) -> str:
    """``owner/name`` from an https or ssh remote URL."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", remote_url.strip())
    if not m:
        raise ValueError(f"cannot read a GitHub repository from {remote_url!r}")
    return f"{m.group(1)}/{m.group(2)}"


def origin_slug() -> str:
    out = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=15, check=False)
    return repo_slug(out.stdout)


def github_get(path: str) -> tuple[int, Any]:
    headers = {"User-Agent": flags.USER_AGENT, "Accept": "application/vnd.github+json"}
    if (token := os.environ.get("GITHUB_TOKEN", "").strip()):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=30) as resp:   # noqa: S310
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


def resolve_sha(slug: str, ref: str, get: Get = github_get) -> str:
    status, body = get(f"/repos/{slug}/commits/{ref}")
    if status == 404:
        raise LookupError(f"{slug}@{ref} not found (a private repository needs GITHUB_TOKEN)")
    if status != 200 or not isinstance(body, dict) or not body.get("sha"):
        raise LookupError(f"GitHub answered {status} for {slug}@{ref}")
    return str(body["sha"])


def preview_state(slug: str, sha: str, get: Get = github_get) -> tuple[str, str, str]:
    """(state, url, note) of the newest preview deployment of ``sha``: state is ``none`` (no deployment yet), ``pending``, ``ready`` or ``failed``."""
    status, deployments = get(f"/repos/{slug}/deployments?sha={sha}&per_page=10")
    if status != 200 or not isinstance(deployments, list):
        return "none", "", f"GitHub answered {status} listing deployments"
    previews = [d for d in deployments if "production" not in str(d.get("environment", "")).lower()] or []
    if not previews:
        return "none", "", "no preview deployment is recorded on this commit yet"
    dep = previews[0]
    status, statuses = get(f"/repos/{slug}/deployments/{dep['id']}/statuses?per_page=5")
    latest = statuses[0] if status == 200 and isinstance(statuses, list) and statuses else {}
    state, url = str(latest.get("state", "")), str(latest.get("environment_url") or "")
    note = str(latest.get("description") or "")
    if state == "success" and url:
        return "ready", url, note
    return ("failed" if state in _FAILED else "pending"), url, note or "waiting for Vercel"


def wait_for_preview(slug: str, sha: str, *, wait_s: float, interval_s: float = 15.0, get: Get = github_get,
                     sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> tuple[str, str, str]:
    """Poll until the preview is ``ready`` (or ``failed``) or ``wait_s`` runs out; returns the last (state, url, note)."""
    deadline = clock() + wait_s
    while True:
        got = preview_state(slug, sha, get)
        if got[0] in ("ready", "failed") or clock() >= deadline:
            return got
        sleep(interval_s)
