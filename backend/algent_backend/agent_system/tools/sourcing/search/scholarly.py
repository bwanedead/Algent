"""
Scholarly resolvers — free DOI / bibliographic lookup (Crossref + OpenAlex).

Science stories often start from a secondary lead (podcast, press) while the primary paper
is recoverable via DOI or title. These resolvers are free HTTP and need no API key.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

_TIMEOUT_S = 20.0
_UA = "AlgentNewsroom/1.0 (research; mailto:newsroom@localhost)"
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def extract_doi(text: str) -> str:
    """Pull the first DOI-looking token from free text, or empty."""
    if not text:
        return ""
    m = _DOI_RE.search(text.strip())
    return m.group(0).rstrip(".)],") if m else ""


def resolve(query: str = "", doi: str = "") -> dict[str, Any]:
    """Resolve a DOI or title/author query to bibliographic records + landing URLs.

    Tries Crossref first, then OpenAlex. Returns ``{action, query, doi, results, via}``.
    """
    target_doi = extract_doi(doi) or extract_doi(query)
    q = (query or doi or "").strip()
    if not target_doi and not q:
        return {"action": "scholar", "error": "provide a doi or a title/author query"}

    if target_doi:
        for via, fn in (("crossref", _crossref_doi), ("openalex", _openalex_doi)):
            hit = fn(target_doi)
            if hit:
                return {
                    "action": "scholar", "kind": "doi", "doi": target_doi,
                    "query": q, "via": via, "results": [hit],
                }
        return {
            "action": "scholar", "kind": "doi", "doi": target_doi, "query": q,
            "results": [], "note": "DOI not found in Crossref or OpenAlex",
        }

    for via, fn in (("crossref", _crossref_query), ("openalex", _openalex_query)):
        hits = fn(q)
        if hits:
            return {"action": "scholar", "kind": "query", "query": q, "via": via, "results": hits}
    return {"action": "scholar", "kind": "query", "query": q, "results": []}


def _crossref_doi(doi: str) -> dict[str, Any] | None:
    import httpx

    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    try:
        r = httpx.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT_S)
        if r.status_code != 200:
            return None
        return _normalize_crossref(r.json().get("message") or {})
    except Exception:
        return None


def _crossref_query(query: str, rows: int = 5) -> list[dict[str, Any]]:
    import httpx

    try:
        r = httpx.get(
            "https://api.crossref.org/works",
            params={"query": query, "rows": rows},
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT_S,
        )
        if r.status_code != 200:
            return []
        items = (r.json().get("message") or {}).get("items") or []
        return [n for it in items if (n := _normalize_crossref(it))]
    except Exception:
        return []


def _openalex_doi(doi: str) -> dict[str, Any] | None:
    import httpx

    url = f"https://api.openalex.org/works/doi:{quote(doi, safe='')}"
    try:
        r = httpx.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT_S)
        if r.status_code != 200:
            return None
        return _normalize_openalex(r.json())
    except Exception:
        return None


def _openalex_query(query: str, rows: int = 5) -> list[dict[str, Any]]:
    import httpx

    try:
        r = httpx.get(
            "https://api.openalex.org/works",
            params={"search": query, "per_page": rows},
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT_S,
        )
        if r.status_code != 200:
            return []
        items = r.json().get("results") or []
        return [n for it in items if (n := _normalize_openalex(it))]
    except Exception:
        return []


def _normalize_crossref(msg: dict[str, Any]) -> dict[str, Any] | None:
    if not msg:
        return None
    doi = str(msg.get("DOI") or "")
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else ""
    authors = []
    for a in (msg.get("author") or [])[:8]:
        name = " ".join(p for p in (a.get("given"), a.get("family")) if p)
        if name:
            authors.append(name)
    year = None
    issued = (msg.get("issued") or {}).get("date-parts") or []
    if issued and issued[0]:
        year = issued[0][0]
    url = str(msg.get("URL") or (f"https://doi.org/{doi}" if doi else ""))
    return {
        "title": title,
        "doi": doi,
        "url": url,
        "authors": authors,
        "year": year,
        "container": (msg.get("container-title") or [""])[0] if msg.get("container-title") else "",
        "type": str(msg.get("type") or ""),
        "publisher": str(msg.get("publisher") or ""),
    }


def _normalize_openalex(msg: dict[str, Any]) -> dict[str, Any] | None:
    if not msg:
        return None
    ids = msg.get("ids") or {}
    doi_raw = str(ids.get("doi") or msg.get("doi") or "")
    doi = extract_doi(doi_raw) or doi_raw.replace("https://doi.org/", "")
    title = str(msg.get("display_name") or msg.get("title") or "")
    authors = []
    for a in (msg.get("authorships") or [])[:8]:
        author = a.get("author") or {}
        name = str(author.get("display_name") or "")
        if name:
            authors.append(name)
    primary = msg.get("primary_location") or {}
    source = primary.get("source") or {}
    url = str(
        primary.get("landing_page_url")
        or ids.get("doi")
        or (f"https://doi.org/{doi}" if doi else "")
        or msg.get("id")
        or ""
    )
    return {
        "title": title,
        "doi": doi,
        "url": url,
        "authors": authors,
        "year": msg.get("publication_year"),
        "container": str(source.get("display_name") or ""),
        "type": str(msg.get("type") or ""),
        "publisher": "",
        "open_access_url": str((msg.get("open_access") or {}).get("oa_url") or ""),
    }
