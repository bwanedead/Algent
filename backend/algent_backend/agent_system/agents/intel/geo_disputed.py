"""
Disputed and occupied territory for the daily maps: Natural Earth's disputed-areas layer (public domain)
plus a small cited table of what is factually said about the areas our theaters touch.

The base map draws internationally recognised borders (``geo._RECOGNISED``: Crimea is Ukraine). This layer
says, on top of that, "this area is held, administered or claimed otherwise" — it never moves a border and
it is NOT a front line (a dated, licensed control layer is a separate seam: see
``docs/editorial/map-data-sources.md``, "Pipeline").

Wording rule (spirit: no deception, reality over neutrality): state the internationally recognised status,
who controls the area now, and since when — facts, not sides. Where the table has no entry, the area carries
only the dataset's own words (``NOTE_BRK``, expanded: "Admin. by Russia; Claimed by Ukraine" becomes
"Administered by Russia; claimed by Ukraine"). An area is drawn only if the table knows it or the dataset
itself records a claim/administration; ordinary entries of the file (Israel, Kosovo, Belize, Ceuta …) are
not "disputed" for our purposes and are skipped.

Bounds: at most ``MAX_AREAS`` per map (largest visible first); specks smaller than a few frame units are
dropped; the table covers the areas of the live theaters (~20 entries) and grows by editing ``STATUS``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .geo_draw import Pt, anchor, ring_area, ring_path, simplify

MAX_AREAS = 12
MIN_EXTENT = 6.0                      # frame units: below this a hatch is invisible, so the area is not drawn
KINDS = ("occupied", "administered", "self-administered", "claimed", "buffer", "former")
_UN = "https://undocs.org/"
_WP = "https://en.wikipedia.org/wiki/"
_CAVEAT_UA = (" Outline is the dataset's older extent, not a front line; other Russian-held areas (parts of "
              "Zaporizhzhia and Kherson regions) are not in this dataset.")


@dataclass(frozen=True)
class Status:
    label: str
    kind: str | None                  # None: derive from the dataset note
    text: str
    source: str


#: Dataset BRK_NAME -> wording. Every entry cites a source; every sentence is a fact, not a position.
STATUS: dict[str, Status] = {
    "Crimea": Status("Crimea", "occupied",
                     "Ukrainian territory (UN General Assembly Res. 68/262) occupied by Russia since 2014; Russia "
                     "declared it annexed in March 2014.", _UN + "A/RES/68/262"),
    "Donetsk People's Republic": Status("Donetsk region", "occupied",
                                        "Ukrainian territory, held in part by Russia-backed forces since 2014. Russia "
                                        "declared annexation in September 2022; the UN General Assembly declared it "
                                        "invalid (Res. ES-11/4)." + _CAVEAT_UA, _UN + "A/RES/ES-11/4"),
    "Luhansk People's Republic": Status("Luhansk region", "occupied",
                                        "Ukrainian territory, held in part by Russia-backed forces since 2014. Russia "
                                        "declared annexation in September 2022; the UN General Assembly declared it "
                                        "invalid (Res. ES-11/4)." + _CAVEAT_UA, _UN + "A/RES/ES-11/4"),
    "Gaza": Status("Gaza Strip", "occupied",
                   "Part of the Occupied Palestinian Territory (UN General Assembly; ICJ advisory opinion of 19 July "
                   "2024). Israel withdrew its settlements and troops in 2005; Israeli forces have operated in the Strip "
                   "since October 2023. The outline is the territory, not who holds which part today.",
                   "https://www.icj-cij.org/case/186"),
    "West Bank": Status("West Bank", "occupied",
                        "Part of the Occupied Palestinian Territory, held by Israel since 1967 (ICJ advisory opinion of "
                        "19 July 2024).", "https://www.icj-cij.org/case/186"),
    "East Jerusalem": Status("East Jerusalem", "occupied",
                             "Held by Israel since 1967 and annexed by it in 1980; the UN Security Council declared the "
                             "annexation null and void (Res. 478).", _UN + "S/RES/478(1980)"),
    "Golan Heights": Status("Golan Heights", "occupied",
                            "Syrian territory held by Israel since 1967; Israel applied its law there in 1981, which the "
                            "UN Security Council declared null and void (Res. 497).", _UN + "S/RES/497(1981)"),
    "Shebaa Farms": Status("Shebaa Farms", "administered",
                           "Held by Israel since 1967. Lebanon claims it; the UN has treated it as part of the Golan "
                           "Heights (Syrian territory).", _WP + "Shebaa_Farms"),
    "Abkhazia": Status("Abkhazia", "self-administered",
                       "Georgian territory (internationally recognised) run by Russia-backed de facto authorities since "
                       "the 1990s. Russia recognised it as independent in 2008; very few states did.",
                       _WP + "International_recognition_of_Abkhazia_and_South_Ossetia"),
    "South Ossetia": Status("South Ossetia", "self-administered",
                            "Georgian territory (internationally recognised) run by Russia-backed de facto authorities "
                            "since the 1990s. Russia recognised it as independent in 2008; very few states did.",
                            _WP + "International_recognition_of_Abkhazia_and_South_Ossetia"),
    "Transnistria": Status("Transnistria", "self-administered",
                           "Moldovan territory (internationally recognised) run by a de facto authority since 1992, with "
                           "Russian troops stationed there. No UN member state recognises it.", _WP + "Transnistria"),
    "Artsakh": Status("Nagorno-Karabakh", "former",
                      "Azerbaijani territory (internationally recognised). Armenian-backed de facto authorities ran it "
                      "from 1994 until Azerbaijan's offensive of September 2023; the self-declared republic dissolved "
                      "in January 2024.", _WP + "2023_Azerbaijani_offensive_in_Nagorno-Karabakh"),
    "W. Sahara": Status("Western Sahara", None,
                        "A UN-listed non-self-governing territory; sovereignty is unresolved. Morocco administers most of "
                        "it, the Polisario Front the area east of the berm.",
                        "https://www.un.org/dppa/decolonization/en/nsgt/western-sahara"),
    "N. Cyprus": Status("Northern Cyprus", "self-administered",
                        "Territory of the Republic of Cyprus (recognised by the UN) run by Turkish Cypriot authorities "
                        "since 1974, backed by Turkish forces. Only Turkey recognises the self-declared state (UN "
                        "Security Council Res. 541).", _UN + "S/RES/541(1983)"),
    "Korean Demilitarized Zone (north)": Status("Korean DMZ", "buffer",
                                                "A buffer zone along the 1953 armistice line, 2 km on each side; not a "
                                                "border.", _WP + "Korean_Demilitarized_Zone"),
    "Korean Demilitarized Zone (south)": Status("Korean DMZ", "buffer",
                                                "A buffer zone along the 1953 armistice line, 2 km on each side; not a "
                                                "border.", _WP + "Korean_Demilitarized_Zone"),
    "Paracel Is.": Status("Paracel Islands", "administered",
                          "Fully controlled by China since 1974; also claimed by Vietnam and Taiwan.",
                          _WP + "Paracel_Islands"),
    "Spratly Is.": Status("Spratly Islands", "claimed",
                          "Claimed in whole or part by China, Taiwan, Vietnam, the Philippines, Malaysia and Brunei; "
                          "all but Brunei occupy some features.", _WP + "Spratly_Islands"),
}

_CLAIM = re.compile(r"claimed|self[ -]admin|admin(?:istered|\.)? by|between", re.I)
_PLAIN = [(re.compile(r"\bAdmin\.? by\b", re.I), "Administered by"), (re.compile(r"\bSelf admin\.?", re.I), "Self-administered"),
          (re.compile(r"\bAzer\b\.?", re.I), "Azerbaijan"), (re.compile(r"\bU\.S\.A\.?", re.I), "the U.S."),
          (re.compile(r"\bU\.K\.", re.I), "the U.K."), (re.compile(r"; Claimed", re.I), "; claimed"),
          (re.compile(r"^Claimed"), "Claimed")]


@dataclass
class Disputed:
    name: str                          # the dataset's own name (BRK_NAME)
    note: str                          # the dataset's own words (NOTE_BRK), may be ""
    polygons: list[list[list[Pt]]]     # lon/lat; outer ring first, holes after
    bbox: tuple[float, float, float, float]


def plain(note: str) -> str:
    """The dataset's abbreviated note as a plain sentence: 'Self admin.; Claimed by Moldova' -> 'Self-administered; claimed by Moldova'."""
    out = note.strip().rstrip(".")
    for pat, rep in _PLAIN:
        out = pat.sub(rep, out)
    return out[:1].upper() + out[1:]


