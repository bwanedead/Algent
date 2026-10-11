"""
The world sweep ("Around the world") and the Spotlight — breadth and depth for what the focus misses.

The focus (``focus.plan``) is heat x novelty, so volume wins: the loud theaters return every day and a quiet,
consequential thing in Africa, the Arctic, Central America or space never reaches a section. The sweep is the
counterweight, and it is cheap: ONE house-model call over material the desk already holds for free (the last
~48 hours of headlines from theaters NOT in today's focus, the source library's recent titles that no theater
claimed, the statements ledger and the flagged instrument moves) that writes a short region-grouped digest.

* DIGEST. Per region where something genuinely consequential happened: a plain sentence (what happened and
  why it matters), the countries involved (ISO alpha-2, for flags) and the URL(s) it rests on. Regions are a
  coverage scaffold the writer looks across, not a quota: an empty region is a finding. What the focus
  sections already cover is excluded, by the writer's instruction and mechanically (an item resting only on
  sources the focus sections cite is dropped).
* SPOTLIGHT. The same call may nominate ONE item for a full researched section: consequential, under-covered,
  and not covered by the daily in the last ``focus.FOCUS_DROP_DAYS`` days (the desk's own span of attention;
  the writer is told what was covered, and the nomination is re-checked here against the dailies on disk).
  A nominee that is a theater already on the board is that theater; any other becomes an AD-HOC theater built
  from the cited headlines. Nothing here creates a Pulse: the spotlight section is an ordinary daily section.

Trust is the same as the sections': a sweep item survives only with at least one source URL that is in the
material it was handed (the writer cannot cite what it was not shown), and a country code that is a real
country. Everything here is best-effort; a failed sweep costs only the sweep (the caller records the error).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import base as base_mod
from . import focus
from . import sensing as sensing_mod
from .contracts import Member, Theater

WINDOW_DAYS = 2             # "the last ~48 hours": the operator's framing of the sweep's reach
#: Library titles are the bulk of the free material (hundreds a day). Every line is prompt the writer must read,
#: so the pool is cut by ``base.spread`` (days and sources take turns); same reasoning as the clusterer's budget.
LIBRARY_LINE_BUDGET = 200
MAX_COUNTRIES = 4           # flags per item: a sentence about more countries than this is about a bloc
_ISO2 = re.compile(r"^[A-Za-z]{2}$")

SWEEP_ROLE = """\
You are an editor on an intelligence desk. The daily report goes deep on the few theaters the headline
volume put in focus today. Your job is the opposite one: look ACROSS THE WORLD for what that machinery
under-weights, and flag it briefly. Loud theaters are covered elsewhere; you are the reader's guard against
a consequential thing happening quietly. Volume is not importance: a coup attempt in the Sahel, a port
concession in Central America, a mining or basing deal in the Arctic, a launch-schedule slip that decides
who reaches the Moon first, a debt restructuring, an election rule change, a river treaty — these often matter
more over a year than a day's escalation in a theater everyone already watches.

Ask, region by region: what would a sharp analyst want flagged here that the headlines are under-weighting?
Regions are only a scaffold for looking (Africa, the Middle East, South Asia, East Asia, Southeast Asia and
Oceania, Europe, Russia and Central Asia, North America, Latin America and the Caribbean, the Arctic and
Antarctic, space and the high seas). They are not a quota. Most days several regions have nothing worth a
line, and saying nothing is the right answer for them. Never pad a region to fill it, and do not restate the
big theaters under another name.

WHAT YOU ARE GIVEN: the last ~48 hours of material the desk already holds, kept apart by what each kind can
prove. Headlines are what other outlets reported and are unverified by us; STATEMENTS are what a named
official said (proof it was said, not that it is true); INSTRUMENT readings are public data with a date.
Write what the material supports and no more; one headline is a lead, not a settled fact, and an item that
rests on a single report should read that way ("reportedly", "according to ...").

WHAT TO WRITE:
- `items`: per region where something genuinely consequential happened, one to three items, most important
  first. Each is ONE plain sentence a newcomer can follow: what happened and why it matters. `region` is the
  region's name. `countries` are the ISO 3166-1 alpha-2 codes of the states involved (they become flags), as
  few as tell the story. `sources` are the URLs the sentence rests on, copied exactly from the material; an
  item with no URL from the material is dropped by the desk, so do not invent or reconstruct one.
- ALREADY COVERED: the focus sections (listed) and the recent dailies already carry their theaters. Do not
  write an item about them, and do not repeat something flagged on a recent day unless it has moved.
