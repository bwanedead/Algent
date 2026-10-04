"""
Tests for the cross-run novelty ledger — why the pool stopped repeating itself.

The bug this guards: only GKG had cross-run memory, so channels that harvest the
top-N of a slow source (12 science feeds at 8 entries each, X search, the beat sheet)
re-offered yesterday's items on every run. A weekly journal feed cannot help doing
that; only we know what we already showed.

The load-bearing property is the ORDER of novelty and capping. Filtering after the
cap leaves the cap already spent on repeats, which is a no-op — so that is tested
directly rather than inferred.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from algent_backend.data_ingestion.newsroom.discovery import seen as sn
from algent_backend.data_ingestion.newsroom.discovery.pool import build_pool
from algent_backend.data_ingestion.newsroom.discovery.report import BeatHit, PoolItem


def _item(n: int, url: str | None = None) -> PoolItem:
    return PoolItem(
        id=f"i{n}", label=f"story {n}", channel="science", kind="news",
        evidence=[BeatHit(title=f"story {n}", url=url or f"https://x.test/{n}")],
    )


# -- keys ---------------------------------------------------------------------

def test_url_identifies_the_item() -> None:
    assert sn.item_key(_item(1)) == "x.test/1"


def test_tracking_junk_does_not_make_one_story_look_like_two() -> None:
    a = sn.item_key(_item(1, "https://x.test/1?utm_source=rss&utm_medium=feed"))
    b = sn.item_key(_item(1, "http://www.x.test/1/"))
    assert a == b == "x.test/1"


def test_an_item_with_no_url_falls_back_to_its_id() -> None:
    bare = PoolItem(id="x:novelty:9", label="p", channel="x", kind="post")
    assert sn.item_key(bare) == "x:novelty:9"


# -- ledger -------------------------------------------------------------------

def test_recording_keeps_the_first_date_seen() -> None:
    led = sn.SeenLedger().record(["a"], today="2026-07-01")
    led = led.record(["a", "b"], today="2026-07-05")
    assert led.first_seen == {"a": "2026-07-01", "b": "2026-07-05"}


def test_old_entries_are_forgotten_so_the_file_cannot_grow_forever() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    old = (now - timedelta(days=40)).date().isoformat()
    recent = (now - timedelta(days=2)).date().isoformat()
    led = sn.SeenLedger(first_seen={"old": old, "recent": recent}).pruned(now=now)
    assert set(led.first_seen) == {"recent"}


def test_a_forgotten_item_becomes_discoverable_again() -> None:
    """The horizon is deliberate: a recurring subject should come back around."""
    now = datetime(2026, 7, 20, tzinfo=UTC)
    stale = (now - timedelta(days=sn.DEFAULT_HORIZON_DAYS + 1)).date().isoformat()
    led = sn.SeenLedger(first_seen={"x.test/1": stale}).pruned(now=now)
    assert not led.is_seen("x.test/1")


def test_ledger_survives_a_round_trip(tmp_path) -> None:
    sn.save_seen(sn.SeenLedger(first_seen={"a": "2026-07-01"}), tmp_path)
    assert sn.load_seen(tmp_path).first_seen == {"a": "2026-07-01"}


def test_a_missing_or_corrupt_ledger_is_empty_not_fatal(tmp_path) -> None:
    assert sn.load_seen(tmp_path).first_seen == {}
    (tmp_path / sn.FILENAME).write_text("{not json", encoding="utf-8")
    assert sn.load_seen(tmp_path).first_seen == {}


# -- ordering in the pool -----------------------------------------------------

#: Deliberately unlike each other. The pool runs echo suppression across channels, and
#: near-identical titles ("story 1", "story 2") collapse into one item — which silently
#: emptied an earlier version of these tests and had nothing to do with novelty.
_TITLES = (
    "Baby tyrannosaur teeth reveal an early feeding shift",
    "Frost-brightened dunes explain a Martian sheen",
    "Open peer review correlates with fewer retractions",
    "Seals evolved amphibious hearing far earlier",
    "A wandering black hole shreds a passing star",
    "Matcha genomics races a warming climate",
    "Charcoal dating pushes cave art back millennia",
    "Misfolded insulin may quietly drive diabetes",
    "Sargassum belt swells across the tropical Atlantic",
)


def _science_hits(n: int) -> list[dict]:
    return [{"title": _TITLES[i - 1], "url": f"https://x.test/{i}", "feed": "f",
             "pillar": "science"}
            for i in range(1, n + 1)]


def _nth(item) -> int:
    """Which fixture an item came from, by its URL tail."""
    return int(str(item.evidence[0].url).rsplit("/", 1)[-1])


def test_fresh_items_take_the_cap_before_repeats() -> None:
    """The whole fix. Items 1-6 were seen; the cap is 3; all three slots must be NEW."""
    ledger = sn.SeenLedger(first_seen={f"x.test/{i}": "2026-07-01" for i in range(1, 7)})
    pool = build_pool(None, None, science=_science_hits(9), science_limit=3, ledger=ledger)

    assert len(pool.items) == 3
    assert all(_nth(i) > 6 for i in pool.items), [i.label for i in pool.items]


def test_repeats_still_fill_the_pool_on_a_quiet_day() -> None:
    """Demoted, never deleted — a slow day should still produce a full menu."""
    ledger = sn.SeenLedger(first_seen={f"x.test/{i}": "2026-07-01" for i in range(1, 6)})
    pool = build_pool(None, None, science=_science_hits(5), science_limit=4, ledger=ledger)

    assert len(pool.items) == 4                       # not emptied
    assert all((i.signals or {}).get("seen_before") for i in pool.items)


def test_repeats_are_marked_so_the_menu_is_honest() -> None:
    ledger = sn.SeenLedger(first_seen={"x.test/1": "2026-07-01"})
    pool = build_pool(None, None, science=_science_hits(2), science_limit=2, ledger=ledger)

    signals = {_nth(i): (i.signals or {}) for i in pool.items}
    assert signals[1].get("seen_before") is True
    assert "seen_before" not in signals[2]


def test_no_ledger_means_no_change_in_behaviour() -> None:
    pool = build_pool(None, None, science=_science_hits(4), science_limit=4)
    assert len(pool.items) == 4
    assert not any((i.signals or {}).get("seen_before") for i in pool.items)