def from_feature(props: dict, polygons: list[list[list[Pt]]]) -> Disputed | None:
    """A Disputed from a Natural Earth feature, or None when the file lists it as an ordinary entry (no claim,
    no administration noted, no table entry) or it has no geometry."""
    name = str(props.get("BRK_NAME") or props.get("NAME") or "").lstrip("﻿").strip()
    note = str(props.get("NOTE_BRK") or "").strip()
    pts = [p for poly in polygons for ring in poly for p in ring]
    if not name or not pts or (name not in STATUS and not _CLAIM.search(note)):
        return None
    return Disputed(name, note, polygons, (min(p[0] for p in pts), min(p[1] for p in pts),
                                           max(p[0] for p in pts), max(p[1] for p in pts)))


def _claimants(note: str) -> list[str]:
    m = re.search(r"claimed by (.+)$", plain(note), re.I)
    if not m:
        return []
    return [c.strip() for c in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1)) if c.strip()]


def _kind(note: str) -> str:
    low = note.lower()
    return "self-administered" if "self admin" in low else "administered" if re.search(r"admin", low) else "claimed"


def entry(area: Disputed, drawn: list[list[list[Pt]]], tol: float) -> dict | None:
    """The spec entry for an area already projected and clipped to the frame (``drawn``: [[outer, *holes], ...]),
    or None when nothing visible is left. {name, d, note, status, claimants, source, x, y, r}: x/y/r seat the label."""
    d = ring_path([r for poly in drawn for r in poly], tol, min_extent=max(MIN_EXTENT, 3 * tol))
    if not d:
        return None
    best = max(drawn, key=lambda poly: ring_area(poly[0]))
    ax, ay, r = anchor(simplify(best[0], tol, closed=True), [simplify(h, tol, closed=True) for h in best[1:]])
    st = STATUS.get(area.name)
    base = {"d": d, "area": ring_area(best[0]), "x": round(ax, 1), "y": round(ay, 1), "r": round(r, 1), "claimants": _claimants(area.note)}
    if st is not None:
        return {"name": st.label, "note": st.text, "status": st.kind or _kind(area.note), "source": st.source, **base}
    return {"name": area.name, "note": plain(area.note), "status": _kind(area.note), "source": "", **base}


def top_areas(entries: list[dict]) -> list[dict]:
    """The ``MAX_AREAS`` largest visible entries, largest first, with the sorting key dropped. The DMZ halves and
    the two Western Sahara pieces share a name and note but are separate hatches."""
    keep = sorted(entries, key=lambda e: -e["area"])[:MAX_AREAS]
    return [{k: v for k, v in e.items() if k != "area"} for e in keep]
