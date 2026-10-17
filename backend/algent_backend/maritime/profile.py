"""
The profile book — a compact, bounded, persisted memory of each vessel (keyed by MMSI) over the last few days.

Per vessel: identity as broadcast (name, IMO, ship type) with the changes seen, the last position / speed / time heard, and a thin
position history (at most one sample an hour, a vessel that sits still keeps ONE sample). Beside the profiles the book keeps the
ACTIVITY of places: hourly counts of underway vessels per 1-degree cell, which is how the gap detector tells a vessel that went
silent in busy, still-heard water from a place that simply lost its receiver.

Bounds: profiles expire ``PROFILE_KEEP_S`` after last heard and never exceed ``PROFILE_MAX`` (freshest kept); samples are capped per
vessel; activity older than ``ACTIVITY_KEEP_H`` is dropped. Persisted as gzip JSON (atomic replace); activity is rebuilt from the samples
on load. The book is written on the stream loop thread only; readers (the detectors) run on that thread too.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import unicodedata
from array import array
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from . import flags
from .geomath import cell_id, km_between

_E4 = 10000
MOVING_KN = 0.5
_NON_NAME = re.compile(r"[^A-Z0-9 ]+")


# ── identity helpers (pure) ──────────────────────────────────────────────────────────────────────
def fold_name(name: str) -> str:
    """Upper-case, accent-free, punctuation-free, single-spaced: the form names are compared in."""
    text = "".join(c for c in unicodedata.normalize("NFKD", name or "") if not unicodedata.combining(c)).upper()
    return " ".join(_NON_NAME.sub(" ", text).split())


def same_name(a: str, b: str) -> bool:
    """True when two broadcast names are the same ship's (truncation, a mistyped letter) - or too short to compare."""
    na, nb = fold_name(a), fold_name(b)
    if len(na) < flags.NAME_MIN_CHARS or len(nb) < flags.NAME_MIN_CHARS:
        return True
    if na.startswith(nb) or nb.startswith(na):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= flags.NAME_SAME_RATIO


