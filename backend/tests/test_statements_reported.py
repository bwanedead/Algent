"""The reported lane — selection, budget, cache, quote validation against the article, primary-over-secondary."""

from __future__ import annotations

from datetime import UTC, datetime

from algent_backend.agent_system.agents.statements import dedupe, extract, reported, store
from algent_backend.agent_system.agents.statements.contracts import (
    ExtractedStatement,
    Statement,
    Transcript,
)

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
ARTICLE = ("Zelensky told reporters on Sunday: \"We will not accept any deal decided without Ukraine at the table\" "
           "and said Kyiv expects more air defence. ") * 8


def _search_none(q, days):
    return []


def _news(items):
    return lambda q: items


def _hit(url, title, outlet="Wire", published="2026-10-04"):
    return {"title": title, "url": url, "outlet": outlet, "published": published, "resolved": True}


LEADERS = {"UA": ["Volodymyr Zelenskyy"], "LT": ["Gitanas Nauseda"]}


def _run(tmp_path, **kw):
    pages = kw.pop("pages", {})
    calls: list[str] = []

    def read(url):
        calls.append(url)
        return pages.get(url, ARTICLE)

    out = reported.collect_reported(
        root=tmp_path, now=NOW, leaders=LEADERS, sleep=lambda _s: None, lib_search=kw.pop("lib_search", _search_none),
        lib_text=lambda u: "", read_page=read, **kw)
    out["reads"] = calls
    return out


def test_plan_orders_silent_theater_actors_first_then_offices_then_states() -> None:
    ts = reported.plan_targets(theaters=["Russia-Ukraine war and European security. NATO posture"], leaders=LEADERS)
    tiers = {t.label: t.tier for t in ts}
    assert tiers["Volodymyr Zelenskyy (Ukraine)"] == 0                 # Ukraine has no feed of its own
    assert tiers["NATO Secretary General"] == 1 and tiers["Gitanas Nauseda (Lithuania)"] == 2
    assert [t.tier for t in ts] == sorted(t.tier for t in ts)


def test_country_names_need_capitals_so_ordinary_words_do_not_resolve() -> None:
    from algent_backend.actors import registry
    found = reported._countries_in("Gaza war as an aid and Hormuz crisis; US-Iran talks", registry.resolve)
    assert set(found) == {"US", "IR"}


def test_search_read_collect_and_cache(tmp_path) -> None:
    items = [_hit("https://a.example/1", "Zelensky says no deal without Kyiv"),
             _hit("https://a.example/2", "Weather report", "Wire"),                 # does not mention the person
             _hit("https://a.example/old", "Zelensky on air defence", published="2026-09-01")]  # outside the window
    t = [reported.Target("p:z", "Zelenskyy", '"Volodymyr Zelenskyy"', ("zelenskyy", "zelensky"), 0)]
    first = _run(tmp_path, targets=t, news_search=_news(items))
    assert first["collected"] == 1 and first["reads"] == ["https://a.example/1"]
    tr = store.load_transcript(store.transcript_ids(tmp_path)[0], tmp_path)
    assert tr.feed == "reported" and tr.outlet == "Wire" and tr.url == "https://a.example/1"
    # a later run (past the cooldown) never re-reads the same url
    later = reported.collect_reported(root=tmp_path, now=datetime(2026, 10, 5, 12, tzinfo=UTC), targets=t,
                                      news_search=_news(items), lib_search=_search_none, lib_text=lambda u: "",
                                      read_page=lambda u: (_ for _ in ()).throw(AssertionError("re-read")),
                                      sleep=lambda _s: None)
    assert later["collected"] == 0 and later["articles_read"] == 0


def test_cooldown_skips_a_target_searched_recently(tmp_path) -> None:
    t = [reported.Target("p:z", "Zelenskyy", '"Z"', ("zelensky",), 0)]
    items = [_hit("https://a.example/1", "Zelensky speaks")]
    _run(tmp_path, targets=t, news_search=_news(items))
    second = _run(tmp_path, targets=t, news_search=_news([_hit("https://a.example/9", "Zelensky again")]))
    assert second["targets_searched"] == 0


def test_budgets_cap_articles_per_target_and_per_run(tmp_path) -> None:
    items = [_hit(f"https://a.example/{i}", f"Zelensky item {i}") for i in range(6)]
    t = [reported.Target(f"p:{n}", n, n, ("zelensky",), 0) for n in "ab"]
    out = _run(tmp_path, targets=t, news_search=_news(items), max_articles=3)
    assert out["articles_read"] == 3 and out["by_target"][0]["articles"].__len__() == reported.MAX_PER_TARGET
    assert out["targets_searched"] == 2
    # the target that hit the budget is not stamped: it is first in line next run
    assert "p:b" not in store.load_seen(tmp_path)["reported"]


