"""
Operator-controlled topic freeze — hard block for 1-at-a-time dev rails.

Reads ``topic_freeze.md`` next to this module. Lines starting with ``-`` / ``*``
are case-insensitive substring matchers against vector text. Matching vectors
cannot promote (forced cooldown) until the operator deletes the line.

Disable: ``ALGENT_TOPIC_FREEZE=0``.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

_ENV = "ALGENT_TOPIC_FREEZE"
_FREEZE_FILE = Path(__file__).with_name("topic_freeze.md")
_BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


def freeze_enabled() -> bool:
    return os.environ.get(_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def freeze_file_path() -> Path:
    return _FREEZE_FILE


@lru_cache(maxsize=1)
def load_freeze_phrases() -> tuple[str, ...]:
    """Frozen topic phrases from the md file (lowercased). Empty if disabled/missing."""
    if not freeze_enabled():
        return ()
    path = freeze_file_path()
    if not path.is_file():
        return ()
    out: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        m = _BULLET.match(line)
        if not m:
            continue
        phrase = m.group(1).strip().lower()
        # strip trailing markdown emphasis / comments
        phrase = phrase.split("#", 1)[0].strip().strip("*_`")
        if len(phrase) >= 3:
            out.append(phrase)
    return tuple(out)


def clear_freeze_cache() -> None:
    """Tests / after editing the md in-process."""
    load_freeze_phrases.cache_clear()


def match_freeze(text: str, phrases: tuple[str, ...] | None = None) -> str | None:
    """Return the first freeze phrase that hits ``text``, else None."""
    phrases = phrases if phrases is not None else load_freeze_phrases()
    if not phrases or not text:
        return None
    blob = text.casefold()
    for p in phrases:
        if p.casefold() in blob:
            return p
    return None


def freeze_lines_for_prompt() -> list[str]:
    """Human-readable freeze list for agent payloads."""
    return [f"- {p}" for p in load_freeze_phrases()]
