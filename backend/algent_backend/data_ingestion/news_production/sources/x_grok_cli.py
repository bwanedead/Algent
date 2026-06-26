"""
X discovery via the Grok Build CLI (subscription, headless) — the "free" channel.

xAI ships the Grok Build CLI with a documented headless mode (`-p`) for scripts
and automations, available to SuperGrok / X Premium+ subscribers. We shell out to
it to ask for the X-native significant-conversation picture and ingest its JSON —
so the marginal cost is the subscription quota you already pay for, not a metered
API.

Two isolation guarantees so the CLI can only use *its own* tooling, never ours:
- **Scrubbed environment**: our provider keys (OpenAI/Tavily/Exa/Firecrawl/X/…) are
  stripped from the subprocess env, so a CLI plugin can't spend them (this is what
  bit us when its Firecrawl plugin grabbed our key).
- **Clean working dir**: run from a temp dir with no project `.env` to load.

**Salvage on timeout**: the agentic search is slow and variable, so we tell Grok to
*append each item it finds* to a JSONL file in its cwd as it goes. We then read that
file after the run — so even a run that hits the wall-clock cap returns whatever it
found so far, instead of nothing. The final stdout array is the fallback parse.

The exact binary/flags vary, so the command is configurable via ``ALGENT_X_GROK_CMD``
(default below); we own the prompt and the parsing. Best-effort throughout: any
failure returns an empty list rather than blocking t0.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_CMD_ENV = "ALGENT_X_GROK_CMD"
# `grok -p` = single-turn headless: prints to stdout and exits. --max-turns bounds
# the agentic search. The search can need many tool turns before it composes its
# answer; too few and it hits "max turns reached" empty-handed, so we give it 20.
# Override the whole command via the env var.
_DEFAULT_CMD = "grok --max-turns 20 -p"
# Grok's agentic X/web search runs many turns at ~20-50s each, so it needs a
# generous wall-clock budget. We let it run long (it's worth it for X-native
# signal) — the JSONL salvage below means a near-miss at the cap still yields hits.
_TIMEOUT_S = 600.0
# Grok appends each found item here (in its temp cwd) so we can read partial results.
_FINDINGS_FILE = "x_findings.jsonl"

# Provider credentials the CLI must NOT see (so its plugins can't bill our APIs).
_SCRUB_PREFIXES = ("OPENAI", "ANTHROPIC", "GEMINI", "TAVILY", "EXA", "BRAVE", "FIRECRAWL", "X_")

_PROMPT = (
    "Use ONLY your own built-in X/web search. Do NOT read, load, or use any API "
    "keys, .env files, or external credentials for any part of this task.\n"
    "Goal: surface what is SIGNIFICANT on X right now that mainstream wire services "
    "would miss or be slow on — favor X-native signal over generic headlines:\n"
    "- AI and tech developments (launches, research, model/industry moves)\n"
    "- politics and notable statements by influential people (what they actually said)\n"
    "- significant live conversations and real-time updates on trending events\n"
    "Skip sports scores, memes, and generic celebrity gossip. Substance over virality.\n"
    "As you confirm EACH newsworthy item, immediately append it as a single-line "
    "JSON object to a file named {outfile} in the current directory, then keep "
    "searching for more (aim for up to {limit}). Each appended line must be exactly:\n"
    '{{"topic": "...", "summary": "one sentence", "urls": ["https://..."]}}\n'
    "When finished, also print the full JSON array to stdout."
)


def fetch_x_grok(*, limit: int = 20) -> list[dict[str, Any]]:
    """Ask the Grok CLI for X-native significant topics; returns normalized hits (or [])."""
    cmd = shlex.split(os.environ.get(_CMD_ENV) or _DEFAULT_CMD)
    prompt = _PROMPT.format(limit=limit, outfile=_FINDINGS_FILE)
    with tempfile.TemporaryDirectory() as workdir:
        stdout = ""
        try:
            result = subprocess.run(
                [*cmd, prompt],
                env=_scrubbed_env(),
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
            stdout = result.stdout or ""
        except subprocess.TimeoutExpired as exc:  # salvage whatever it wrote before the cap
            stdout = (exc.stdout if isinstance(exc.stdout, str) else "") or ""
        except OSError:
            return []
        # Prefer the incrementally-written file (survives timeouts); fall back to
        # the final stdout array (read inside the with-block, before cleanup).
        items = _read_findings(Path(workdir) / _FINDINGS_FILE) or _parse_json_array(stdout)
    return _normalize(items, limit)


def _scrubbed_env() -> dict[str, str]:
    """The current env minus our provider keys; keeps PATH/HOME so the CLI runs."""
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.endswith("_API_KEY") or k.startswith(_SCRUB_PREFIXES))
    }


def _read_findings(path: Path) -> list:
    """Read the JSONL salvage file — one item per line, skipping any partial line."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue  # a half-written last line; ignore it
        if isinstance(obj, dict):
            out.append(obj)
    return out


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
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not item.get("topic"):
            continue
        topic = str(item.get("topic", "")).strip()
        if topic.lower() in seen:  # JSONL + stdout can overlap; dedupe by topic
            continue
        seen.add(topic.lower())
        out.append({
            "topic": topic,
            "summary": str(item.get("summary", "")).strip(),
            "urls": [u for u in (item.get("urls") or []) if isinstance(u, str)][:3],
            "source": "x_grok",
        })
        if len(out) >= limit:
            break
    return out
