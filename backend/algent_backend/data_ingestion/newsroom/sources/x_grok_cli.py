"""
X discovery via the Grok Build CLI (subscription, headless) — **optional supplement only**.

Primary t0 X is the native X API (``x_native`` / same surface as ``api.x.com/mcp``).
This module remains for ``ALGENT_X_T0_VIA=api+grok`` or ``grok`` when you want an
extra LLM-curated pass — not the default discovery path.

xAI ships the Grok Build CLI with a documented headless mode (`-p`) for scripts
and automations, available to SuperGrok / X Premium+ subscribers. We shell out to
it to ask for the X-native significant-conversation picture and ingest its JSON —
so the marginal cost is the subscription quota you already pay for, not a metered
API.

**Lane fan-out**: one generalist instance spreads its turn budget thin across every
topic. Instead we run one focused instance *per direction* (ai, tech, politics, mma,
…), in parallel — each spends its whole budget going deep on its lane, and every hit
is tagged with the lane it came from. Lanes are configurable via ``ALGENT_X_GROK_LANES``.

Two isolation guarantees so the CLI can only use *its own* tooling, never ours:
- **Scrubbed environment**: our provider keys (OpenAI/Tavily/Exa/Firecrawl/X/…) are
  stripped from the subprocess env, so a CLI plugin can't spend them (this is what
  bit us when its Firecrawl plugin grabbed our key).
- **Clean working dir**: each lane runs from its own temp dir with no project `.env`.

**Salvage on timeout**: the agentic search is slow and variable, so we tell Grok to
*append each item it finds* to a JSONL file in its cwd as it goes. We read that file
after the run — so even a lane that hits the wall-clock cap returns whatever it found,
instead of nothing. The final stdout array is the fallback parse.

Best-effort throughout: any lane's failure returns no items for that lane rather than
blocking the others or t0.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from algent_backend.agent_system.runs.control_plane.process_tree import run_capturing

_CMD_ENV = "ALGENT_X_GROK_CMD"
_LANES_ENV = "ALGENT_X_GROK_LANES"  # comma list, e.g. "ai,mma" — overrides defaults
_CONCURRENCY_ENV = "ALGENT_X_GROK_CONCURRENCY"  # max lanes to run at once

# `grok -p` = single-turn headless: prints to stdout and exits. --max-turns bounds
# the agentic search; per *lane* (one focused topic) this is a generous ceiling,
# not a target. Override the whole command via the env var.
_DEFAULT_CMD = "grok --max-turns 20 -p"
# Per-lane wall-clock budget. The search is worth running long; the JSONL salvage
# below means a near-miss at the cap still yields hits. Lanes run in parallel, so
# total time is ~the slowest wave, not the sum.
_TIMEOUT_S = 600.0
_DEFAULT_CONCURRENCY = 3  # be polite to the subscription; tunable via env
_FINDINGS_FILE = "x_findings.jsonl"  # Grok appends each item here (in its temp cwd)

# Provider credentials the CLI must NOT see (so its plugins can't bill our APIs).
_SCRUB_PREFIXES = ("OPENAI", "ANTHROPIC", "GEMINI", "TAVILY", "EXA", "BRAVE", "FIRECRAWL", "X_")

# Search directions. Each becomes one focused headless instance. Add/trim freely;
# select per run via ALGENT_X_GROK_LANES. Defaults cover the high-value lanes.
_LANE_FOCUS = {
    "ai": "AI developments: model/product launches, research, lab and industry moves, "
          "and notable statements by influential AI figures.",
    "tech": "technology and startups beyond AI: product launches, funding rounds, "
            "big-tech strategy, and engineering/security news.",
    "politics": "politics and policy: significant developments and notable statements "
                "by influential political figures (what they actually said).",
    "discussions": "significant live conversations and discourse trending on X right "
                   "now that could become news.",
    "gaming": "video game and gaming-industry news: releases, studio/publisher moves, "
              "major patches, esports, and significant community developments.",
    "mma": "UFC and MMA world news: fight announcements and bookings, results and "
           "finishes, fighter news and injuries, and promotion (UFC/PFL/ONE) developments.",
    "misc": "significant breaking or trending items not covered by the other lanes.",
}
_DEFAULT_LANES = ("ai", "tech", "politics", "mma")

_BASE_PROMPT = (
    "Use ONLY your own built-in X/web search. Do NOT read, load, or use any API "
    "keys, .env files, or external credentials for any part of this task.\n"
    "Focus area: {focus}\n"
    "Surface what is SIGNIFICANT on X right now within this focus area — favor "
    "X-native signal that mainstream wire services miss or are slow on. Skip memes "
    "and generic gossip; substance over virality.\n"
    "As you confirm EACH newsworthy item, immediately append it as a single-line "
    "JSON object to a file named {outfile} in the current directory, then keep "
    "searching for more (aim for up to {limit}). Each appended line must be exactly:\n"
    '{{"topic": "...", "summary": "one sentence", "urls": ["https://..."]}}\n'
    "When finished, also print the full JSON array to stdout."
)


def fetch_x_grok(
    *, limit: int = 6, lanes: tuple[str, ...] | None = None, max_workers: int | None = None,
) -> list[dict[str, Any]]:
    """Fan out one focused Grok instance per lane; merge, dedupe, and return hits.

    ``limit`` is the per-lane cap. Each hit carries the ``lane`` it came from.
    """
    chosen = resolve_lanes(lanes)
    workers = max_workers or _concurrency()
    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_lane, lane, limit): lane for lane in chosen}
        for future in as_completed(futures):
            try:
                collected.extend(future.result())
            except Exception:  # noqa: BLE001 — a lane crashing must not sink the rest
                continue
    return _dedupe(collected)


def resolve_lanes(lanes: tuple[str, ...] | None) -> tuple[str, ...]:
    """Pick active lanes: explicit arg → ``ALGENT_X_GROK_LANES`` → defaults."""
    if lanes is not None:
        picked = [lane.strip().lower() for lane in lanes if lane.strip()]
    else:
        env = os.environ.get(_LANES_ENV, "")
        picked = [lane.strip().lower() for lane in env.split(",") if lane.strip()] if env else list(_DEFAULT_LANES)
    valid = tuple(lane for lane in picked if lane in _LANE_FOCUS)
    return valid or _DEFAULT_LANES


def _concurrency() -> int:
    try:
        return max(1, int(os.environ.get(_CONCURRENCY_ENV, _DEFAULT_CONCURRENCY)))
    except ValueError:
        return _DEFAULT_CONCURRENCY


def _run_lane(lane: str, limit: int) -> list[dict[str, Any]]:
    """Run one headless Grok instance scoped to ``lane``; return its tagged hits."""
    cmd = shlex.split(os.environ.get(_CMD_ENV) or _DEFAULT_CMD)
    prompt = _BASE_PROMPT.format(focus=_LANE_FOCUS[lane], limit=limit, outfile=_FINDINGS_FILE)
    with tempfile.TemporaryDirectory() as workdir:
        stdout = ""
        try:
            result = run_capturing(
                [*cmd, prompt],
                env=_scrubbed_env(),
                cwd=workdir,
                timeout=_TIMEOUT_S,
            )
            stdout = result.stdout or ""
        except subprocess.TimeoutExpired as exc:  # salvage whatever it wrote before the cap
            stdout = (exc.stdout if isinstance(exc.stdout, str) else "") or ""
        except OSError:
            return []
        # Prefer the incrementally-written file (survives timeouts); fall back to the
        # final stdout array (read inside the with-block, before cleanup).
        items = _read_findings(Path(workdir) / _FINDINGS_FILE) or _parse_json_array(stdout)
    return _normalize(items, limit, lane)


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


def _normalize(items: list, limit: int, lane: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not item.get("topic"):
            continue
        topic = str(item.get("topic", "")).strip()
        if topic.lower() in seen:  # JSONL + stdout can overlap within a lane
            continue
        seen.add(topic.lower())
        out.append({
            "topic": topic,
            "summary": str(item.get("summary", "")).strip(),
            "urls": [u for u in (item.get("urls") or []) if isinstance(u, str)][:3],
            "lane": lane,
            "source": "x_grok",
        })
        if len(out) >= limit:
            break
    return out


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop topics that recur across lanes (keep the first lane that found it)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = item.get("topic", "").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