- `spotlight`: on AT MOST ONE item, set `spotlight: true`. Choose the item that most deserves a full
  researched section: consequential, genuinely under-covered, and not covered by the daily in the last week.
  Give it a `title` (a short name for the dynamic, naming who and what, like a theater's name). If it is
  plainly the same dynamic as a theater listed under THEATERS NOT IN FOCUS, give that theater's id as
  `theater_id`; otherwise leave `theater_id` empty. A day with no such item has no spotlight: do not
  nominate for the sake of it, and a spotlight costs real research money, so nominate only what a section
  could actually be built on (an item whose sources are rich enough to research further).
Plain words; no internal jargon (no claim ids, no pipeline terms). Do not reproduce passages from sources.
"""


class SweepItemDraft(BaseModel):
    region: str
    text: str = Field(description="One plain sentence: what happened and why it matters.")
    countries: list[str] = Field(default_factory=list, description="ISO 3166-1 alpha-2 codes of the states involved.")
    sources: list[str] = Field(default_factory=list, description="URLs from the material the sentence rests on.")
    spotlight: bool = Field(default=False, description="True on at most one item: the one most deserving a section.")
    title: str = Field(default="", description="Spotlight only: a short name for the dynamic.")
    theater_id: str = Field(default="", description="Spotlight only: the id of a listed not-in-focus theater it is.")


class SweepDraft(BaseModel):
    items: list[SweepItemDraft] = Field(default_factory=list)


def norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


@dataclass
class Material:
    """What the writer is shown, and the closed sets it may cite from."""

    text: str = ""
    urls: set[str] = field(default_factory=set)             # normalised: the only URLs an item may cite
    heads: dict[str, dict] = field(default_factory=dict)    # normalised url -> {title, thesis, day, kind}
    eligible: dict[str, Theater] = field(default_factory=dict)    # not-in-focus theaters of the domain, by id

    @property
    def empty(self) -> bool:
        return not self.urls


@dataclass
class Sweep:
    regions: list[dict] = field(default_factory=list)       # [{"region", "items": [{text, countries, sources, spotlight?}]}]
    spotlight: dict | None = None                            # {theater_id, name, text, region, countries, sources, adhoc}
    theater: Theater | None = None                           # the spotlight's theater (board theater or ad hoc)
    error: str = ""

    def record(self) -> dict:
        return {"window_days": WINDOW_DAYS, "regions": self.regions, "spotlight": self.spotlight}

    @property
    def items(self) -> int:
        return sum(len(r["items"]) for r in self.regions)


# ── material (free: no model, no network beyond local stores) ─────────────────────────────────
def _window_start(as_of: str) -> str:
    return (date.fromisoformat(as_of) - timedelta(days=WINDOW_DAYS - 1)).isoformat()


def library_material(as_of: str) -> list[dict]:
    """Recent source-library titles (a local read; [] when the library is absent)."""
    return base_mod.library_heads(WINDOW_DAYS, date.fromisoformat(as_of))


def _theater_block(t: Theater, start: str, mat: Material) -> str:
    """A not-in-focus theater's headlines inside the window ('' when it has none); feeds ``mat``'s closed sets."""
    lines = []
    for m in sorted(t.members, key=lambda m: m.edition):
        if m.edition[:10] < start:
            continue
        url = next((norm_url(u) for u in m.sources if norm_url(u)), "")
        if url:
            mat.urls.add(url)
            mat.heads.setdefault(url, {"title": m.title, "thesis": m.thesis, "day": m.edition[:10], "kind": m.kind})
        lines.append(f"- ({m.edition[:10]}) {m.title} — {m.thesis[:200]} [{url or 'no url'}]")
    if lines:
        mat.eligible[t.id] = t
    return f"THEATER {t.id} — {t.name}\n" + "\n".join(lines) if lines else ""


def _library_block(board: dict, mat: Material, as_of: str, library: Callable[[str], list[dict]]) -> str:
    """Recent library titles no theater (of any domain or focus) already carries: the unclaimed remainder."""
    claimed = {norm_url(u) for raw in board.get("theaters", []) for m in raw.get("members", []) for u in m.get("sources", [])}
    try:
        pool = [h for h in base_mod.dedupe(library(as_of)) if norm_url((h.get("sources") or [""])[0]) not in claimed]
    except Exception:  # noqa: BLE001 - the library is an aid; a broken store costs the sweep nothing else
        pool = []
    lines = []
    for h in base_mod.spread(pool, LIBRARY_LINE_BUDGET):
        url = norm_url(h["sources"][0]) if h.get("sources") else ""
        if url:
            mat.urls.add(url)
            mat.heads.setdefault(url, {"title": h["title"], "thesis": h.get("thesis", ""), "day": h["day"], "kind": h["kind"]})
            lines.append(f"- ({h['day']}) [{h.get('thesis', '')}] {h['title']} [{url}]")
    return "NOT IN ANY THEATER (recent titles from our trusted-source library)\n" + "\n".join(lines) if lines else ""


def gather(board: dict, *, domain: str, focus_ids: set[str], as_of: str,
           library: Callable[[str], list[dict]] = library_material,
           evidence: sensing_mod.Evidence | None = None) -> Material:
    """The last ~48h of what the desk holds, minus what today's focus already carries."""
    start = _window_start(as_of)
    mat = Material()
    theaters = [Theater.model_validate(raw) for raw in board.get("theaters", [])]
    blocks = [_theater_block(t, start, mat) for t in theaters
              if t.id not in focus_ids and (t.domain or "").lower() == domain.lower()]
    blocks.append(_library_block(board, mat, as_of, library))
    ev = evidence if evidence is not None else sensing_mod.across_theaters(as_of=as_of, days=WINDOW_DAYS)
    mat.urls |= {norm_url(u) for u in ev.statement_urls | ev.instrument_urls}
    if ev.render().strip():
        blocks.append("STATEMENTS ON RECORD AND INSTRUMENT MOVES, ACROSS ALL ACTORS\n" + ev.render().strip())
    mat.urls.discard("")
    mat.text = "\n\n".join(b for b in blocks if b)
    return mat


def _coverage_of(rec: dict, stem: str) -> tuple[list[str], set[str]]:
    """One daily record's coverage as prompt lines (sections, flagged items, spotlight) and theater ids."""
    lines, ids = [], set()
    for sec in rec.get("theaters") or []:
        ids.add(sec.get("theater_id", ""))
        lines.append(f"- ({stem}) section: {sec.get('name', '')} — {str(sec.get('bottom_line', ''))[:160]}")
        lines += [f"- ({stem}) update: {sec.get('name', '')} — {str(u.get('bottom_line', ''))[:160]}"
                  for u in sec.get("updates") or []]
    sweep = rec.get("sweep") or {}
    for reg in sweep.get("regions") or []:
        lines += [f"- ({stem}) flagged, {reg.get('region', '')}: {i.get('text', '')[:160]}"
                  for i in reg.get("items") or []]
    spot = sweep.get("spotlight") or {}
    if spot.get("theater_id"):
        ids.add(spot["theater_id"])
    return lines, ids


def recent_coverage(folder: Path, *, before: str, today: dict | None = None) -> tuple[str, set[str]]:
    """What the dailies of the last ``FOCUS_DROP_DAYS`` days covered (theater names and bottom lines, earlier
    sweep items, earlier spotlights) as prompt text, and the theater ids that had a section or a spotlight.
    ``today`` is the day's record so far, for a later edition: its earlier parts count as covered too."""
    floor = (date.fromisoformat(before) - timedelta(days=focus.FOCUS_DROP_DAYS)).isoformat()
    lines, ids = [], set()
    for path in sorted(folder.glob("*.json"), reverse=True) if folder.is_dir() else []:
        if not floor <= path.stem < before:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        more, got = _coverage_of(rec, path.stem)
        lines += more
        ids |= got
    if today:
        more, got = _coverage_of(today, f"{before}, earlier today")
        lines += more
        ids |= got
    ids.discard("")
    return "\n".join(lines), ids


# ── the writer and its guards ─────────────────────────────────────────────────────────────────
def clean(draft: SweepDraft, mat: Material, *, covered_urls: set[str], known_iso: set[str] | None = None
          ) -> list[tuple[SweepItemDraft, dict]]:
    """Items that hold: text, at least one source that is in the material and not one the focus sections
    already rest on, countries that are real two-letter codes. Returns (draft item, clean record) pairs."""
    out = []
    covered = {norm_url(u) for u in covered_urls}
    for it in draft.items:
        text = " ".join(it.text.split())
        sources = [u.strip() for u in dict.fromkeys(it.sources) if norm_url(u) in mat.urls]
        fresh = [u for u in sources if norm_url(u) not in covered]
        if not text or not it.region.strip() or not fresh:
            continue                    # nothing to stand on, or already carried by a focus section
        codes = [c.upper() for c in dict.fromkeys(it.countries) if _ISO2.match(c.strip() or "-")]
        codes = [c for c in codes if known_iso is None or c in known_iso][:MAX_COUNTRIES]
        out.append((it, {"region": " ".join(it.region.split()), "text": text, "countries": codes, "sources": fresh}))
    return out


def _group(pairs: list[tuple[SweepItemDraft, dict]], spotlight_item: SweepItemDraft | None) -> list[dict]:
    regions: dict[str, list[dict]] = {}
    for it, rec in pairs:
        item = {k: rec[k] for k in ("text", "countries", "sources")}
        if it is spotlight_item:
            item["spotlight"] = True
        regions.setdefault(rec["region"], []).append(item)
    return [{"region": r, "items": items} for r, items in regions.items()]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48] or "item"


