"""
Wikidata (CC0) — every current sovereign state's head of state (P35) and head of government (P6).

One SPARQL query. "Current" = the statement has no end-time qualifier (P582) and the state no
dissolution date (P576). A state can come back with several holders (a dual-leader or stale entry); the
one with the latest start date wins per office. Wikidata asks bulk clients to identify themselves, so
the request carries the descriptive User-Agent with a contact (catalog.HEADERS). Foreign and defence ministers are left
out: the data is too patchy to publish as fact (see docs/architecture/actors.md).
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.polite_http import SourceError, get

from .. import registry
from ..catalog import HEADERS
from ..contracts import Leaders, Official, now_iso

ENDPOINT = "https://query.wikidata.org/sparql"

QUERY = """
SELECT ?iso ?hos ?hosL ?hosStart ?hog ?hogL ?hogStart WHERE {
  ?c wdt:P297 ?iso .
  FILTER NOT EXISTS { ?c wdt:P576 [] }
  ?c wdt:P31/wdt:P279* wd:Q3624078 .
  OPTIONAL { ?c p:P35 ?hs . ?hs ps:P35 ?hos . FILTER NOT EXISTS { ?hs pq:P582 [] } OPTIONAL { ?hs pq:P580 ?hosStart } }
  OPTIONAL { ?c p:P6 ?gs . ?gs ps:P6 ?hog . FILTER NOT EXISTS { ?gs pq:P582 [] } OPTIONAL { ?gs pq:P580 ?hogStart } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". ?hos rdfs:label ?hosL. ?hog rdfs:label ?hogL. }
}"""


def _val(row: dict, key: str) -> str:
    return (row.get(key) or {}).get("value", "")


def _official(row: dict, who: str, label: str, start: str) -> tuple[str, Official] | None:
    name = _val(row, label)
    if not name or (name.startswith("Q") and name[1:].isdigit()):      # an unlabelled entity renders as its Q-id
        return None
    return _val(row, start), Official(name=name, since=_val(row, start)[:10], id=_val(row, who).rsplit("/", 1)[-1])


def parse_bindings(payload: Any, fetched_at: str) -> list[Leaders]:
    """Leaders per registry country from a SPARQL JSON result; the latest-started holder wins per office."""
    best: dict[tuple[str, str], tuple[str, Official]] = {}
    for row in payload["results"]["bindings"]:
        iso2 = _val(row, "iso").upper()
        if registry.get(iso2) is None:
            continue
        for office, args in (("hos", ("hos", "hosL", "hosStart")), ("hog", ("hog", "hogL", "hogStart"))):
            cand = _official(row, *args)
            if cand and ((iso2, office) not in best or cand[0] > best[(iso2, office)][0]):
                best[(iso2, office)] = cand
    out = []
    for iso2 in sorted({k[0] for k in best}):
        hos, hog = best.get((iso2, "hos")), best.get((iso2, "hog"))
        out.append(Leaders(iso2=iso2, head_of_state=hos[1] if hos else None, head_of_government=hog[1] if hog else None,
                           fetched_at=fetched_at, source_url=f"{ENDPOINT} (Wikidata P35/P6)"))
    return out


def fetch_leaders() -> list[Leaders]:
    body = get(ENDPOINT, {"query": QUERY, "format": "json"}, headers={**HEADERS, "Accept": "application/sparql-results+json"})
    try:
        return parse_bindings(json.loads(body), now_iso())
    except (KeyError, ValueError) as exc:
        raise SourceError(f"Wikidata: unexpected result shape ({exc})") from exc
