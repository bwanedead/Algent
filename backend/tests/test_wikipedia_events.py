"""
Tests for the Wikipedia Current Events parser.

The one property that matters: entries NEST, and only the deepest one is a real event.
Outer list items are topic breadcrumbs, so a parser that collects every ``<li>`` returns
three fragments of topic label for every actual occurrence. The discriminator is the
citation — a leaf carries an external link and breadcrumbs do not — so that is what is
pinned here, on markup shaped exactly like the live portal's.
"""

from __future__ import annotations

from datetime import UTC, datetime

from algent_backend.data_ingestion.newsroom.sources import wikipedia_events as we

# Shaped from the real page: a three-level breadcrumb chain ending in one cited event.
_NESTED = """
<div class="current-events-content description">
<p><b>Armed conflicts and attacks</b></p>
<ul><li><a href="/wiki/Middle_Eastern_crisis">Middle Eastern crisis</a>
<ul><li><a href="/wiki/Gaza_war">Gaza war</a>
<ul><li><a href="/wiki/Attacks_on_religious_sites">Attacks on religious sites</a>
<ul><li><a href="/wiki/Israeli_forces">Israeli forces</a> strike a mosque in Gaza City in
violation of the ongoing ceasefire, accusing Hamas of storing weapons there.
<a rel="nofollow" class="external text" href="https://www.nytimes.com/x.html">(<i>NYT</i>)</a>
</li></ul></li></ul></li></ul>
</div>
"""


def test_only_the_cited_leaf_becomes_an_event() -> None:
    events = we.parse_portal(_NESTED)
    assert len(events) == 1
    assert events[0]["text"].startswith("Israeli forces strike a mosque in Gaza City")
    assert events[0]["url"] == "https://www.nytimes.com/x.html"


def test_breadcrumbs_are_kept_as_a_free_topic_path() -> None:
    """Volunteers already filed the event under a topic hierarchy — that is worth having."""
    assert we.parse_portal(_NESTED)[0]["breadcrumbs"] == [
        "Middle Eastern crisis", "Gaza war", "Attacks on religious sites",
    ]


def test_the_leaf_text_excludes_its_ancestors_labels() -> None:
    """Text accumulates into the innermost item only; otherwise every event would be
    prefixed with the whole breadcrumb chain."""
    text = we.parse_portal(_NESTED)[0]["text"]
    assert "Gaza war" not in text
    assert "Middle Eastern crisis" not in text


def test_the_trailing_citation_label_is_stripped() -> None:
    assert not we.parse_portal(_NESTED)[0]["text"].endswith("(NYT)")


def test_the_category_heading_is_captured() -> None:
    assert we.parse_portal(_NESTED)[0]["category"] == "Armed conflicts and attacks"


def test_an_uncited_item_is_not_an_event() -> None:
    """No citation means it is a breadcrumb or a stub, not something that happened."""
    html = """<div class="current-events-content"><p><b>Politics and elections</b></p>
    <ul><li>A long line of text with no citation attached to it whatsoever here.</li></ul>
    </div>"""
    assert we.parse_portal(html) == []


def test_a_cited_stub_is_too_short_to_be_an_event() -> None:
    html = """<div class="current-events-content"><p><b>Sports</b></p>
    <ul><li>Short. <a class="external text" href="https://x.test/a">(<i>S</i>)</a></li></ul>
    </div>"""
    assert we.parse_portal(html) == []


def test_content_outside_the_events_block_is_ignored() -> None:
    """The page ships stylesheet and navigation markup with its own lists."""
    html = """<div class="current-events-navbar"><ul><li>
    Some navigation text long enough to pass the length floor for an entry here.
    <a class="external text" href="https://x.test/edit">(<i>edit</i>)</a></li></ul></div>"""
    assert we.parse_portal(html) == []


def test_malformed_markup_does_not_raise() -> None:
    assert we.parse_portal('<div class="current-events-content"><ul><li>unclosed') == []


# -- fetch shaping ------------------------------------------------------------

class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _Client:
    """Serves one day of portal HTML and reports a missing page for the other."""

    def __init__(self, html: str):
        self._html = html
        self.pages: list[str] = []

    def get(self, _url, params=None, **_kw):
        page = (params or {}).get("page", "")
        self.pages.append(page)
        if page.endswith("_29"):
            return _Response({"parse": {"text": self._html}})
        return _Response({"error": {"code": "missingtitle"}})

    def close(self):
        pass


def _fetch(html: str, **kw):
    client = _Client(html)
    hits = we.fetch_current_events(
        client=client, now=datetime(2026, 7, 29, tzinfo=UTC), **kw)
    return hits, client


def test_a_missing_day_is_skipped_not_fatal() -> None:
    """The portal page for a day may not exist yet — that is normal, not an error."""
    hits, client = _fetch(_NESTED, days=2)
    assert len(client.pages) == 2                       # both days attempted
    assert len(hits) == 1                               # only the one that existed


def test_hits_carry_the_pillar_and_the_world_channel() -> None:
    hits, _ = _fetch(_NESTED, days=1)
    assert hits[0]["pillar"] == "geopolitics"
    assert hits[0]["group"] == "world"
    assert hits[0]["seendate"] == "2026-07-29"


def test_sports_is_excluded() -> None:
    html = _NESTED.replace("Armed conflicts and attacks", "Sports")
    hits, _ = _fetch(html, days=1)
    assert hits == []


def test_an_unmapped_category_gets_no_pillar_rather_than_a_wrong_one() -> None:
    html = _NESTED.replace("Armed conflicts and attacks", "Something Unforeseen")
    hits, _ = _fetch(html, days=1)
    assert hits[0]["pillar"] == ""


def test_page_titles_match_the_portals_own_naming() -> None:
    """No zero padding, full month name — get this wrong and every day 404s."""
    assert we._page_for(datetime(2026, 7, 5, tzinfo=UTC)) == "Portal:Current_events/2026_July_5"
