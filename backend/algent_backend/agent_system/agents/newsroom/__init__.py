"""
Newsroom editorial doctrine — the spirit + craft markdown surfaces, loadable into
production-agent prompts.

`doctrine("spirit")` returns the text of `spirit.md`, etc. Production agents compose
these as prompt layers (after the universal base + newsroom map), so the editorial
spirit and craft embed into every agent that touches public-facing meaning. The .md
files are the source of truth; this just loads them.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@cache
def doctrine(name: str) -> str:
    """Load an editorial doctrine file by stem (e.g. 'spirit', 'writing-ergonomics')."""
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")
