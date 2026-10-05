"""
The source registry: every outlet and institution the library indexes. Code-defined, curated, canonical.

This is THE catalog of trusted feeds. ``news_feeds`` (the agent's feed lister) reads from it, and the
statements desk's feeds are folded in (``statement_sources``) rather than copied, so there is one place
to add or retire a feed. Every entry was verified to answer with fresh items on 2026-10-04; feeds that
did not (403 to an honest bot user-agent, 404, empty, stale) are listed as open in
docs/architecture/library.md, not here.

``kind`` drives ranking (primary sources outrank news — see ``search.KIND_WEIGHT``) and retention:
government, ministry, international_org, central_bank, statistics_office (primary record);
think_tank, research, ngo (analysis); wire, regional_news (coverage). ``note`` says why it is trusted
and, for state-affiliated outlets, whose voice it is — the source-spectrum rule wants those labelled,
not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FeedType = Literal["rss", "sitemap"]

PRIMARY_KINDS = frozenset({"government", "ministry", "international_org", "central_bank", "statistics_office"})
ANALYSIS_KINDS = frozenset({"think_tank", "research", "ngo"})


@dataclass(frozen=True)
class Feed:
    url: str
    type: FeedType = "rss"          # "sitemap" = a Google-News-style urlset (loc + news:title + publication_date)
    beat: str = "world"
    crawl: bool = True              # False: listed for ``news_feeds`` readers only (paywalled / not indexed)


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    domains: tuple[str, ...]
    kind: str
    region: str
    feeds: tuple[Feed, ...]
    note: str
    language: str = "en"


def _s(id: str, name: str, domain: str, kind: str, region: str, feeds: tuple[Feed, ...] | Feed | str, note: str,
       language: str = "en", *more_domains: str) -> Source:
    fs = (Feed(feeds),) if isinstance(feeds, str) else (feeds,) if isinstance(feeds, Feed) else feeds
    return Source(id, name, (domain, *more_domains), kind, region, fs, note, language)


def _rss(url: str, beat: str = "world", crawl: bool = True) -> Feed:
    return Feed(url, "rss", beat, crawl)


def _map(url: str, beat: str = "world") -> Feed:
    return Feed(url, "sitemap", beat)


SOURCES: tuple[Source, ...] = (
    # -- international organisations -------------------------------------------------------------
    _s("un_news", "UN News", "news.un.org", "international_org", "global",
       "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "the UN's own newsroom: agency and Secretariat reporting"),
    _s("reliefweb", "ReliefWeb updates", "reliefweb.int", "international_org", "global",
       _rss("https://reliefweb.int/updates/rss.xml", "humanitarian"), "OCHA's humanitarian clearing house; situation reports by agencies"),
    _s("ocha", "UN OCHA", "unocha.org", "international_org", "global",
       _rss("https://www.unocha.org/rss.xml", "humanitarian"), "UN humanitarian coordination: first-party figures on crises"),
    _s("iaea", "IAEA", "iaea.org", "international_org", "global",
       _rss("https://www.iaea.org/feeds/topnews", "nuclear"), "the nuclear watchdog: safeguards, plant-safety statements"),
    _s("icrc", "ICRC", "icrc.org", "international_org", "global",
       _rss("https://www.icrc.org/en/rss/news", "humanitarian"), "neutral humanitarian actor in conflicts"),
    _s("wto", "WTO news", "wto.org", "international_org", "global",
       _rss("https://www.wto.org/library/rss/latest_news_e.xml", "trade"), "trade rules body: disputes, forecasts"),
    _s("eu_council", "Council of the EU press", "consilium.europa.eu", "international_org", "europe",
       _rss("https://www.consilium.europa.eu/en/rss/pressreleases.ashx", "politics"), "member-state decisions, sanctions listings"),
    # -- central banks ---------------------------------------------------------------------------
    _s("fed", "Federal Reserve press", "federalreserve.gov", "central_bank", "north_america",
       _rss("https://www.federalreserve.gov/feeds/press_all.xml", "economy"), "FOMC statements and Board releases"),
    _s("fed_speeches", "Federal Reserve speeches", "federalreserve.gov", "central_bank", "north_america",
       _rss("https://www.federalreserve.gov/feeds/speeches.xml", "economy"), "Governors' and Chair's speeches"),
    _s("ecb", "ECB press", "ecb.europa.eu", "central_bank", "europe",
       _rss("https://www.ecb.europa.eu/rss/press.html", "economy"), "ECB decisions, speeches, interviews"),
    _s("boe", "Bank of England news", "bankofengland.co.uk", "central_bank", "europe",
       _rss("https://www.bankofengland.co.uk/rss/news", "economy"), "MPC decisions and publications"),
    _s("boe_speeches", "Bank of England speeches", "bankofengland.co.uk", "central_bank", "europe",
       _rss("https://www.bankofengland.co.uk/rss/speeches", "economy"), "Governor / MPC speeches"),
    _s("boj", "Bank of Japan", "boj.or.jp", "central_bank", "asia",
       _rss("https://www.boj.or.jp/en/rss/whatsnew.xml", "economy"), "BoJ policy statements and releases"),
    _s("bis_speeches", "BIS central bank speeches", "bis.org", "central_bank", "global",
       _rss("https://www.bis.org/doclist/cbspeeches.rss", "economy"), "speeches by central bankers worldwide, collected by the BIS"),
    # -- governments and ministries (statement feeds are added by ``statement_sources``) ---------
    _s("us_dod", "US Department of War/Defense", "defense.gov", "ministry", "north_america",
       _rss("https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10", "defence"), "Pentagon releases and statements", "en", "war.gov"),
    _s("uk_mod", "UK Ministry of Defence", "gov.uk", "ministry", "europe",
       _rss("https://www.gov.uk/government/organisations/ministry-of-defence.atom", "defence"), "UK defence releases and intelligence updates"),
    _s("eia", "US EIA Today in Energy", "eia.gov", "statistics_office", "north_america",
       _rss("https://www.eia.gov/rss/todayinenergy.xml", "energy"), "US energy statistics agency: data-led notes"),
    _s("us_treasury", "US Treasury press", "home.treasury.gov", "ministry", "north_america",
       _rss("https://home.treasury.gov/news/press-releases/rss.xml", "economy"), "sanctions and financial announcements (slow host; may time out)"),
    # -- think tanks, research, NGOs -------------------------------------------------------------
    _s("crisisgroup", "International Crisis Group", "crisisgroup.org", "think_tank", "global",
       _rss("https://www.crisisgroup.org/rss.xml", "conflict"), "field-based conflict analysis"),
    _s("atlanticcouncil", "Atlantic Council", "atlanticcouncil.org", "think_tank", "north_america",
       _rss("https://www.atlanticcouncil.org/feed/", "security"), "transatlantic security and economics (Western-aligned)"),
    _s("warontherocks", "War on the Rocks", "warontherocks.com", "research", "north_america",
       _rss("https://warontherocks.com/feed/", "defence"), "practitioner defence and strategy commentary"),
    _s("lowy", "Lowy Interpreter", "lowyinstitute.org", "think_tank", "oceania",
       _rss("https://www.lowyinstitute.org/the-interpreter/rss.xml", "asia-pacific"), "Australian view on Indo-Pacific affairs"),
    _s("bellingcat", "Bellingcat", "bellingcat.com", "research", "global",
       _rss("https://www.bellingcat.com/feed/", "osint"), "open-source investigations with shown methods"),
    _s("hrw", "Human Rights Watch", "hrw.org", "ngo", "global",
       _rss("https://www.hrw.org/rss", "rights"), "documented rights abuses; advocacy organisation"),
    _s("amnesty", "Amnesty International", "amnesty.org", "ngo", "global",
       _rss("https://www.amnesty.org/en/latest/feed/", "rights"), "documented rights abuses; advocacy organisation"),
    # -- wires and broad outlets (RSS; some also by news sitemap) --------------------------------
    _s("aljazeera", "Al Jazeera", "aljazeera.com", "wire", "middle_east",
       (_rss("https://www.aljazeera.com/xml/rss/all.xml"), _map("https://www.aljazeera.com/news-sitemap.xml")),
       "Qatar-funded; strong Middle East / Global South reach"),
    _s("bbc", "BBC News", "bbc.com", "wire", "europe",
       (_rss("https://feeds.bbci.co.uk/news/world/rss.xml"), _rss("https://feeds.bbci.co.uk/news/business/rss.xml", "business"),
        _rss("https://feeds.bbci.co.uk/news/technology/rss.xml", "tech"), _map("https://www.bbc.com/sitemaps/https-sitemap-com-news-1.xml")),
       "UK public broadcaster; wide bureau network", "en", "bbc.co.uk"),
    _s("guardian", "The Guardian", "theguardian.com", "wire", "europe",
       (_rss("https://www.theguardian.com/world/rss"), _map("https://www.theguardian.com/sitemaps/news.xml")),
       "UK paper, left-liberal editorial line"),
    _s("dw", "Deutsche Welle", "dw.com", "wire", "europe",
       "https://rss.dw.com/rdf/rss-en-all", "German public international broadcaster"),
    _s("france24", "France 24", "france24.com", "wire", "europe",
       "https://www.france24.com/en/rss", "French state international broadcaster; Africa/Mideast reach"),
    _s("npr", "NPR", "npr.org", "wire", "north_america",
       _rss("https://feeds.npr.org/1004/rss.xml"), "US public radio, world desk"),
    _s("kyivindependent", "Kyiv Independent", "kyivindependent.com", "regional_news", "europe",
       (_rss("https://kyivindependent.com/news-archive/rss/"), _map("https://kyivindependent.com/news-sitemap.xml")),
       "Ukrainian English-language outlet; the war from the Ukrainian side"),
    _s("almonitor", "Al-Monitor", "al-monitor.com", "regional_news", "middle_east",
       "https://www.al-monitor.com/rss", "Middle East coverage drawing on regional journalists"),
    _s("mee", "Middle East Eye", "middleeasteye.net", "regional_news", "middle_east",
       "https://www.middleeasteye.net/rss", "London-based; Middle East, critical of Gulf and Western governments"),
    _s("jpost", "Jerusalem Post", "jpost.com", "regional_news", "middle_east",
       "https://www.jpost.com/rss/rssfeedsfrontpage.aspx", "Israeli daily, centre-right"),
    _s("aa", "Anadolu Agency", "aa.com.tr", "wire", "middle_east",
       "https://www.aa.com.tr/en/rss/default?cat=world", "Turkish state news agency: Ankara's framing, wide Turkey/Gulf/Africa coverage"),
    _s("arabnews", "Arab News", "arabnews.com", "regional_news", "middle_east",
       "https://www.arabnews.com/rss.xml", "Saudi-based English daily; Riyadh-aligned"),
    _s("tass", "TASS", "tass.com", "wire", "europe",
       "https://tass.com/rss/v2.xml", "Russian state news agency: the Kremlin's account, not a neutral record"),
    _s("moscowtimes", "The Moscow Times", "themoscowtimes.com", "regional_news", "europe",
       "https://www.themoscowtimes.com/rss/news", "independent Russia coverage, now run from exile"),
    _s("meduza", "Meduza", "meduza.io", "regional_news", "europe",
       "https://meduza.io/rss/en/all", "Russian independent outlet in exile"),
    _s("politico_eu", "Politico Europe", "politico.eu", "regional_news", "europe",
       "https://www.politico.eu/feed/", "Brussels policy and politics"),
    _s("scmp", "South China Morning Post", "scmp.com", "regional_news", "asia",
       _rss("https://www.scmp.com/rss/91/feed"), "Hong Kong daily, Alibaba-owned; China/Asia reach"),
    _s("thehindu", "The Hindu", "thehindu.com", "regional_news", "asia",
       (_rss("https://www.thehindu.com/news/international/feeder/default.rss"),
        _map("https://www.thehindu.com/sitemap/googlenews/all/all.xml")), "Indian national daily; South Asia vantage"),
    _s("dawn", "Dawn", "dawn.com", "regional_news", "asia",
       "https://www.dawn.com/feeds/home", "Pakistani national daily"),
    _s("cna", "CNA (Channel NewsAsia)", "channelnewsasia.com", "regional_news", "asia",
       "https://www.channelnewsasia.com/rssfeeds/8395986", "Singapore-based; Southeast Asia"),
    _s("straitstimes", "The Straits Times", "straitstimes.com", "regional_news", "asia",
       "https://www.straitstimes.com/news/world/rss.xml", "Singapore daily; ASEAN/China reach"),
    _s("japantimes", "The Japan Times", "japantimes.co.jp", "regional_news", "asia",
       "https://www.japantimes.co.jp/feed/", "Japan's English daily"),
    _s("yonhap", "Yonhap News", "en.yna.co.kr", "wire", "asia",
       "https://en.yna.co.kr/RSS/news.xml", "South Korean news agency"),
    _s("taipeitimes", "Taipei Times", "taipeitimes.com", "regional_news", "asia",
       "https://www.taipeitimes.com/xml/index.rss", "Taiwan daily; cross-strait coverage"),
    _s("cgtn", "CGTN", "cgtn.com", "wire", "asia",
       "https://www.cgtn.com/subscribe/rss/section/world.xml", "Chinese state broadcaster: Beijing's framing"),
    _s("thediplomat", "The Diplomat", "thediplomat.com", "regional_news", "asia",
       "https://thediplomat.com/feed/", "Asia-Pacific politics and security magazine"),
    _s("abc_au", "ABC News (Australia)", "abc.net.au", "wire", "oceania",
       "https://www.abc.net.au/news/feed/2942460/rss.xml", "Australian public broadcaster"),
    _s("africanews", "Africanews", "africanews.com", "regional_news", "africa",
       "https://www.africanews.com/feed/rss", "pan-African English/French service"),
    _s("allafrica", "allAfrica", "allafrica.com", "regional_news", "africa",
       "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", "aggregator of African publishers"),
    _s("premiumtimes", "Premium Times (Nigeria)", "premiumtimesng.com", "regional_news", "africa",
       "https://www.premiumtimesng.com/feed", "Nigerian independent investigative daily"),
    _s("dailymaverick", "Daily Maverick", "dailymaverick.co.za", "regional_news", "africa",
       "https://www.dailymaverick.co.za/dmrss/", "South African independent daily"),
    _s("mercopress", "MercoPress", "en.mercopress.com", "regional_news", "latin_america",
       "https://en.mercopress.com/rss", "South Atlantic and Mercosur news"),
    # Listed for ``news_feeds`` readers, not indexed (paywalled: a page read returns a stub).
    Source("nyt", "New York Times", ("nytimes.com",), "wire", "north_america",
           (_rss("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", crawl=False),
            _rss("https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "business", crawl=False)),
           "US paper of record; paywalled, so listed for headlines only"),
)

#: How the statements desk's feeds map onto the library's taxonomy (the feed URLs stay theirs).
_STATEMENT_KINDS: dict[str, tuple[str, str]] = {
    "kremlin_transcripts": ("government", "europe"), "kremlin_news": ("government", "europe"),
    "whitehouse": ("government", "north_america"), "state_dept": ("ministry", "north_america"),
    "fcdo": ("ministry", "europe"), "uk_pmo": ("government", "europe"),
    "un_press": ("international_org", "global"), "ec_presscorner": ("international_org", "europe"),
}


def statement_sources() -> tuple[Source, ...]:
    """The statements desk's RSS/Atom feeds as library sources — read from its catalog, not copied."""
    from urllib.parse import urlsplit

    from algent_backend.agent_system.agents.statements.sources import SOURCES as STATEMENTS

    out = []
    for s in STATEMENTS:
        if s.kind != "feed" or s.id not in _STATEMENT_KINDS:
            continue
        kind, region = _STATEMENT_KINDS[s.id]
        out.append(Source(f"stmt_{s.id}", s.name, (urlsplit(s.url).netloc,), kind, region, (Feed(s.url, "rss", "statements"),),
                          f"primary statements ({s.affiliation}); shared with the statements ledger"))
    return tuple(out)


def all_sources() -> tuple[Source, ...]:
    return (*SOURCES, *statement_sources())


def by_id(source_id: str) -> Source | None:
    return next((s for s in all_sources() if s.id == source_id), None)


def domain_index() -> dict[str, Source]:
    """host -> source, for attributing a bare URL (a host also matches its sub-domains)."""
    return {d: s for s in all_sources() for d in s.domains}