def _nominee(pairs: list[tuple[SweepItemDraft, dict]], mat: Material, recent_ids: set[str], domain: str
             ) -> tuple[SweepItemDraft | None, Theater | None]:
    """The first flagged item that can carry a section: a theater on the board (not in focus, not covered in
    the last span) or an ad-hoc one built from the headlines it cites. None otherwise."""
    for it, rec in pairs:
        if not it.spotlight or not it.title.strip():
            continue
        known = mat.eligible.get(it.theater_id.strip())
        if known is not None:
            if known.id in recent_ids:
                continue
            return it, known
        tid = f"thr_spot_{_slug(it.title)}"
        members = [Member(edition=f"{h['day']}-{h['kind']}", n=i, kind=h["kind"], title=h["title"], thesis=h["thesis"],
                          sources=[u]) for i, u in enumerate(rec["sources"], 1) if (h := mat.heads.get(norm_url(u)))]
        if tid in recent_ids or not members:
            continue                    # recently the spotlight, or nothing headline-shaped to build a theater from
        return it, Theater(id=tid, name=it.title.strip(), domain=domain, description=rec["text"], why=rec["text"],
                           members=members)
    return None, None


def regions_from_archive(archive: dict, *, known_iso: set[str] | None, spotlight_text: str = "") -> list[dict]:
    """The sweep's regions re-derived from its saved raw draft, no model: the same guards (``clean``) over the
    saved material URLs, with the saved spotlight's item re-flagged. For ``daily_rerender``."""
    pairs = clean(SweepDraft.model_validate(archive["draft"]), Material(urls=set(archive["urls"])),
                  covered_urls=set(archive["covered_urls"]), known_iso=known_iso)
    nominee = next((it for it, rec in pairs if spotlight_text and rec["text"] == spotlight_text), None)
    return _group(pairs, nominee)


