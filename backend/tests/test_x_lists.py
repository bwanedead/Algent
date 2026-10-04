"""
Tests for the X list band — roster file, collect-everything policy, interleave, dedup.

Every one of these pins something found by running the band against three real lists.
None was theoretical: the first two lists in the roster consumed the entire budget and
left the third with nothing; one account belonged to all three lists so its posts arrived
three times; and quote-tweets whose own text was "Wow. Super cool." carried real stories
in the post they referenced, which an earlier retweet filter threw away after paying for.

The policy under test is COLLECT, don't filter. t0 buys posts and keeps all of them,
because the endpoint cannot filter server-side and triage downstream is free.
"""

from __future__ import annotations

import json

from algent_backend.data_ingestion.newsroom.sources import x_native as xn


# -- roster file --------------------------------------------------------------

def _write(tmp_path, payload) -> object:
    path = tmp_path / "x_lists.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_roster_is_read_from_the_file(tmp_path) -> None:
    path = _write(tmp_path, {"lists": [
        {"id": "123", "label": "science_space", "pillar": "science"},
    ]})
    assert xn._lists_from_file(path) == (("123", "science_space", "science"),)


def test_a_disabled_entry_is_skipped(tmp_path) -> None:
    """Turning a list off should not mean deleting the note about why it was there."""
    path = _write(tmp_path, {"lists": [
        {"id": "1", "label": "a", "enabled": False},
        {"id": "2", "label": "b", "enabled": True},
    ]})
    assert [lid for lid, _, _ in xn._lists_from_file(path)] == ["2"]


def test_a_non_numeric_id_is_ignored(tmp_path) -> None:
    """A pasted URL instead of the id is the obvious mistake; it must not crash a run."""
    path = _write(tmp_path, {"lists": [
        {"id": "https://x.com/i/lists/9", "label": "oops"},
        {"id": "9", "label": "fine"},
    ]})
    assert [lid for lid, _, _ in xn._lists_from_file(path)] == ["9"]


def test_a_missing_or_broken_file_yields_no_lists(tmp_path) -> None:
    assert xn._lists_from_file(tmp_path / "nope.json") == ()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert xn._lists_from_file(bad) == ()


