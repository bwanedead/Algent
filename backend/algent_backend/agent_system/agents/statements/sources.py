"""
The feed catalog: where the desk listens for primary statements. Code-defined, one entry per source.

``kind``: ``feed`` (RSS/Atom) or ``listing`` (an HTML index page whose links are the items).
``body``: where the full text comes from — ``feed`` (the feed entry carries it), ``page`` (a free page
read of the entry URL), or ``ec_api`` (the Commission's press-corner JSON). Anything not verified
working is listed as open in docs/architecture/statements.md, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    affiliation: str                    # country/org speaking, passed to the extractor as context
    url: str
    kind: Literal["feed", "listing"] = "feed"
    body: Literal["feed", "page", "ec_api"] = "feed"
    language: str = "en"
    venue_hint: str = "statement"       # what this source mostly is (speech / readout / statement ...)
    skip_title: str = ""                # regex of titles that are never statements (travel advice, lists)
    link_pattern: str = ""              # listing only: regex whose group 1 is the item URL


SOURCES: tuple[Source, ...] = (
    Source("kremlin_transcripts", "Kremlin: President transcripts", "Russia",
           "http://en.kremlin.ru/events/president/transcripts/feed", body="feed", venue_hint="speech or press event"),
    Source("kremlin_news", "Kremlin: President news", "Russia",
           "http://en.kremlin.ru/events/president/news/feed", body="feed", venue_hint="readout"),
    Source("whitehouse", "White House news", "United States",
           "https://www.whitehouse.gov/news/feed/", body="feed", venue_hint="statement"),
    Source("state_dept", "US State Department press releases", "United States",
           "https://www.state.gov/rss-feed/press-releases/feed/", body="feed", venue_hint="statement or readout"),
    Source("fcdo", "UK Foreign Office (FCDO)", "United Kingdom",
           "https://www.gov.uk/government/organisations/foreign-commonwealth-development-office.atom",
           body="page", venue_hint="statement",
           skip_title=r"travel advice|^Living in |^When someone dies|sanctions (list|notices)|^Guidance:|forms and|information for victims"),
    Source("uk_pmo", "UK Prime Minister's Office", "United Kingdom",
           "https://www.gov.uk/government/organisations/prime-ministers-office-10-downing-street.atom",
           body="page", venue_hint="statement", skip_title=r"^Appointment of |^Transparency data"),
    Source("un_press", "UN press meetings and statements", "United Nations",
           "https://press.un.org/en/rss.xml", body="page", venue_hint="statement"),
    Source("ec_presscorner", "European Commission press corner", "European Union",
           "https://ec.europa.eu/commission/presscorner/api/rss", body="ec_api", venue_hint="statement"),
    Source("china_mfa", "China MFA spokesperson remarks", "China",
           "https://www.mfa.gov.cn/eng/xw/fyrbt/", kind="listing", body="page", venue_hint="press_conference",
           link_pattern=r"t\d{8}_\d+\.html"),
)


def by_id(source_id: str) -> Source | None:
    return next((s for s in SOURCES if s.id == source_id), None)
