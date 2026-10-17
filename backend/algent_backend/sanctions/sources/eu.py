"""
EU consolidated financial sanctions list (the Commission's Financial Sanctions Files, "FSF" XML 1.1).

The public token in the URL is the one the Commission documents for anonymous download. An entity's ``designationDate`` (newer
entries) or the publication date of its regulation gives the day it was listed. The EU publishes the list for reuse
(Commission Decision 2011/833/EU, free reuse with attribution).
"""

from __future__ import annotations

from pathlib import Path

from algent_backend import polite_http

from .. import countries
from ..contracts import Entry
from . import descendants, elements, local

URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"


def _attr(el, tag: str, attr: str) -> list[str]:
    return [(d.get(attr) or "").strip() for d in el.iter() if local(d.tag) == tag and (d.get(attr) or "").strip()]


def parse(path: Path) -> dict[str, Entry]:
    out: dict[str, Entry] = {}
    for el in elements(path, "sanctionEntity"):
        ref = el.get("logicalId") or ""
        names = _attr(el, "nameAlias", "wholeName")
        if not ref or not names:
            continue
        ids = [(d.get("identificationTypeCode") or "", (d.get("number") or "").strip()) for d in el.iter() if local(d.tag) == "identification"]
        imo = next((n for t, n in ids if t.casefold() == "imo" and n.isdigit()), "")
        subject = next((d.get("code") or "" for d in el.iter() if local(d.tag) == "subjectType"), "")
        regs = [d for d in el if local(d.tag) == "regulation"]
        urls = [u for r in regs for u in descendants(r, "publicationUrl")]
        out[ref] = Entry(ref=ref, name=names[0], type="vessel" if imo else ("person" if subject == "person" else "entity"),
                         programmes=list(dict.fromkeys(r.get("programme") or "" for r in regs if r.get("programme"))),
                         countries=countries.many([*_attr(el, "address", "countryIso2Code"), *_attr(el, "citizenship", "countryIso2Code")]),
                         designated_on=el.get("designationDate") or max((r.get("publicationDate") or "" for r in regs), default=""),
                         imo=imo, url=urls[-1] if urls else "")
    return out


def fetch(workdir: Path) -> dict[str, Entry]:
    return parse(polite_http.download(URL, workdir / "eu_sanctions.xml"))