def test_env_overrides_the_file(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_X_LISTS", "77:probe:ai")
    assert xn.resolve_lists() == (("77", "probe", "ai"),)


def test_no_default_lists_are_baked_in() -> None:
    """Which lists carry our name is an editorial choice, never a code default — and the
    easy-to-find ones were newsroom staff rosters, which is the opposite of the point."""
    assert xn._DEFAULT_LISTS == ()


# -- fetch fairness -----------------------------------------------------------

class _Client:
    """Serves canned posts per list id, and records which lists were asked for."""

    def __init__(self, by_list: dict[str, list[dict]], referenced: dict | None = None):
        self._by_list = by_list
        # author -> (ref_type, ref_author, ref_text), mirroring the API's `includes.tweets`.
        self._referenced = referenced or {}
        self.asked: list[str] = []

    def get(self, url, params=None, **_kw):
        list_id = url.rstrip("/").split("/")[-2]
        self.asked.append(list_id)
        posts = self._by_list.get(list_id, [])
        users = [{"id": f"u{i}", "username": p["author"]} for i, p in enumerate(posts)]
        data = []
        ref_tweets = []
        for i, p in enumerate(posts):
            row = {"id": f"t{i}", "text": p["text"], "author_id": f"u{i}",
                   "public_metrics": {}, "created_at": "2026-07-30T05:00:00.000Z"}
            ref = self._referenced.get(p["author"])
            if ref:
                ref_type, ref_author, ref_text = ref
                row["referenced_tweets"] = [{"type": ref_type, "id": f"r{i}"}]
                ref_tweets.append({"id": f"r{i}", "text": ref_text, "author_id": f"ru{i}"})
                users.append({"id": f"ru{i}", "username": ref_author})
            data.append(row)
        return _Resp({"data": data,
                      "includes": {"users": users, "tweets": ref_tweets}})


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._payload


def _post(author: str, text: str) -> dict:
    return {"author": author, "text": text}


def _cfg(monkeypatch, spec: str) -> None:
    monkeypatch.setenv("ALGENT_X_LISTS", spec)


def test_everything_bought_is_kept(monkeypatch) -> None:
    """t0 collects, synthesis triages. Nothing is filtered after being paid for.

    There was briefly a per-author cap and a retweet filter here. Both discarded posts the
    API had already billed us for — the endpoint cannot filter server-side, so a dropped post
    is money spent on nothing, and the triage is free one layer down where the pool's echo
    suppression, the crystallizer and synthesis all run for zero marginal cost.
    """
    _cfg(monkeypatch, "1:solo:")
    client = _Client({"1": [
        _post("loud", f"A genuinely long enough post number {i} about something") for i in range(6)
    ] + [_post("quiet", "A different voice with something else entirely to say here")]})

    hits, fetched = xn.fetch_list_hits(max_hits=20, max_posts=50, client=client)
    assert len(hits) == fetched == 7        # every billed post survives to the pool
    assert [h["author"] for h in hits].count("loud") == 6


def test_every_configured_list_reaches_the_menu(monkeypatch) -> None:
    """The bug: the first two lists took all 12 slots and the third contributed nothing."""
    _cfg(monkeypatch, "1:one:,2:two:,3:three:")
    client = _Client({
        str(n): [_post(f"a{n}", f"List {n} post number {i} with enough length to survive")
                 for i in range(5)]
        for n in (1, 2, 3)
    })

    hits, _ = xn.fetch_list_hits(max_hits=6, max_posts=100, client=client)
    lanes = {h["lane"] for h in hits}
    assert lanes == {"list:one", "list:two", "list:three"}


def test_a_post_shared_by_two_lists_is_kept_once(monkeypatch) -> None:
    """Rosters overlap: one account belonged to all three lists, so its posts arrived
    three times and spent three slots."""
    _cfg(monkeypatch, "1:one:,2:two:")
    shared = _post("both", "The same post carried by two different lists at once here")
    client = _Client({"1": [shared], "2": [shared]})

    hits, _ = xn.fetch_list_hits(max_hits=10, max_posts=50, client=client)
    assert len(hits) == 1


def test_an_amplification_is_labelled_not_dropped(monkeypatch) -> None:
    """A retweet is weaker evidence than first-hand reporting, but it is not noise — it says
    what a curated roster is attending to. So it is labelled for synthesis to weigh."""
    _cfg(monkeypatch, "1:one:")
    client = _Client({"1": [
        _post("a", "RT @someone: this is an amplification of another person's post"),
        _post("b", "An original post that is long enough to clear the length floor"),
    ]})

    hits, _ = xn.fetch_list_hits(max_hits=10, max_posts=50, client=client)
    by_author = {h["author"]: h for h in hits}
    assert set(by_author) == {"a", "b"}
    assert by_author["a"]["is_retweet"] is True
    assert by_author["a"]["retweet_of"] == "someone"
    assert by_author["b"]["is_retweet"] is False


def test_the_referenced_post_supplies_the_substance(monkeypatch) -> None:
    """The whole reason amplifications are kept: a quote-tweet's own text is often just
    "interesting" and every fact lives in the post being quoted. Measured live — @chamath's
    "Wow. Super cool and very valuable." quoting a real story about skin-cancer robotics."""
    _cfg(monkeypatch, "1:one:")
    client = _Client({"1": [_post("chamath", "Wow. Super cool and very valuable.")]},
                     referenced={"chamath": ("quoted", "marionlepert",
                                             "Catching skin cancer early is a home robotics problem")})

    hits, _ = xn.fetch_list_hits(max_hits=10, max_posts=50, client=client)
    assert "home robotics problem" in hits[0]["summary"]
    assert "@marionlepert" in hits[0]["summary"]
    assert hits[0]["retweet_of"] == "marionlepert"
    assert hits[0]["ref_type"] == "quoted"


def test_the_band_is_off_when_no_lists_are_configured(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_X_LISTS", "")
    monkeypatch.setattr(xn, "_lists_from_file", lambda path=None: ())
    hits, fetched = xn.fetch_list_hits(max_hits=10, max_posts=50, client=_Client({}))
    assert hits == [] and fetched == 0
