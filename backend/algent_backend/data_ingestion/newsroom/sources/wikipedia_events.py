"""
Wikipedia's Current Events portal — a human-curated ledger of what happened today.

Every other discovery channel answers "what is being *covered*". GKG and the beat sweep
read a wire corpus and measure amplification; feeds report each outlet's own editorial
picks; markets price expectations. All of them inherit somebody's publication incentives,
which is why discovery kept converging on the same super-topics.

This one is different in kind. Volunteers maintain a daily page of *events that occurred*,
each with a citation, organised by category (armed conflicts, disasters, politics, science
and technology, business). It is the closest freely available thing to "the day's record"
rather than "the day's coverage", and it is global by construction rather than by our
choosing which foreign outlets to add.

Two properties make it unusually good for us:

- **It is a list of events, not headlines.** Entries read "Israeli forces strike a mosque
  in Gaza City in violation of the ongoing ceasefire" — a described occurrence, which is
  much closer to what synthesis wants than a wire headline is.
- **It carries the source with it.** Each entry cites the outlet that reported it, so a
  lead arrives with its first-hop attribution already attached.

## Structure, and the one thing that matters when parsing it

Entries nest. The outer list items are topic breadcrumbs and the DEEPEST item is the actual
event:

    Middle Eastern crisis            <- breadcrumb
      Gaza war                       <- breadcrumb
        Attacks on religious sites   <- breadcrumb
          Israeli forces strike ...  <- the event, with a citation link

So a naive "collect every <li>" yields three fragments of topic label for every real event.
The discriminator is the citation: a leaf carries an external link, breadcrumbs do not. The
breadcrumbs are still worth keeping — they are a free, human-assigned topic path.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

SOURCE_ID = "wikipedia_events"

_API = "https://en.wikipedia.org/w/api.php"
_TIMEOUT_S = 25.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}

#: How many days back to read. Two, because the portal for "today" is thin early in the UTC
#: day and an operator running in the morning would otherwise see almost nothing.
DEFAULT_DAYS = 2

#: An entry has to be a sentence about something, not a stub. Tuned to the portal's own
#: style: real entries run well past this, orphaned label fragments do not.
_MIN_CHARS = 45

#: Categories we never want. Sports is a standing exclusion across the newsroom, and the
#: portal files a lot of it — a live two-day sample was 1 of 16 entries.
_SKIP_CATEGORIES = frozenset({"sports"})

#: The portal's category headings map onto our pillars. Anything unlisted keeps no pillar
#: rather than being forced into one — a wrong pillar is worse than none.
_PILLARS = {
    "armed conflicts and attacks": "geopolitics",
    "arts and culture": "culture",
    "business and economy": "economics",
    "disasters and accidents": "environment",
    "health and environment": "health",
    "international relations": "geopolitics",
    "law and crime": "politics",
    "politics and elections": "politics",
    "science and technology": "science",
    "sports": "sports",
}

#: The trailing "(The New York Times)" citation, which is furniture once we have the URL.
_TRAILING_CITE = re.compile(r"\s*\((?:[^()]*)\)\s*$")


class _PortalParser(HTMLParser):
    """Pull ``(text, url, category, breadcrumbs)`` for each cited leaf entry."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[dict[str, Any]] = []
        self._in_content = False
        self._depth = 0            # div nesting inside the content block, to know when it ends
        self._category = ""
        self._in_heading = False
        # One text buffer per open <li>. Text lands in the INNERMOST buffer only, so an outer
        # item collects just its own label and the leaf collects just the event sentence.
        self._li_text: list[list[str]] = []
        self._li_url: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = attr.get("class", "")

        if tag == "div":
            if self._in_content:
                self._depth += 1
            elif "current-events-content" in classes:
                self._in_content = True
                self._depth = 1
            return
        if not self._in_content:
            return
        if tag == "b" and not self._li_text:
            self._in_heading = True      # a bold run outside any list item is a category
            self._category = ""
        elif tag == "li":
            self._li_text.append([])
            self._li_url.append("")
        elif tag == "a" and self._li_text:
            href = attr.get("href", "")
            # An external citation marks this item as a real event; internal /wiki/ links are
            # just the portal's usual heavy cross-linking and say nothing about leaf-ness.
            if "external" in classes and href.startswith("http"):
                self._li_url[-1] = href

    def handle_endtag(self, tag: str) -> None:
        if not self._in_content:
            return
        if tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self._in_content = False
            return
        if tag == "b":
            self._in_heading = False
        elif tag == "li" and self._li_text:
            text = " ".join("".join(self._li_text.pop()).split())
            url = self._li_url.pop()
            if url and len(text) >= _MIN_CHARS:
                self.events.append({
                    "text": _TRAILING_CITE.sub("", text).strip(),
                    "url": url,
                    "category": self._category,
                    # Ancestors' own labels, outermost first — a free human topic path.
                    "breadcrumbs": [
                        " ".join("".join(buf).split())
                        for buf in self._li_text if "".join(buf).strip()
                    ],
                })

    def handle_data(self, data: str) -> None:
        if not self._in_content:
            return
        if self._in_heading:
            self._category += data
        elif self._li_text:
            self._li_text[-1].append(data)


def parse_portal(html: str) -> list[dict[str, Any]]:
    """Parse one day's portal HTML into cited event entries."""
    parser = _PortalParser()
    parser.feed(html)
    return parser.events


def _page_for(day: datetime) -> str:
    # The portal's own naming: "Portal:Current_events/2026_July_29" (no zero padding).
    return f"Portal:Current_events/{day.year}_{day.strftime('%B')}_{day.day}"


def fetch_current_events(
    *, days: int = DEFAULT_DAYS, client: object | None = None, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Recent days of the Current Events portal as discovery hits. A missing day is skipped."""
    import httpx

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS, follow_redirects=True)
    today = now or datetime.now(UTC)
    hits: list[dict[str, Any]] = []
    try:
        for back in range(max(1, days)):
            day = today - timedelta(days=back)
            try:
                response = http.get(_API, params={  # type: ignore[attr-defined]
                    "action": "parse", "page": _page_for(day), "format": "json",
                    "prop": "text", "formatversion": "2", "redirects": "1",
                })
                if getattr(response, "status_code", 0) != 200:
                    continue
                payload = response.json()
                if "error" in payload:      # the page for a day may not exist yet
                    continue
                html = payload["parse"]["text"]
            except Exception:  # noqa: BLE001 — one bad day is one fewer, never an error
                continue
            stamp = day.date().isoformat()
            for event in parse_portal(html):
                category = event["category"].strip().casefold()
                if category in _SKIP_CATEGORIES:
                    continue
                hits.append({
                    "title": event["text"],
                    "url": event["url"],
                    "feed": "wikipedia_events",
                    "pillar": _PILLARS.get(category, ""),
                    "group": "world",
                    "category": event["category"].strip(),
                    "breadcrumbs": event["breadcrumbs"],
                    "seendate": stamp,
                })
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]
    return hits
