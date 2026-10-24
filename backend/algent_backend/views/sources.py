"""
Where a view builder reads its inputs: three narrow doors, each swappable in tests.

* ``Staged``  the documents the publishers stage for the site (``content/intel/**``: dailies, dossiers, actor pages, the snapshot, briefs, the record;
              ``public/data/**``: the agent feeds). The server reads its own files; nothing is read back from the bucket.
* ``Tables``  the table-shaped products' documents (sanctions, calendar, geoledger, live anomalies, the track record), built by each domain's own
              ``documents()`` function on first use and cached for the run. A builder that needs none of them never pays for them.
* ``Corpus``  the SQLite index (``corpus.Corpus``), or None when no index has been built: the builders that need it degrade to what the staged
              documents hold.

A document path is the path the site reads (``daily/geopolitics/2026-10-01.json``, ``theaters/index.json``, ``data/forecasts.json``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any


class Staged:
    """Documents by path, read lazily and parsed once. Subclasses supply ``_names`` and ``_read``."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def names(self, directory: str) -> list[str]:
        """File names (not paths) directly inside ``directory``, sorted."""
        raise NotImplementedError

    def _read(self, path: str) -> Any:
        raise NotImplementedError

    def get(self, path: str, *, keep: bool = True) -> Any:
        """The parsed document, or None. ``keep=False`` reads without remembering it: a pass over hundreds of dailies must not hold them all."""
        if path in self._cache:
            return self._cache[path]
        try:
            doc = self._read(path)
        except (OSError, ValueError):
            doc = None
        if keep:
            self._cache[path] = doc
        return doc

    def slugs(self, directory: str) -> list[str]:
        return sorted(n[:-5] for n in self.names(directory) if n.endswith(".json"))


class DictStaged(Staged):
    """An in-memory tree (tests, and ``rebuild.site_documents`` output)."""

    def __init__(self, docs: Mapping[str, Any]) -> None:
        super().__init__()
        self.docs = dict(docs)

    def names(self, directory: str) -> list[str]:
        cut = len(directory) + 1
        return sorted({p[cut:] for p in self.docs if p.startswith(directory + "/") and "/" not in p[cut:]})

    def _read(self, path: str) -> Any:
        return self.docs.get(path)


class TreeStaged(Staged):
    """The site checkout(s) on disk. The first root that has a file wins (the publish worktree is newer than the repo copy)."""

    def __init__(self, roots: Iterable[Path]) -> None:
        super().__init__()
        self.roots = [Path(r) for r in roots]

    @staticmethod
    def _locate(root: Path, path: str) -> Path:
        return root / "public" / "data" / path[5:] if path.startswith("data/") else root / "content" / "intel" / path

    def names(self, directory: str) -> list[str]:
        out: set[str] = set()
        for root in self.roots:
            folder = self._locate(root, directory)
            if folder.is_dir():
                out.update(p.name for p in folder.iterdir() if p.is_file())
        return sorted(out)

    def _read(self, path: str) -> Any:
        for root in self.roots:
            f = self._locate(root, path)
            if f.is_file():
                return json.loads(f.read_text(encoding="utf-8"))
        return None


class Tables:
    """Documents of the table-shaped products, by the path the site reads. ``builders`` are zero-argument functions returning ``{path: body}``;
    the one that answers for a path prefix runs once per context."""

    def __init__(self, builders: Mapping[str, Callable[[], dict[str, Any]]] | None = None, docs: Mapping[str, Any] | None = None) -> None:
        self.builders = dict(builders or {})
        self._docs: dict[str, Any] = dict(docs or {})
        self._ran: set[str] = set()

    def get(self, path: str) -> Any:
        if path in self._docs:
            return self._docs[path]
        for prefix, build in self.builders.items():
            if path.startswith(prefix) and prefix not in self._ran:
                self._ran.add(prefix)
                try:
                    self._docs.update(build())
                except Exception as exc:  # noqa: BLE001 - a product that cannot build leaves its views without that block, never the whole build
                    print(f"[views] {prefix} not built: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
        return self._docs.get(path)


def default_tables() -> Tables:
    """The production wiring: each prefix is answered by the owning domain's document builder (the one its publisher already uses)."""
    def sanctions() -> dict[str, Any]:
        from algent_backend.sanctions import publish
        return publish.documents()

    def calendar() -> dict[str, Any]:
        from algent_backend.lookahead import publish
        return publish.documents()

    def places() -> dict[str, Any]:
        from algent_backend.geoledger import site_docs
        return site_docs.documents()

    def grid() -> dict[str, Any]:
        from datetime import UTC, datetime

        from algent_backend.geoledger import grid as g
        led, as_of = g.cached_ledger(), datetime.now(UTC).date().isoformat()
        return {f"geo/grid/{iso}.json": g.rollup(led, iso, as_of) for iso in g.countries_with_events(led, as_of)}

    def anomalies() -> dict[str, Any]:
        from algent_backend.live.memory import anomalies as a
        return {"live/anomalies.json": {"anomalies": [{**x.model_dump(), "active": x.active} for x in a.read_current()]}}

    def track() -> dict[str, Any]:
        from algent_backend.markets import score
        return {"data/track-record.json": score.track_record()}

    return Tables({"sanctions/": sanctions, "calendar/": calendar, "geo/a/": places, "geo/grid/": grid, "live/anomalies": anomalies,
                   "data/track-record": track})