def run(ask: Callable[[Any, str, str], Any], *, board: dict, domain: str, as_of: str, focus_ids: set[str],
        covered: list[str], covered_urls: set[str], folder: Path, known_iso: set[str] | None = None,
        library: Callable[[str], list[dict]] = library_material,
        evidence: sensing_mod.Evidence | None = None, archive: dict | None = None,
        today: dict | None = None, allow_spotlight: bool = True) -> Sweep:
    """Gather, ask once, validate. ``ask(schema, role, task)`` makes the model call (the daily's ``_ask``).
    Raises only what ``ask`` raises; the caller decides that a failed sweep must not cost the day.
    ``today`` is the day's record so far (a later edition's sweep excludes what the earlier parts covered);
    ``allow_spotlight=False`` keeps this call from nominating one (the day already has its spotlight)."""
    mat = gather(board, domain=domain, focus_ids=focus_ids, as_of=as_of, library=library, evidence=evidence)
    if mat.empty:
        return Sweep()
    recent_text, recent_ids = recent_coverage(folder, before=as_of, today=today)
    task = (f"TODAY: {as_of}. Material is from the last {WINDOW_DAYS} days.\n\n"
            "ALREADY COVERED TODAY BY THE FOCUS SECTIONS (do not write about these):\n"
            + ("\n".join(f"- {c}" for c in covered) or "- (none)") + "\n\n"
            f"COVERED OR FLAGGED IN THE LAST {focus.FOCUS_DROP_DAYS} DAYS:\n{recent_text or '- (none)'}\n\n"
            f"MATERIAL:\n{mat.text}\n\nTASK: write the sweep.")
    draft = ask(SweepDraft, SWEEP_ROLE, task)
    if not isinstance(draft, SweepDraft):
        return Sweep(error="sweep writer returned nothing")
    if archive is not None:         # the raw draft and what its guards need, for ``regions_from_archive``
        archive.update(draft=draft.model_dump(), urls=sorted(mat.urls), covered_urls=sorted(covered_urls))
    pairs = clean(draft, mat, covered_urls=covered_urls, known_iso=known_iso)
    nominee, theater = _nominee(pairs, mat, recent_ids, domain) if allow_spotlight else (None, None)
    spot = None
    if nominee is not None and theater is not None:
        rec = next(r for it, r in pairs if it is nominee)
        spot = {"theater_id": theater.id, "name": theater.name, "text": rec["text"], "region": rec["region"],
                "countries": rec["countries"], "sources": rec["sources"], "adhoc": theater.id not in mat.eligible}
    return Sweep(regions=_group(pairs, nominee), spotlight=spot, theater=theater)
