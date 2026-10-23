"""
What the smoke test asks a site for, derived rather than listed by hand:

* every static page route of every product in the registry (``site_routes``; a new page is checked the day it is registered),
* a sample of each dynamic route, taken from the site's own sitemap (the newest date per desk, one situation, one country, one article ...),
* the agent API (``/api/v1`` index, search, entity, about, series, the newest daily per desk, the freshness endpoints),
* the retired routes that must keep redirecting.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote, urlparse

from algent_backend.ops.products import views
from algent_backend.views import flags as view_flags

from . import flags

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Probe:
    path: str                              # path and query, no host
    kind: str                              # page | api | json | xml | text | redirect
    why: str = ""                          # where it came from (a product, a sample, the agent API)
    expect: str = ""                       # redirect: the exact destination path; text: a string the body must contain
    fresh: tuple[str, str] | None = None   # (registry product id, severity when late)


def desks() -> list[str]:
    return [d["id"] for d in view_flags.DESKS]


def static_probes() -> list[Probe]:
    """Registry routes without a parameter, the machine-readable endpoints, the agent API and the retired redirects."""
    seen: dict[str, Probe] = {}
    for p in views.products():
        for route in p.site_routes:
            if "[" not in route:
                seen.setdefault(route, Probe(route, "page", f"registry: {p.id}"))
    out = list(seen.values())
    out += [Probe("/sitemap.xml", "xml", "sitemap"), Probe("/feed.xml", "xml", "feed"), Probe("/robots.txt", "text", "robots", expect="Sitemap"),
            Probe("/llms-full.txt", "text", "llms")]
    q = quote(flags.ENTITY_PROBE)
    out += [Probe("/api/v1", "api", "agent API index"), Probe("/api/v1/openapi.json", "json", "agent API spec"),
            Probe(f"/api/v1/search?q={q}", "api", "agent API search"), Probe(f"/api/v1/entity?name={q}", "api", "agent API entity"),
            Probe(f"/api/v1/about?entity={q}", "api", "agent API about"), Probe("/api/v1/series?metric=gdp", "api", "agent API series"),
            Probe("/api/v1/theaters?limit=1", "api", "agent API theaters")]
    api_paths = {p.path for p in out}
    for tmpl, product, severity in flags.FRESHNESS:
        for path in ([tmpl.format(desk=d) for d in desks()] if "{desk}" in tmpl else [tmpl]):
            if path in api_paths:
                continue
            out.append(Probe(path, "api", f"freshness: {product}", fresh=(product, severity)))
    out += [Probe(src, "redirect", "retired route", expect=dest) for src, dest in flags.REDIRECTS]
    return out


def sitemap_paths(xml_text: str) -> list[str]:
    """The paths in a sitemap, in document order. The host is dropped: a preview's sitemap names the canonical origin, not its own."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    return [urlparse(loc.text.strip()).path or "/" for loc in root.iter() if loc.tag.endswith("loc") and loc.text]


def _sample(paths: list[str]) -> list[str]:
    """One path per group (a group shares the template's parent path): the newest if the leaf is a date, else the first in sitemap order."""
    groups: dict[str, list[str]] = {}
    for p in paths:
        groups.setdefault(p.rpartition("/")[0], []).append(p)
    out = []
    for _parent, items in list(groups.items())[: flags.MAX_GROUPS]:
        dated = [i for i in items if _DATE.match(i.rpartition("/")[2])]
        out += sorted(dated, reverse=True)[: flags.SAMPLES_PER_GROUP] if dated else items[: flags.SAMPLES_PER_GROUP]
    return out


def dynamic_probes(sitemap_xml: str) -> tuple[list[Probe], list[str]]:
    """(samples of every dynamic route, the templates for which no sample could be found). A template the sitemap does not list is filled from the
    desks when its only parameter is ``[desk]``; otherwise it is reported as unsampled (a note, not a failure)."""
    paths = sitemap_paths(sitemap_xml)
    out: list[Probe] = []
    missing: list[str] = []
    seen: set[str] = set()
    for p in views.products():
        for route in p.site_routes:
            if "[" not in route or route in seen:
                continue
            seen.add(route)
            pattern = views.route_pattern(route)
            found = [x for x in paths if pattern.match(x)]
            if not found and re.fullmatch(r"[^\[]*\[desk\][^\[]*", route):
                found = [route.replace("[desk]", d) for d in desks()]
            if not found:
                missing.append(route)
                continue
            out += [Probe(x, "page", f"sample of {route}") for x in _sample(found)]
    iso = next((x.rpartition("/")[2] for x in (q.path for q in out) if x.startswith("/intel/actors/")), "")
    if iso:
        out.append(Probe(f"/api/globe/country/{iso}", "json", "sample of the globe country panel"))
    return out, missing
