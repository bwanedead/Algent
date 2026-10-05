"""
The feed catalog: where the desk listens for primary statements. Code-defined, one entry per source.

``kind``: ``feed`` (RSS/Atom), ``listing`` (an HTML index page whose links are the items) or ``json``
(a site's own listing API; ``parser`` names the reader in ``collect.JSON_PARSERS``).
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
    kind: Literal["feed", "listing", "json"] = "feed"
    body: Literal["feed", "page", "ec_api"] = "feed"
    language: str = "en"
    venue_hint: str = "statement"       # what this source mostly is (speech / readout / statement ...)
    skip_title: str = ""                # regex of titles that are never statements (travel advice, lists)
    link_pattern: str = ""              # listing only: regex whose group 1 is the item URL
    date_side: Literal["", "before", "after"] = ""   # listing only: the item's date sits before/after its link in the markup
    rewrite: tuple[str, str] = ("", "")  # (old, new) substring swap on item URLs, when the feed links to dead pages
    parser: str = ""                    # json only: reader name in collect.JSON_PARSERS


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
    # -- the wider table (verified live 2026-10-04; the failures are listed in docs/architecture/statements.md) --
    Source("nato_transcripts", "NATO transcripts (Secretary General speeches and press conferences)", "NATO",
           "https://www.nato.int/content/nato/en/news-and-events/events/transcripts/jcr:content/root/container/"
           "general_search_copy.search.json?searchText=&searchType=wcm&sortBy=dateDesc&pageSize=15&page=1&languages=en",
           kind="json", parser="nato", body="page", venue_hint="speech or press conference"),
    Source("elysee", "Elysee (President Macron)", "France", "https://www.elysee.fr/en/feed", body="page", language="fr",
           rewrite=("/en/emmanuel-macron/", "/emmanuel-macron/"), venue_hint="statement or readout",
           skip_title=r"^Compte rendu du Conseil des ministres|^Nomination|^Décret|^Agenda"),
    Source("presidentti_fi", "President of Finland", "Finland", "https://www.presidentti.fi/en/feed",
           body="feed", venue_hint="speech or statement"),
    Source("pm_au", "Prime Minister of Australia", "Australia", "https://www.pm.gov.au/rss.xml",
           body="page", venue_hint="press conference or release", skip_title=r"^Vale "),
    Source("un_sg", "UN Secretary-General (quotes and remarks)", "United Nations", "https://www.un.org/sg/en/rss.xml",
           body="feed", venue_hint="remarks"),
    Source("auswaertiges_amt", "German Federal Foreign Office (newsroom)", "Germany",
           "https://www.auswaertiges-amt.de/en/newsroom/news", kind="listing", body="page",
           link_pattern=r"/en/newsroom/news/\d{6,}-\d+", skip_title=r"^(Show )?more$", venue_hint="statement or speech"),
    Source("tccb", "Presidency of Turkiye (President Erdogan)", "Turkey", "https://www.tccb.gov.tr/en/news/",
           kind="listing", body="page", link_pattern=r"/en/news/\d+/\d+/[^\"']+", date_side="before",
           venue_hint="speech or readout"),
    Source("kantei", "Prime Minister of Japan (Kantei)", "Japan", "https://japan.kantei.go.jp/", kind="listing",
           body="page", link_pattern=r"/105/(?:statement|speech)/\d{6}/[^\"']+\.html", venue_hint="statement or press remarks"),
    Source("iran_mfa", "Iran Ministry of Foreign Affairs (English)", "Iran", "https://en.mfa.ir/", kind="listing",
           body="page", link_pattern=r"/portal/[Nn]ews[Vv]iew/\d+", date_side="after", venue_hint="statement"),
    Source("brazil_mre", "Brazil Ministry of Foreign Affairs (press notes)", "Brazil",
           "https://www.gov.br/mre/en/contact-us/press-area/press-releases", kind="listing", body="page",
           link_pattern=r"/mre/en/contact-us/press-area/press-releases/[a-z0-9-]{12,}", skip_title=r"^GOV.BR$", venue_hint="note to the press"),
    Source("president_lv", "President of Latvia", "Latvia", "https://www.president.lv/en/articles", kind="listing",
           body="page", link_pattern=r"/en/article/[a-z0-9-]+", skip_title=r"^Photos?\b", venue_hint="statement"),
    Source("mfa_lv", "Latvia Ministry of Foreign Affairs", "Latvia", "https://www.mfa.gov.lv/en/articles", kind="listing",
           body="page", link_pattern=r"/en/article/[a-z0-9-]+", venue_hint="statement"),
)


def by_id(source_id: str) -> Source | None:
    return next((s for s in SOURCES if s.id == source_id), None)
