"""Statements store queries and recall formatting — no network, no model."""

from __future__ import annotations

from datetime import date

from algent_backend.agent_system.agents.statements import recall, speaker_history, store
from algent_backend.agent_system.agents.statements.contracts import Statement, statement_id

TODAY = date(2026, 10, 4)


def _st(speaker, day, text, *, about=("NATO",), affiliation="Russia", topics=(), stance=0, quote="", signal="warning") -> Statement:
    url = f"http://example.org/{speaker}/{day}"
    return Statement(id=statement_id(url, speaker, quote or text), speaker=speaker, role="President", affiliation=affiliation,
                     date=day, quote=quote, paraphrase=text, about=list(about), topics=list(topics), signal=signal,
                     stance=stance, significance="matters", source_url=url, transcript_id="tr_x")


def _seed(tmp_path):
    rows = [
        _st("Vladimir Putin", "2026-09-20", "Warns NATO against deployments.", about=("NATO", "Ukraine"), topics=("troops",), stance=-1),
        _st("Vladimir Putin", "2026-10-01", "Says Europe may talk if sanctions ease.", about=("EU",), topics=("sanctions",), stance=1,
            quote="we are ready to talk", signal="offer"),
        _st("Mark Rutte", "2026-10-02", "NATO will defend every inch.", about=("Russia",), affiliation="NATO", stance=-1),
        _st("Old Speaker", "2026-06-01", "Ancient history.", about=("Russia",)),
    ]
    assert store.append_statements(rows, tmp_path) == 4
    return rows


def test_append_is_idempotent_and_survives_a_torn_line(tmp_path) -> None:
    rows = _seed(tmp_path)
    assert store.append_statements(rows, tmp_path) == 0
    with (tmp_path / "statements.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"id": "torn\n')
    assert len(store.load_statements(tmp_path)) == 4


def test_query_filters_newest_first_and_word_level_matching(tmp_path) -> None:
    _seed(tmp_path)
    q = lambda **k: store.query(root=tmp_path, today=TODAY, **k)           # noqa: E731
    assert [s.speaker for s in q(days=10)] == ["Mark Rutte", "Vladimir Putin"]    # newest first, 10-day window
    assert len(q(days=10, speaker="Putin")) == 1 and len(q(speaker="putin")) == 2          # partial name, any case
    assert [s.speaker for s in q(about="Russia")] == ["Mark Rutte", "Old Speaker"]
    assert q(about="US") == [] and q(affiliation="us") == []                         # 'us' is not inside 'Russia'
    assert [s.speaker for s in q(affiliation="NATO")] == ["Mark Rutte"]
    assert len(q(topic="sanctions")) == 1
    assert len(q(terms=["Ukraine", "Hormuz"])) == 1 and q(terms=["Hormuz"]) == []
    assert len(q(limit=1)) == 1


def test_recall_formats_an_evidence_block_with_links(tmp_path) -> None:
    _seed(tmp_path)
    block = recall(["NATO", "sanctions"], days=30, today=TODAY, root=tmp_path)
    assert block.startswith("STATEMENTS ON RECORD")
    lines = [ln for ln in block.splitlines() if ln.startswith("- ")]
    assert [ln.split(" · ")[0] for ln in lines] == ["- 2026-10-02", "- 2026-10-01", "- 2026-09-20"]    # newest first
    assert '"we are ready to talk"' in block and "[offer, stance +1]" in block and "Mark Rutte, President (NATO)" in block
    assert "http://example.org/Mark Rutte/2026-10-02" in block and "Ancient history" not in block
    assert recall(["Hormuz"], today=TODAY, root=tmp_path) == ""
    assert len([ln for ln in recall(["NATO"], days=365, limit=1, today=TODAY, root=tmp_path).splitlines() if ln.startswith("- ")]) == 1


def test_speaker_history_runs_oldest_first(tmp_path) -> None:
    _seed(tmp_path)
    block = speaker_history("Putin", 90, today=TODAY, root=tmp_path)
    assert block.startswith("STATEMENT HISTORY: Putin")
    assert block.index("2026-09-20") < block.index("2026-10-01")
    assert speaker_history("Nobody", today=TODAY, root=tmp_path) == ""