def clean_imo(raw: Any) -> str:
    """The IMO number as 7 digits ('' when absent, zero or malformed)."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("IMO"):
        digits = digits[3:]
    return digits if len(digits) == 7 and digits != "0000000" else ""


def imo_valid(imo: str) -> bool:
    """IMO check digit: the last digit equals the sum of the first six, weighted 7..2, modulo 10."""
    return len(imo) == 7 and imo.isdigit() and sum(int(d) * w for d, w in zip(imo[:6], range(7, 1, -1))) % 10 == int(imo[6])


def plausible_mmsi(mmsi: int) -> bool:
    """A ship station: nine digits starting 2-7 (coast stations, aids to navigation, SAR craft and test ids are not vessels)."""
    s = str(mmsi)
    return len(s) == 9 and s[0] in "234567"


# ── one vessel ───────────────────────────────────────────────────────────────────────────────────
class Profile:
    __slots__ = ("mmsi", "imo", "name", "ship_type", "first", "last", "lat", "lon", "sog", "samples", "changes")

    def __init__(self, mmsi: int, first: float) -> None:
        self.mmsi, self.first = mmsi, first
        self.imo, self.name, self.ship_type = "", "", 0
        self.last, self.lat, self.lon, self.sog = 0.0, 0.0, 0.0, -1.0
        self.samples = array("i")                      # rows of (ts, lat e4, lon e4, speed tenths of a knot; -10 unknown)
        self.changes: list[list[Any]] = []             # [ts, "name" | "imo" | "type", old, new]

    def points(self) -> list[tuple[int, float, float, float]]:
        """(ts, lat, lon, sog) oldest first."""
        a = self.samples
        return [(a[i], a[i + 1] / _E4, a[i + 2] / _E4, a[i + 3] / 10) for i in range(0, len(a), 4)]

    def to_json(self) -> list[Any]:
        return [self.imo, self.name, self.ship_type, int(self.first), int(self.last), round(self.lat, 4), round(self.lon, 4), round(self.sog, 1),
                list(self.samples), self.changes]

    @classmethod
    def from_json(cls, mmsi: int, row: list[Any]) -> "Profile":
        p = cls(mmsi, float(row[3]))
        p.imo, p.name, p.ship_type = str(row[0]), str(row[1]), int(row[2])
        p.last, p.lat, p.lon, p.sog = float(row[4]), float(row[5]), float(row[6]), float(row[7])
        p.samples = array("i", (int(x) for x in row[8]))
        p.changes = [list(c) for c in row[9]]
        return p


# ── the book ─────────────────────────────────────────────────────────────────────────────────────
class ProfileBook:
    def __init__(self) -> None:
        self.profiles: dict[int, Profile] = {}
        self.activity: dict[tuple[int, int], int] = {}          # (cell id, hour index) -> underway samples
        self.by_imo: dict[str, set[int]] = {}

    def get(self, mmsi: int) -> Profile | None:
        return self.profiles.get(mmsi)

    def _profile(self, mmsi: int, ts: float) -> Profile | None:
        p = self.profiles.get(mmsi)
        if p is None:
            if not plausible_mmsi(mmsi):
                return None
            p = self.profiles[mmsi] = Profile(mmsi, ts)
        return p

    # ── identity (from static messages / names carried on position messages) ───────────────────
    def identity(self, mmsi: int, name: Any, imo: Any, ship_type: Any, ts: float) -> None:
        """Merge broadcast identity into the profile and record changes. An absent field never erases a known one."""
        nm = (name or "").strip()[:24] if isinstance(name, str) else ""
        imo_s = clean_imo(imo)
        typ = ship_type if isinstance(ship_type, int) and ship_type > 0 else 0
        p = self.profiles.get(mmsi)
        if p is not None and (not nm or nm == p.name) and (not imo_s or imo_s == p.imo) and (not typ or typ == p.ship_type):
            return                                               # the common case: nothing new
        p = self._profile(mmsi, ts)
        if p is None:
            return
        if nm:
            if not p.name:
                p.name = nm
            elif not same_name(p.name, nm):
                self._change(p, ts, "name", p.name, nm)
                p.name = nm
            elif len(nm) > len(p.name) and fold_name(nm).startswith(fold_name(p.name)):
                p.name = nm                                      # a fuller form of the same name
        if imo_s and imo_s != p.imo:
            if p.imo:
                self._change(p, ts, "imo", p.imo, imo_s)
                self.by_imo.get(p.imo, set()).discard(mmsi)
            p.imo = imo_s
            self.by_imo.setdefault(imo_s, set()).add(mmsi)
        if typ and typ != p.ship_type:
            if p.ship_type and (p.ship_type // 10) != (typ // 10):   # a different family of ship, not a Class B part A/B difference
                self._change(p, ts, "type", p.ship_type, typ)
            p.ship_type = typ

    @staticmethod
    def _change(p: Profile, ts: float, kind: str, old: Any, new: Any) -> None:
        p.changes.append([int(ts), kind, old, new])
        del p.changes[:-flags.CHANGES_MAX]

    # ── positions (from the live board, once a cycle) ──────────────────────────────────────────
    def observe(self, rows: Iterable[tuple[int, float, float, float, float]], now: float) -> int:
        """Fold the board's latest rows ``(mmsi, lat, lon, sog, seen)`` in. Returns how many profiles gained a newer position."""
        n = 0
        for mmsi, lat, lon, sog, seen in rows:
            p = self._profile(mmsi, seen)
            if p is None or seen <= p.last:
                continue
            p.last, p.lat, p.lon, p.sog = seen, lat, lon, sog
            n += 1
            a = p.samples
            if len(a) and seen - a[-4] < flags.SAMPLE_STEP_S:
                continue
            row = (int(seen), round(lat * _E4), round(lon * _E4), round(sog * 10) if sog >= 0 else -10)
            if len(a) and km_between(a[-3] / _E4, a[-2] / _E4, lat, lon) * 1000 < flags.STILL_M:
                a[-4:] = array("i", row)                         # still here: refresh the last sample rather than add one
            else:
                a.extend(row)
                if len(a) > flags.SAMPLES_MAX * 4:
                    del a[:4]
            if sog >= MOVING_KN:
                self._bump(lat, lon, seen)
        return n

    def _bump(self, lat: float, lon: float, ts: float) -> None:
        k = (cell_id(lat, lon), int(ts // 3600))
        self.activity[k] = self.activity.get(k, 0) + 1

    def hourly_activity(self, cells: Iterable[int], first_hour: int, last_hour: int) -> float:
        """Mean underway samples per hour over [first_hour, last_hour] summed across ``cells`` (0 for an empty range)."""
        if last_hour < first_hour:
            return 0.0
        cs = list(cells)
        total = sum(self.activity.get((c, h), 0) for c in cs for h in range(first_hour, last_hour + 1))
        return total / (last_hour - first_hour + 1)

    # ── bounds ─────────────────────────────────────────────────────────────────────────────────
    def prune(self, now: float) -> int:
        """Drop expired profiles, enforce the cap (freshest kept), and drop old activity. Returns profiles removed."""
        horizon = now - flags.PROFILE_KEEP_S
        before = len(self.profiles)
        self.profiles = {m: p for m, p in self.profiles.items() if max(p.last, p.first) >= horizon}
        if len(self.profiles) > flags.PROFILE_MAX:
            keep = sorted(self.profiles.items(), key=lambda kv: -max(kv[1].last, kv[1].first))[:flags.PROFILE_MAX]
            self.profiles = dict(keep)
        if len(self.profiles) != before:
            self.by_imo = {}
            for m, p in self.profiles.items():
                if p.imo:
                    self.by_imo.setdefault(p.imo, set()).add(m)
        cut = int(now // 3600) - flags.ACTIVITY_KEEP_H
        if any(h < cut for _c, h in self.activity):
            self.activity = {k: v for k, v in self.activity.items() if k[1] >= cut}
        return before - len(self.profiles)

    # ── disk ───────────────────────────────────────────────────────────────────────────────────
    def document(self) -> dict[str, Any]:
        return {"v": 1, "p": {str(m): p.to_json() for m, p in self.profiles.items()}}

    @staticmethod
    def write(path: Path, doc: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=5) as fh:
            json.dump(doc, fh, separators=(",", ":"), ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "ProfileBook":
        book = cls()
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError, EOFError):
            return book
        for k, row in (doc.get("p") or {}).items():
            try:
                p = Profile.from_json(int(k), row)
            except (ValueError, TypeError, IndexError):
                continue
            book.profiles[p.mmsi] = p
            if p.imo:
                book.by_imo.setdefault(p.imo, set()).add(p.mmsi)
            for ts, lat, lon, sog in p.points():
                if sog >= MOVING_KN:
                    book._bump(lat, lon, ts)
        return book
