"""
Names and ids, deterministically. Every id in the index is a pure function of source ids, so a rebuild reproduces them exactly.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

_NON_WORD = re.compile(r"[^a-z0-9]+")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def norm(text: Any) -> str:
    """The comparison form of a name: case-folded, accent-stripped, punctuation to single spaces."""
    t = unicodedata.normalize("NFKD", str(text or "")).casefold().replace("’", "'")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", t).strip()


def slug(text: Any, *, limit: int = 60) -> str:
    return norm(text).replace(" ", "-")[:limit].strip("-") or "unnamed"


def digest(*parts: Any, size: int = 12) -> str:
    """A short stable hash of any JSON-able parts."""
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:size]


def day(text: Any) -> str:
    """``YYYY-MM-DD`` from an ISO date or timestamp, else ``""``."""
    m = _DATE.match(str(text or ""))
    return m.group(0) if m else ""


def clip(text: Any, n: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def domain_of(url: str) -> str:
    m = re.match(r"^[a-z][a-z0-9+.-]*://([^/:?#]+)", (url or "").strip(), re.I)
    return m.group(1).lower().removeprefix("www.") if m else ""