def test_library_first_and_primary_kind_documents_are_not_reports(tmp_path) -> None:
    lib = [{"url": "https://wire.example/x", "title": "Rutte warns on drones", "source": "reuters", "kind": "wire",
            "published": "2026-10-04", "snippet": "NATO chief"},
           {"url": "https://nato.example/y", "title": "Rutte speech", "source": "nato", "kind": "international_org",
            "published": "2026-10-04", "snippet": "NATO"}]
    t = [reported.Target("o:n", "NATO SG", "NATO", ("nato", "rutte"), 1)]
    out = reported.collect_reported(root=tmp_path, now=NOW, targets=t, lib_search=lambda q, d: lib,
                                    lib_text=lambda u: ARTICLE, read_page=lambda u: (_ for _ in ()).throw(AssertionError()),
                                    news_search=_news([]), sleep=lambda _s: None)
    urls = [a["url"] for a in out["by_target"][0]["articles"]]
    assert urls == ["https://wire.example/x"] and out["collected"] == 1       # library text used, nothing fetched


def test_unreadable_and_stub_articles_fail_and_park(tmp_path) -> None:
    t = [reported.Target("p:z", "Z", "Z", ("zelensky",), 0)]
    out = _run(tmp_path, targets=t, news_search=_news([_hit("https://a.example/stub", "Zelensky")]),
               pages={"https://a.example/stub": "Subscribe to read"})
    assert out["failed"] == 1 and store.load_seen(tmp_path)["failed"]["https://a.example/stub"] == 1


# ── extraction validation and dedupe ────────────────────────────────────────────────────────
def _tr(text=ARTICLE):
    return Transcript(id="tr_r", feed="reported", url="https://a.example/1", title="t", published="2026-10-04",
                      text=text, fetched_at=NOW.isoformat(), outlet="Wire")


def test_quote_is_validated_against_the_article_and_marked_secondary() -> None:
    good = "We will not accept any deal decided without Ukraine at the table"
    out = extract.validate([
        ExtractedStatement(speaker="Volodymyr Zelensky", quote=good, paraphrase="No deal without Kyiv."),
        ExtractedStatement(speaker="Volodymyr Zelensky", quote="We will fight to the last", paraphrase="Vows to fight on."),
    ], _tr(), source_kind="secondary")
    assert [s.source_kind for s in out] == ["secondary", "secondary"]
    assert all(s.reported_by == "Wire" and s.source_url == "https://a.example/1" for s in out)
    assert out[0].quote == good and out[1].quote == ""                  # invented wording falls back to paraphrase


def test_extract_transcript_marks_reports_secondary_and_says_so_in_the_task() -> None:
    assert "NEWS REPORT by Wire" in extract._task(_tr(), "x", 0, 1, "")
    assert "never the outlet or its journalist" in " ".join(extract.EXTRACTOR_ROLE.split())


def _st(id, source_kind, speaker, date, quote="", para=""):
    return Statement(id=id, speaker=speaker, date=date, quote=quote, paraphrase=para, source_url="u" + id,
                     source_kind=source_kind, transcript_id="t" + id)


def test_primary_wins_over_the_same_remark_reported(tmp_path) -> None:
    primary = _st("p", "primary", "Mark Rutte", "2026-10-01", "we stand with Ukraine as long as it takes")
    report = _st("s", "secondary", "Rutte", "2026-10-02", "we stand with Ukraine as long as it takes")
    other = _st("o", "secondary", "Rutte", "2026-10-02", para="Rutte urged allies to buy more interceptors this winter")
    store.append_statements([primary], tmp_path)
    assert store.append_statements([report, other], tmp_path) == 1       # the report is skipped on write
    assert [s.id for s in store.query(root=tmp_path)] == ["o", "p"] or {s.id for s in store.query(root=tmp_path)} == {"o", "p"}


def test_a_report_filed_before_its_primary_is_hidden_on_read(tmp_path) -> None:
    report = _st("s", "secondary", "Mark Rutte", "2026-10-01", para="Rutte said NATO will keep arming Ukraine long term")
    store.append_statements([report], tmp_path)
    primary = _st("p", "primary", "Mark Rutte", "2026-10-01", para="NATO will keep arming Ukraine for the long term, Rutte said")
    store.append_statements([primary], tmp_path)
    assert [s.id for s in store.query(root=tmp_path)] == ["p"]


def test_two_outlets_reporting_one_remark_keep_one() -> None:
    a = _st("a", "secondary", "Zelensky", "2026-10-03", para="Zelensky demanded air defence from Germany this week")
    b = _st("b", "secondary", "Volodymyr Zelensky", "2026-10-04", para="Zelensky demanded more air defence from Germany")
    c = _st("c", "secondary", "Zelensky", "2026-10-04", para="Zelensky praised the sanctions package on Moscow banks")
    assert [s.id for s in dedupe.visible([a, b, c])] == ["a", "c"]
    assert dedupe.covered_by(_st("x", "primary", "Zelensky", "2026-10-03", para=a.paraphrase), [a]) is None
