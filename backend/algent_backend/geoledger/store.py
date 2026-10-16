"""
The ledger on disk: two append-only JSONL files and an in-memory view.

    <root>/assets.jsonl    one line per asset REVISION (a new alias, a corrected position is a new line; the last wins)
    <root>/events.jsonl    one line per status event; never rewritten, a repeated id is ignored
    <root>/merges.jsonl    one line per "this asset is that asset" decision (``merge``); nothing else is touched, the
                           view maps the duplicate onto its target and keeps every line of its history
    <root>/published.json  how many lines of each file the site database already has (``publish``)
    <root>/cache/          raw answers of free data services (Overpass), so a rerun costs nobody anything

Root: ``ALGENT_GEOLEDGER_STORE`` or ``geoledger_store``. History is the record: nothing here edits or deletes a line, and
the current state of an asset (its latest event) is derived on read.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .alias import unit_keys
from .contracts import Asset, StatusEvent, fold, latest
from .match import tokens

_ENV = "ALGENT_GEOLEDGER_STORE"
_DEFAULT = "geoledger_store"
_PREFIX = 3                 # candidate lookup keys a name by the first letters of its words, so spelling variants meet


def root() -> Path:
    return Path(os.environ.get(_ENV) or _DEFAULT)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _lines(path: Path) -> list[str]:
    try:
        return [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []


def _append(path: Path, rows: Iterable[str]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(rows) + "\n")


def _same(a: Asset, b: Asset) -> bool:
    return a.model_dump(exclude={"recorded_at"}) == b.model_dump(exclude={"recorded_at"})


class Ledger:
    """The current view of the ledger (loaded once), with append methods that write through to disk."""

    def __init__(self, base: Path | None = None) -> None:
        self.base = base or root()
        self.assets: dict[str, Asset] = {}
        self.events: dict[str, StatusEvent] = {}
        self.by_asset: dict[str, list[StatusEvent]] = {}       # keyed by CANONICAL asset id (a merged duplicate's events live under its target)
        self.merged: dict[str, str] = {}                       # duplicate id -> the id it was merged into
        self._claims: set[tuple[str, str, str, str]] = set()   # (asset, day, status, claimant): one claim, one event
        self._units: dict[tuple[str, str, str], set[str]] = {}  # (country, plant kind, unit number) -> power plant ids
        self._keys: dict[str, dict[str, set[str]]] = {}        # word prefix -> country -> asset ids
        for line in _lines(self.base / "assets.jsonl"):
            try:
                self._put(Asset.model_validate_json(line))
            except ValueError:
                continue                                       # a torn line must not hide the rest
        for line in _lines(self.base / "merges.jsonl"):
            try:
                m = json.loads(line)
                self.merged[str(m["dup"])] = str(m["into"])
            except (ValueError, KeyError):
                continue
        for line in _lines(self.base / "events.jsonl"):
            try:
                self._note(StatusEvent.model_validate_json(line))
            except ValueError:
                continue

    # -- in-memory ---------------------------------------------------------------------------
    def _put(self, a: Asset) -> None:
        self.assets[a.id] = a
        for name in (a.name, *a.aliases):
            for w in tokens(name)[0]:
                self._keys.setdefault(w[:_PREFIX], {}).setdefault(a.country, set()).add(a.id)
        for cls, num in unit_keys(a):
            self._units.setdefault((a.country, cls, num), set()).add(a.id)

    def _note(self, e: StatusEvent) -> bool:
        key = self._claim_key(e)
        if e.id in self.events or key in self._claims:
            return False
        self.events[e.id] = e
        self._claims.add(key)
        self.by_asset.setdefault(self.canonical(e.asset_id), []).append(e)
        return True

    def _claim_key(self, e: StatusEvent) -> tuple[str, str, str, str]:
        return (self.canonical(e.asset_id), e.occurred_on, e.status, " ".join(fold(e.claimant).split()))

    def canonical(self, asset_id: str) -> str:
        """The asset an id stands for now: itself, or where a merge sent it (followed to the end)."""
        seen = {asset_id}
        while (nxt := self.merged.get(asset_id)) is not None and nxt not in seen:
            asset_id = nxt
            seen.add(nxt)
        return asset_id

    def live(self) -> list[Asset]:
        """The assets in play: every one that has not been merged into another."""
        return [a for i, a in self.assets.items() if i not in self.merged]

    # -- writes ------------------------------------------------------------------------------
    def add_assets(self, assets: Iterable[Asset]) -> int:
        """Append a revision for each asset that is new or differs from its current revision; returns how many."""
        rows = []
        for a in assets:
            old = self.assets.get(a.id)
            if old is not None and _same(old, a):
                continue
            a = a.model_copy(update={"recorded_at": a.recorded_at or now_iso()})
            self._put(a)
            rows.append(a.model_dump_json())
        _append(self.base / "assets.jsonl", rows)
        return len(rows)

    def add_events(self, events: Iterable[StatusEvent]) -> int:
        """Append the events not already on file (by id); an event for an asset the ledger lacks is refused."""
        rows = []
        for e in events:
            if e.asset_id not in self.assets or e.id in self.events:
                continue
            e = e.model_copy(update={"observed_at": e.observed_at or now_iso(), "asset_id": self.canonical(e.asset_id)})
            if self._note(e):
                rows.append(e.model_dump_json())
        _append(self.base / "events.jsonl", rows)
        return len(rows)

    # -- reads -------------------------------------------------------------------------------
    def history(self, asset_id: str) -> list[StatusEvent]:
        """Every event of an asset, oldest first."""
        return sorted(self.by_asset.get(self.canonical(asset_id), []), key=lambda e: (e.occurred_on, e.occurred_at, e.observed_at))

    def status(self, asset_id: str) -> StatusEvent | None:
        return latest(self.by_asset.get(self.canonical(asset_id), []))

    def candidates(self, words: set[str], country: str = "") -> list[Asset]:
        """Assets with a name word that starts like one of ``words`` (country-matched, or country-less on either side)."""
        ids: set[str] = set()
        for prefix in {w[:_PREFIX] for w in words}:
            for c, found in self._keys.get(prefix, {}).items():
                if not country or not c or c == country:
                    ids |= found
        return [self.assets[i] for i in sorted(ids) if i not in self.merged]

    def by_unit(self, country: str, cls: str, num: str) -> list[Asset]:
        """Power plants of a country whose name carries this kind and unit number ("CHP-5"), merged duplicates left out."""
        return [self.assets[i] for i in sorted(self._units.get((country, cls, num), ())) if i not in self.merged]

    def in_bbox(self, west: float, south: float, east: float, north: float, types: Iterable[str] | None = None) -> list[Asset]:
        want = set(types) if types else None
        return [a for a in self.live()
                if a.lat is not None and a.lon is not None and south <= a.lat <= north and west <= a.lon <= east
                and (want is None or a.type in want)]

    def near(self, lat: float, lon: float, km: float, type_: str | None = None) -> list[Asset]:
        from .match import km_between

        return [a for a in self.live()
                if a.lat is not None and a.lon is not None and (type_ is None or a.type == type_)
                and abs(a.lat - lat) <= km / 100.0 and km_between((lat, lon), (a.lat, a.lon)) <= km]

    def counts(self) -> dict[str, int]:
        types: dict[str, int] = {}
        for a in self.live():
            types[a.type] = types.get(a.type, 0) + 1
        return {"assets": len(self.assets) - len(self.merged), "merged": len(self.merged), "events": len(self.events),
                "assets_with_events": len(self.by_asset), **{f"type:{k}": v for k, v in sorted(types.items())}}


    # -- merging -----------------------------------------------------------------------------
    def merge(self, dup: str, into: str, *, by: str = "cli", note: str = "") -> dict:
        """Record that asset ``dup`` is the same place as ``into``. Nothing is deleted or rewritten: the duplicate keeps its
        lines and events on file, the view reads them under the target, and the target gains the duplicate's names (a new
        revision) and any attribute it lacked. Raises ValueError when the merge makes no sense."""
        if dup not in self.assets or into not in self.assets:
            raise ValueError(f"unknown asset {dup if dup not in self.assets else into!r}")
        target = self.canonical(into)
        if dup in self.merged:
            raise ValueError(f"{dup} is already merged into {self.merged[dup]}")
        if target == dup:
            raise ValueError(f"{into} is already {dup} (it was merged into it, or they are the same asset)")
        a, b = self.assets[target], self.assets[dup]
        names = [n for n in dict.fromkeys([*a.aliases, b.name, *b.aliases]) if fold(n) != fold(a.name)]
        attrs = {**{k: v for k, v in b.attrs.items() if k not in a.attrs}, **a.attrs}
        self.add_assets([a.model_copy(update={"aliases": names[:10], "attrs": attrs})])
        moved = self.by_asset.pop(dup, [])
        row = {"dup": dup, "into": target, "at": now_iso(), "by": by, "note": note[:240], "events_moved": len(moved)}
        _append(self.base / "merges.jsonl", [json.dumps(row, ensure_ascii=False)])
        self.merged[dup] = target
        self.by_asset.setdefault(target, []).extend(moved)
        for k, v in list(self.merged.items()):                  # anything that pointed at the duplicate now points at the target
            if v == dup:
                self.merged[k] = target
        return row


# -- publish watermark -------------------------------------------------------------------------
def line_counts(base: Path | None = None) -> dict[str, int]:
    b = base or root()
    return {n: len(_lines(b / f"{n}.jsonl")) for n in ("assets", "events", "merges")}


def load_marker(base: Path | None = None) -> dict[str, int]:
    try:
        raw = json.loads(((base or root()) / "published.json").read_text(encoding="utf-8"))
        return {n: int(raw.get(n, 0)) for n in ("assets", "events", "merges")}
    except (OSError, ValueError):
        return {"assets": 0, "events": 0, "merges": 0}


def save_marker(marker: dict[str, int], base: Path | None = None) -> None:
    path = (base or root()) / "published.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker), encoding="utf-8")


def lines_after(name: str, offset: int, base: Path | None = None) -> list[str]:
    """The raw lines of ``assets`` / ``events`` / ``merges`` written after the first ``offset`` (what the database lacks)."""
    return _lines((base or root()) / f"{name}.jsonl")[offset:]
