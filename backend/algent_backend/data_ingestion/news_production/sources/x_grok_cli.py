"""
X discovery via the Grok Build CLI (subscription, headless) — the "free" channel.

xAI ships the Grok Build CLI with a documented headless mode (`-p`) for scripts
and automations, available to SuperGrok / X Premium+ subscribers. We shell out to
it to ask for the broad X trending/breaking picture and ingest its JSON — so the
marginal cost is the subscription quota you already pay for, not a metered API.

Two isolation guarantees so the CLI can only use *its own* tooling, never ours:
- **Scrubbed environment**: our provider keys (OpenAI/Tavily/Exa/Firecrawl/X/…) are
  stripped from the subprocess env, so a CLI plugin can't spend them (this is what
  bit us when its Firecrawl plugin grabbed our key).
- **Clean working dir**: run from a temp dir with no project `.env` to load.

The exact binary/flags vary, so the command is configurable via ``ALGENT_X_GROK_CMD``
(default ``grok -p``); we own the prompt and the parsing. Best-effort: any failure
returns an empty list rather than blocking t0.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from typing import Any

_CMD_ENV = "ALGENT_X_GROK_CMD"
# `grok -p` = single-turn headless: prints to stdout and exits. --max-turns bounds
# the agentic X search so it can't loop. Override the whole command via the env var.
_DEFAULT_CMD = "grok --max-turns 8 -p"
# Grok's agentic X/web search runs ~8 turns at ~20-50s each, so it needs a generous
# wall-clock budget; 150s clipped it mid-search. 240s absorbs the run-to-run variance.
_TIMEOUT_S = 240.0

# Provider credentials the CLI must NOT see (so its plugins can't bill our APIs).
_SCRUB_PREFIXES = ("OPENAI", "ANTHROPIC", "GEMINI", "TAVILY", "EXA", "BRAVE", "FIRECRAWL", "X_")

_PROMPT = (
    "Search X for the top trending and breaking NEWS topics right now (not sports "
    "scores or memes). Return ONLY a JSON array, no prose, of up to {limit} items: "
    '[{{"topic": "...", "summary": "one sentence", "urls": ["https://..."]}}]'
)


def fetch_x_grok(*, limit: int = 20) -> list[dict[str, Any]]:
    """Ask the Grok CLI for X trending news; returns normalized hits (or [])."""
    cmd = shlex.split(os.environ.get(_CMD_ENV) or _DEFAULT_CMD)
    prompt = _PROMPT.format(limit=limit)
    try:
        with tempfile.TemporaryDirectory() as workdir:
            result = subprocess.run(
                [*cmd, prompt],
                env=_scrubbed_env(),
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return []
    return _normalize(_parse_json_array(result.stdout), limit)


def _scrubbed_env() -> dict[str, str]:
    """The current env minus our provider keys; keeps PATH/HOME so the CLI runs."""
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.endswith("_API_KEY") or k.startswith(_SCRUB_PREFIXES))
    }


def _parse_json_array(text: str) -> list:
    """Extract the JSON array from CLI stdout, tolerating markdown fences/prose."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _normalize(items: list, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("topic"):
            continue
        out.append({
            "topic": str(item.get("topic", "")).strip(),
            "summary": str(item.get("summary", "")).strip(),
            "urls": [u for u in (item.get("urls") or []) if isinstance(u, str)][:3],
            "source": "x_grok",
        })
        if len(out) >= limit:
            break
    return out
