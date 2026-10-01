"""The daily report engine: shape, Pulse numbers from the store, continuity, honesty guards, publishing."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from algent_backend.agent_system.agents.intel import daily, render
from algent_backend.agent_system.agents.intel.contracts import (
    CrossTheater,
    DailyChange,
    DailyEscalation,
    DaySummary,
    Development,
    PulseProposal,
    SectionDraft,
    Statement,
)
from algent_backend.agent_system.agents.pulse import PulseStore, repository
from algent_backend.agent_system.agents.pulse.contracts import Influence, Pulse, PulseDefinition, Situation
from algent_backend.publishing import intel_page

AS_OF = "2026-09-29"
SRC_A, SRC_B = "https://wire.example/a", "https://wire.example/b"


class _Model:
    def __init__(self, drafts, summary, tasks):
        self.drafts, self.summary, self.tasks, self.schema = drafts, summary, tasks, None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages, **_k):
        task = messages[1].content
        self.tasks.append(task)
        if self.schema is DaySummary:
            return self.summary
        return next(d for name, d in self.drafts.items() if f"THEATER: {name}" in task)


def _ctx(drafts, summary, tasks=None):
    model = _Model(drafts, summary, [] if tasks is None else tasks)
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


def _board():
    def theater(tid, name, domain, src):
        return {"id": tid, "name": name, "domain": domain, "why": "w",
                "members": [{"edition": "2026-09-29-0800", "n": 1, "title": f"{name} headline", "thesis": "t",
                             "sources": [src]}]}
    return {"as_of": AS_OF,
            "theaters": [theater("thr_a", "Alpha", "geopolitics", SRC_A), theater("thr_b", "Bravo", "geopolitics", SRC_B),
                         theater("thr_c", "Chip", "technology", "https://x")],
            "heat": [{"theater_id": "thr_a", "name": "Alpha", "heat": 9.0, "trend": "heating", "recent_share": 0.2,
                      "prior_share": 0.1},
                     {"theater_id": "thr_b", "name": "Bravo", "heat": 5.0, "trend": "steady", "recent_share": 0.1,
                      "prior_share": 0.1},
                     {"theater_id": "thr_c", "name": "Chip", "heat": 20.0, "trend": "steady"}]}


def _store(tmp_path, monkeypatch) -> PulseStore:
    store = PulseStore(tmp_path / "pulses")
    store.save_situation(Situation(id="sit_a", title="Alpha situation", status="active"))
    store.create_pulse(Pulse(id="pls_h", situation_id="sit_a", name="Hormuz Risk",
                             definitions=[PulseDefinition(question="q", low_end="lo", high_end="hi")]))
    for at, pos in (("2026-09-20T10:00:00+00:00", 25), ("2026-09-27T10:00:00+00:00", 30),
                    ("2026-09-29T10:00:00+00:00", 50),
                    ("2026-10-02T10:00:00+00:00", 90)):          # after as_of: must not count
        store.append(Influence(pulse_id="pls_h", at=at, mode="article", definition_version=1, proposed_position=pos,
                               absolute_position=99, decision="applied", rationale="r", key=f"k{at}"))
    monkeypatch.setattr(repository, "pulse_store", lambda: store)
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))
    return store


def _draft(**kw) -> SectionDraft:
    base = dict(bottom_line="Likely rising.", escalation=DailyEscalation(direction="rising", pace="fast"),
                developments=[Development(headline="Strike on port", when="2026-09-28", sources=[SRC_A],
                                          verification="researched")],
                pulses=["hormuz risk", "Invented Pulse"], outlook="Likely to continue.", watch_next=["talks"])
    return SectionDraft(**{**base, **kw})


SUMMARY = DaySummary(headline="Alpha heats up", the_day=["a", "b", "c", "d", "e", "f", "g"],
                     cross_theater=[CrossTheater(theaters=["alpha", "Bravo", "Nowhere"], link="shared sea lane"),
                                    CrossTheater(theaters=["Alpha"], link="alone")])


def test_report_shape_persistence_pulses_and_marking(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    ctx = _ctx({"Alpha": _draft(since_yesterday=[DailyChange(what="x", kind="new")]), "Bravo": _draft(pulses=[])},
               SUMMARY)
    res = daily.produce_daily(ctx, domain="geopolitics", top=5, research=False, model_spec=None, as_of=AS_OF,
                              board=_board(), out=tmp_path)
    rec = json.loads((tmp_path / "intel" / "daily" / "geopolitics" / f"{AS_OF}.json").read_text(encoding="utf-8"))
    assert rec == res["report"] and rec["schema"] == "ohmega.daily/1" and rec["researched"] is False
    assert [t["theater_id"] for t in rec["theaters"]] == ["thr_a", "thr_b"]          # technology theater skipped
    a = rec["theaters"][0]
    assert set(a) == {"theater_id", "name", "temperature", "escalation", "pulses", "bottom_line", "since_yesterday",
                      "developments", "context", "outlook", "watch_next", "brief_slug", "map"}
    assert a["temperature"] == {"heat": 9.0, "trend": "heating", "recent_share": 0.2, "prior_share": 0.1}
    assert a["map"] is None and a["brief_slug"] is None
    # Pulse numbers come from the store as of the report date: 50 now; 30 a day ago; 25 a week ago
    assert a["pulses"] == [{"id": "pls_h", "name": "Hormuz Risk", "position": 50.0, "band": a["pulses"][0]["band"],
                            "change_24h": 20.0, "change_7d": 25.0}]
    assert rec["theaters"][1]["pulses"] == []
    # no research ran: a "researched" claim is downgraded to reported
    assert a["developments"][0]["verification"] == "reported"
    assert a["since_yesterday"] == []                                                # nothing to compare with
    assert rec["summary"]["headline"] == "Alpha heats up" and len(rec["summary"]["the_day"]) == 6
    assert rec["cross_theater"] == [{"theaters": ["Alpha", "Bravo"], "link": "shared sea lane"}]
    assert (tmp_path / "daily_geopolitics.html").is_file()


def test_since_yesterday_uses_the_previous_section_by_theater_id(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    folder = tmp_path / "intel" / "daily" / "geopolitics"
    folder.mkdir(parents=True)

    def old(date, marker):
        return {"date": date, "theaters": [{"theater_id": "thr_a", "name": "renamed", "bottom_line": marker,
                                           "escalation": {"direction": "steady", "pace": "flat"},
                                           "developments": [{"when": date, "headline": "h"}], "watch_next": ["w"]}]}
    (folder / "2026-09-26.json").write_text(json.dumps(old("2026-09-26", "OLDER")), encoding="utf-8")
    (folder / "2026-09-28.json").write_text(json.dumps(old("2026-09-28", "YESTERDAY")), encoding="utf-8")
    (folder / "2026-09-30.json").write_text(json.dumps(old("2026-09-30", "FUTURE")), encoding="utf-8")
    tasks: list[str] = []
    ctx = _ctx({"Alpha": _draft(since_yesterday=[DailyChange(what="port hit", kind="escalated")]),
                "Bravo": _draft(since_yesterday=[DailyChange(what="invented", kind="new")])}, SUMMARY, tasks)
    rec = daily.produce_daily(ctx, domain="geopolitics", top=2, model_spec=None, as_of=AS_OF, board=_board())["report"]
    alpha_task = next(t for t in tasks if "THEATER: Alpha" in t)
    assert "YESTERDAY" in alpha_task and "OLDER" not in alpha_task and "FUTURE" not in alpha_task
    assert "PREVIOUS DAILY SECTION: none" in next(t for t in tasks if "THEATER: Bravo" in t)
    assert [c["what"] for c in rec["theaters"][0]["since_yesterday"]] == ["port hit"]
    assert rec["theaters"][1]["since_yesterday"] == []                               # Bravo has no earlier section


def test_quotes_over_25_words_are_downgraded_and_urls_must_be_known() -> None:
    long_quote = " ".join(f"w{i}" for i in range(40))
    draft = _draft(developments=[Development(
        headline="h", sources=[SRC_A, "https://invented.example"],
        statements=[Statement(who="Minister", said=long_quote, quote=True, source="https://invented.example"),
                    Statement(who="Envoy", said="we will respond", quote=True, source=SRC_A)])])
    out = daily.normalise_section(draft, pulse_table={}, has_previous=False, researched=False,
                                  research_urls=set(), reported_urls={SRC_A})
    long, short = out.developments[0].statements
    assert long.quote is True and long.said.endswith(" …") and len(long.said.split()) == 26 and long.source == ""
    assert len(long.said.rstrip("…").split()) == daily.MAX_QUOTE_WORDS
    assert short.quote is True and short.said == "we will respond" and short.source == SRC_A
    assert out.developments[0].sources == [SRC_A]


def test_researched_needs_research_and_a_cited_research_source() -> None:
    def run(researched, research_urls):
        d = _draft(developments=[Development(headline="a", sources=[SRC_A], verification="researched"),
                                 Development(headline="b", sources=[SRC_B], verification="researched"),
                                 Development(headline="c", verification="researched")])
        out = daily.normalise_section(d, pulse_table={}, has_previous=False, researched=researched,
                                      research_urls=research_urls, reported_urls={SRC_B})
        return [x.verification for x in out.developments]
    assert run(True, {SRC_A + "/"}) == ["researched", "reported", "reported"]   # trailing slash tolerated
    assert run(False, {SRC_A}) == ["reported"] * 3


def test_pulse_names_are_filtered_to_the_table_and_proposals_to_missing_dimensions() -> None:
    table = {"Hormuz Risk": "- row"}
    draft = _draft(pulses=["hormuz risk", "HORMUZ RISK", "Made Up"],
                   pulse_proposals=[PulseProposal(name="Hormuz Risk", question="q", low_end="a", high_end="b"),
                                    PulseProposal(name="Shipping Insurance Stress", question="q", low_end="a",
                                                  high_end="b"),
                                    PulseProposal(name="No Ends", question="q", low_end="", high_end="b")])
    out = daily.normalise_section(draft, pulse_table=table, has_previous=False, researched=False,
                                  research_urls=set(), reported_urls=set())
    assert out.pulses == ["Hormuz Risk"]
    assert [p.name for p in out.pulse_proposals] == ["Shipping Insurance Stress"]


def test_proposals_are_appended_once_and_no_pulse_is_created(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path, monkeypatch)
    prop = PulseProposal(name="Shipping Insurance Stress", question="q?", low_end="calm", high_end="crisis", why="gap")
    ctx = _ctx({"Alpha": _draft(pulse_proposals=[prop]), "Bravo": _draft(pulse_proposals=[prop])}, SUMMARY)
    rec = daily.produce_daily(ctx, domain="geopolitics", top=2, model_spec=None, as_of=AS_OF, board=_board())["report"]
    lines = [json.loads(x) for x in daily.proposals_path().read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1                                                            # same name not logged twice
    assert lines[0]["date"] == AS_OF and lines[0]["domain"] == "geopolitics" and lines[0]["theater_id"] == "thr_a"
    assert lines[0]["theater"] == "Alpha" and lines[0]["name"] == "Shipping Insurance Stress"
    assert len(rec["pulse_proposals"]) == 2 and set(rec["pulse_proposals"][0]) == {
        "theater", "name", "question", "low_end", "high_end", "why"}
    assert [p.name for p in store.pulses()] == ["Hormuz Risk"]


def test_research_evidence_carries_source_urls() -> None:
    profile = {"id": "p", "title": "T", "source_ledger": [{"id": "s1", "url": SRC_A}, {"id": "s2", "url": ""}],
               "claim_ledger": [{"id": "c1", "text": "Alpha fired", "status": "confirmed", "salience": "high",
                                 "supported_by": ["s1", "s2"]}]}
    text, urls = daily.research_evidence([profile])
    assert f"[sources: {SRC_A}]" in text and urls == {SRC_A}


def test_publish_mirrors_daily_files_and_snapshot_lists_them(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path, monkeypatch)
    ctx = _ctx({"Alpha": _draft(), "Bravo": _draft()}, SUMMARY)
    daily.produce_daily(ctx, domain="geopolitics", top=2, model_spec=None, as_of="2026-09-28", board=_board())
    daily.produce_daily(ctx, domain="geopolitics", top=2, model_spec=None, as_of=AS_OF, board=_board())
    intel = tmp_path / "intel"
    snap = intel_page.build_snapshot(store, intel, now=datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
    assert snap["daily"] == [{"domain": "geopolitics", "date": AS_OF, "headline": "Alpha heats up"},
                             {"domain": "geopolitics", "date": "2026-09-28", "headline": "Alpha heats up"}]
    site = tmp_path / "site"
    intel_page.write_intel(site, snap, intel)
    files = sorted((site / "content" / "intel" / "daily" / "geopolitics").glob("*.json"))
    assert [f.stem for f in files] == ["2026-09-28", AS_OF]
    assert json.loads(files[1].read_text(encoding="utf-8"))["schema"] == "ohmega.daily/1"
    stamps = {f: f.stat().st_mtime_ns for f in files}
    intel_page.write_intel(site, snap, intel)
    assert stamps == {f: f.stat().st_mtime_ns for f in files}


def test_render_daily_escapes_and_marks_verification(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    draft = _draft(developments=[Development(headline="<script>x</script>", sources=[SRC_B],
                                             statements=[Statement(who="Envoy", said="we will respond", quote=True)])])
    rec = daily.produce_daily(_ctx({"Alpha": draft, "Bravo": _draft()}, SUMMARY), domain="geopolitics", top=2,
                              model_spec=None, as_of=AS_OF, board=_board())["report"]
    page = render.render_daily(rec)
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    assert "pill reported" in page and "“we will respond”" in page and "Hormuz Risk" in page


def test_an_empty_domain_still_yields_a_valid_report(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    res = daily.produce_daily(_ctx({}, SUMMARY), domain="science", top=3, model_spec=None, as_of=AS_OF, board=_board())
    assert res["report"]["theaters"] == [] and res["report"]["summary"]["the_day"] == []
