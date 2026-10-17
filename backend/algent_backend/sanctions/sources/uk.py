"""
UK Sanctions List (the single list the FCDO and OFSI publish since the OFSI consolidated list was retired).

Each designation states its own ``DateDesignated``, so a first snapshot can still report the last weeks' designations.
Published under the Open Government Licence v3.0.
"""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend import polite_http

from .. import countries
from ..contracts import Entry
from . import child, descendants, elements, local

URL = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml"
_TYPES = {"individual": "person", "entity": "entity", "ship": "vessel"}
_REGIME = re.compile(r"^(?:The\s+)?(.*?)\s*\(Sanctions\)", re.I)
_IMO = re.compile(r"(\d{7})")


def _date(text: str) -> str:
    """dd/mm/yyyy -> yyyy-mm-dd ('' when it is not a full date)."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text.strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _primary_name(el) -> str:
    for n in el.iter():
        if local(n.tag) == "Name" and child(n, "NameType").casefold() in ("primary name",):
            return " ".join(t for k in range(1, 7) if (t := child(n, f"Name{k}")))
    return ""


def parse(path: Path) -> dict[str, Entry]:
    out: dict[str, Entry] = {}
    for el in elements(path, "Designation"):
        ref = child(el, "UniqueID")
        kind = _TYPES.get(child(el, "IndividualEntityShip").casefold())
        name = _primary_name(el)
        if not ref or kind is None or not name:
            continue
        regime = child(el, "RegimeName")
        prog = _REGIME.match(regime)
        flags = descendants(el, "CurrentBelievedFlagOfShip")
        imo = next((m.group(1) for t in descendants(el, "IMONumber") if (m := _IMO.search(t))), "")
        out[ref] = Entry(ref=ref, name=name, type=kind,                                          # type: ignore[arg-type]
                         programmes=[(prog.group(1) if prog else regime)] if regime else [],
                         countries=countries.many([*descendants(el, "AddressCountry"), *descendants(el, "Nationality"), *flags]),
                         designated_on=_date(child(el, "DateDesignated")), imo=imo,
                         flag=countries.iso2(flags[0]) or "" if flags else "",
                         owner=(descendants(el, "CurrentOwnerOperator") or [""])[0])
    return out


def fetch(workdir: Path) -> dict[str, Entry]:
    return parse(polite_http.download(URL, workdir / "uk_sanctions.xml"))
