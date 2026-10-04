"""Library parsing (feed + sitemap, captured real payloads) and the polite-network seam (robots, pacing, validators)."""

from __future__ import annotations

from pathlib import Path

import pytest

from algent_backend.library import net as netmod
from algent_backend.library.parse import ParseError, canonical_url, parse_feed, parse_sitemap
from algent_backend.library.sources import SOURCES, all_sources

FIX = Path(__file__).parent / "fixtures" / "library"


def test_parse_real_rss_feed() -> None:
    cands = parse_feed((FIX / "un_news_feed.xml").read_bytes())
    assert len(cands) >= 10
    assert all(c.url.startswith("http") and c.title and c.published for c in cands)
    assert cands[0].published.endswith("+00:00")          # normalised to UTC ISO


def test_parse_real_news_sitemap_takes_title_and_publication_date() -> None:
    cands = parse_sitemap((FIX / "kyiv_news_sitemap.xml").read_bytes())
    assert len(cands) >= 10
    first = cands[0]
    assert first.title and "&apos;" not in first.title
    assert first.published.startswith("2026-")
    assert first.stamp                                     # lastmod, the change detector


def test_sitemap_index_is_refused_not_followed() -> None:
    index = b'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://x.test/a.xml</loc></sitemap></sitemapindex>'
    with pytest.raises(ParseError, match="index"):
        parse_sitemap(index)


def test_garbage_yields_no_candidates() -> None:
    assert parse_feed(b"<html><body>not a feed</body></html>") == []


def test_canonical_url_drops_fragment_and_tracking() -> None:
    assert canonical_url("https://a.test/p?id=3&utm_source=x#frag") == "https://a.test/p?id=3"


def test_registry_is_consistent() -> None:
    ids = [s.id for s in all_sources()]
    assert len(ids) == len(set(ids)), "source ids must be unique"
    assert len(SOURCES) >= 40
    assert all(s.feeds and s.domains and s.note for s in all_sources())
    assert any(s.id.startswith("stmt_") for s in all_sources()), "statements feeds are read from their catalog"


def test_news_feeds_tool_reads_the_registry() -> None:
    from algent_backend.agent_system.tools.sourcing.discovery.news_feeds import _list_feeds

    feeds = _list_feeds()
    urls = {f["url"] for f in feeds}
    assert "https://feeds.bbci.co.uk/news/world/rss.xml" in urls and "https://www.aljazeera.com/xml/rss/all.xml" in urls
    assert all({"name", "url", "beat", "kind", "region"} <= set(f) for f in feeds)
    assert not any("sitemap" in u for u in urls)           # only RSS/Atom are readable by rss_feed


# -- network seam ----------------------------------------------------------------------------------
class _Clock:
    def __init__(self) -> None:
        self.t, self.slept = 0.0, []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def _net(routes: dict[str, netmod.Response], clock: _Clock | None = None) -> tuple[netmod.Net, list]:
    calls: list = []
    clock = clock or _Clock()

    def http(url: str, headers: dict[str, str]) -> netmod.Response:
        calls.append((url, headers))
        if url not in routes:
            return netmod.Response(404)
        return routes[url]

    return netmod.Net(http=http, sleep=clock.sleep, clock=clock.now), calls


def test_robots_disallow_is_honoured_and_named() -> None:
    robots = b"User-agent: *\nDisallow: /private/\n"
    net, calls = _net({"https://a.test/robots.txt": netmod.Response(200, robots)})
    assert net.allowed("https://a.test/news/1")[0]
    ok, why = net.allowed("https://a.test/private/x")
    assert not ok and "robots" in why
    assert sum(1 for u, _ in calls if u.endswith("robots.txt")) == 1       # cached per origin


def test_robots_for_our_agent_specifically() -> None:
    robots = b"User-agent: OhmegaLibraryBot\nDisallow: /\n"
    net, _ = _net({"https://a.test/robots.txt": netmod.Response(200, robots)})
    assert not net.allowed("https://a.test/anything")[0]


def test_robots_403_closes_the_site_and_404_opens_it() -> None:
    net, _ = _net({"https://closed.test/robots.txt": netmod.Response(403)})
    assert not net.allowed("https://closed.test/x")[0]
    assert net.allowed("https://open.test/x")[0]                           # 404 -> no rules published


def test_pacing_spaces_requests_to_one_host_only() -> None:
    clock = _Clock()
    net, _ = _net({}, clock)
    net.get("https://a.test/1")
    net.get("https://a.test/2")
    net.get("https://b.test/1")
    assert len(clock.slept) == 1 and clock.slept[0] == pytest.approx(netmod.PACE_S, abs=0.01)


def test_conditional_get_sends_validators_and_honest_agent() -> None:
    net, calls = _net({"https://a.test/f": netmod.Response(304)})
    resp = net.get("https://a.test/f", etag='"abc"', last_modified="Sat, 03 Oct 2026 00:00:00 GMT")
    headers = calls[0][1]
    assert resp.status == 304 and headers["If-None-Match"] == '"abc"' and "If-Modified-Since" in headers
    assert "OhmegaLibraryBot" in headers["User-Agent"]
