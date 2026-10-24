"""
What a source adapter is. An adapter reads ONE registered product's store through that product's own reader functions (never by re-parsing a
format here) and offers it as *units*: the smallest piece that can change independently (a daily file, a profile, a ledger line).

``fingerprint`` of a unit is a content hash; an unchanged unit is skipped without being written. ``watermark`` of the whole source is a cheap
stat-based mark (sizes and mtimes) so an untouched store is not even read. Both are only optimisations: ``--full`` ignores them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..sink import Sink


@dataclass(frozen=True)
class Unit:
    key: str                                  # stable and unique across sources, e.g. ``daily:geopolitics:2026-10-05``
    fingerprint: str                          # changes iff the unit's content changed
    emit: Callable[[Sink], None]              # writes the unit through the sink
    date: str = ""                            # YYYY-MM-DD when dated: ``--since`` skips units older than it
    path: str = ""                            # where in the store it came from (provenance for people)


@dataclass(frozen=True)
class Source:
    name: str                                 # adapter name, the unit-key prefix owner and the ``--only`` selector
    product: str                              # registry product id (``ops/products/registry.py``)
    units: Callable[[], Iterable[Unit]]
    watermark: Callable[[], str] = lambda: ""  # cheap "has anything changed" mark; "" = unknown, always scan


def digest_of(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def file_digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:16]


def mark(paths: Iterable[Path]) -> str:
    """A stat-based mark of files and directories: changes when any listed path changes size or mtime, or appears or disappears."""
    parts = []
    for p in sorted(paths):
        try:
            st = p.stat()
            parts.append(f"{p.name}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{p.name}:-")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def tree_mark(root: Path, pattern: str) -> str:
    """``mark`` over every file under ``root`` matching ``pattern`` (recursive glob)."""
    return mark(root.rglob(pattern)) if root.is_dir() else ""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def files(root: Path, pattern: str = "*.json") -> Iterator[Path]:
    yield from sorted(root.glob(pattern)) if root.is_dir() else ()
