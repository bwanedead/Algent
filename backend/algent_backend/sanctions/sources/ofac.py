"""
US Treasury OFAC — the Specially Designated Nationals list (SDN.XML from the Sanctions List Service).

The list carries no designation date, so a first snapshot is only a baseline; from the second on, additions and removals are
events dated the day we saw them. A work of the US government (public domain).
"""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend import polite_http

from .. import countries
from ..contracts import Entry
from . import child, descendants, elements

URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML"
DETAIL = "https://sanctionssearch.ofac.treas.gov/Details.aspx?id={ref}"
_TYPES = {"individual": "person", "entity": "entity", "vessel": "vessel", "aircraft": "aircraft"}
_IMO = re.compile(r"IMO\s*(\d{7})")


def parse(path: Path) -> dict[str, Entry]:
    out: dict[str, Entry] = {}
    for el in elements(path, "sdnEntry"):
        ref = child(el, "uid")
        kind = _TYPES.get(child(el, "sdnType").casefold())
        if not ref or kind is None:
            continue
        last, first = child(el, "lastName"), child(el, "firstName")
        # countries: where it is based (addresses), whose it is (nationality / citizenship), the flag of a vessel
        places = [*descendants(el, "country"), *descendants(el, "vesselFlag")]
        imo = next((m.group(1) for t in descendants(el, "idNumber") if (m := _IMO.search(t))), "")
        out[ref] = Entry(ref=ref, name=" ".join(p for p in (first, last) if p), type=kind,       # type: ignore[arg-type]
                         programmes=list(dict.fromkeys(descendants(el, "program"))), countries=countries.many(places),
                         imo=imo, flag=countries.iso2(child_of(el, "vesselInfo", "vesselFlag")) or "",
                         owner=child_of(el, "vesselInfo", "vesselOwner"))
    return out


def child_of(el, parent: str, name: str) -> str:
    for c in el:
        if c.tag.rsplit("}", 1)[-1] == parent:
            return child(c, name)
    return ""


def fetch(workdir: Path) -> dict[str, Entry]:
    return parse(polite_http.download(URL, workdir / "ofac_sdn.xml", system_trust=True))
