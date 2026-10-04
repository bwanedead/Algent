"""Statements extraction — a fake model returns canned plans; the harness validation is under test."""

from __future__ import annotations

from algent_backend.agent_system.agents.statements import extract, store
from algent_backend.agent_system.agents.statements.contracts import (
    ExtractedStatement,
    ExtractionPlan,
    Transcript,
)

TEXT = ("Vladimir Putin: We have never wanted war with Europe, but any troops placed in Ukraine\n"
        "will be treated as a legitimate target.\n\n"
        "Question: Is NATO a threat?\n\n"
        "Vladimir Putin: The enlargement of the alliance toward our borders is the core problem.")


def _transcript(text: str = TEXT, tid: str = "tr_a") -> Transcript:
    return Transcript(id=tid, feed="kremlin_transcripts", url=f"http://en.kremlin.ru/{tid}", title="Q&A",
                      published="2026-10-01T21:30:00+04:00", text=text, fetched_at="2026-10-04T10:00:00+00:00")


def _s(**kw) -> ExtractedStatement:
    base = dict(speaker="Vladimir Putin", role="President of Russia", affiliation="Russia", venue_kind="press_conference",
                about=["EU", "Ukraine"], signal="threat", stance=-2, significance="Names foreign troops as targets.")
    return ExtractedStatement(**{**base, **kw})


class _Fake:
    def __init__(self, plans):
        self.plans, self.calls = list(plans), 0

    def with_structured_output(self, _s):
        return self

    def invoke(self, *_a, **_k):
        self.calls += 1
        return self.plans[min(self.calls - 1, len(self.plans) - 1)]


def _ctx(fake):
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": fake})()})()})()


def test_a_fabricated_quote_is_dropped_but_the_paraphrase_survives() -> None:
    plan = ExtractionPlan(statements=[
        _s(quote="any troops placed in Ukraine will be treated as a legitimate target", paraphrase="Foreign troops in Ukraine are targets."),
        _s(quote="We will crush Europe", paraphrase="Threatens Europe."),          # fabricated wording
        _s(quote="We will bury NATO", paraphrase="", signal="warning"),            # fabricated and nothing else: dropped
    ])
    out = extract.extract_transcript(_ctx(_Fake([plan])), None, None, _transcript())
    assert len(out) == 2
    real, faked = out
    assert real.quote.startswith("any troops placed") and faked.quote == "" and faked.paraphrase == "Threatens Europe."


def test_harness_stamps_provenance_and_fixes_dates_and_stance() -> None:
    plan = ExtractionPlan(statements=[_s(paraphrase="NATO enlargement is the core problem.", date="not a date", stance=9)])
    (s,) = extract.extract_transcript(_ctx(_Fake([plan])), None, None, _transcript())
    assert s.source_url == "http://en.kremlin.ru/tr_a" and s.transcript_id == "tr_a" and s.source_kind == "primary"
    assert s.date == "2026-10-01" and s.stance == 2 and s.id.startswith("st_")


def test_quote_check_ignores_whitespace_and_typography() -> None:
    t = _transcript("He said: “we won’t   accept\nthis” — clearly.")
    plan = ExtractionPlan(statements=[_s(quote="we won't accept this", paraphrase="Rejects it.")])
    (s,) = extract.validate(plan.statements, t)
    assert s.quote == "we won't accept this"


def test_long_quotes_are_cut_to_the_word_limit_as_a_verbatim_prefix() -> None:
    words = " ".join(f"w{i}" for i in range(90))
    (s,) = extract.validate([_s(quote=words, paraphrase="Long.")], _transcript(words))
    assert len(s.quote.split()) == 60 and words.startswith(s.quote)


def test_chunking_on_paragraph_boundaries_and_merge_dedupes() -> None:
    paragraphs = [f"Paragraph {i}: " + "word " * 40 for i in range(200)]
    chunks = extract.chunk_text("\n\n".join(paragraphs), limit=1500)
    assert len(chunks) > 1 and all(len(c) <= 1500 for c in chunks)
    assert "\n\n".join(chunks).count("Paragraph") == 200            # nothing lost, cut only between paragraphs
    plan = ExtractionPlan(statements=[_s(paraphrase="Same point every time.")])
    fake = _Fake([plan])
    out = extract.extract_transcript(_ctx(fake), None, None, _transcript("\n\n".join(paragraphs)))
    assert fake.calls == len(extract.chunk_text("\n\n".join(paragraphs))) > 1 and len(out) == 1


def test_extract_pending_extracts_once_and_a_failure_is_retried(tmp_path) -> None:
    store.save_transcript(_transcript(tid="tr_a"), tmp_path)
    store.save_transcript(_transcript(tid="tr_b"), tmp_path)
    plan = ExtractionPlan(statements=[_s(paraphrase="Point.")])

    class Flaky(_Fake):
        def invoke(self, *a, **k):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("provider 504")
            return plan

    fake = Flaky([])
    first = extract.extract_pending(_ctx(fake), None, None, root=tmp_path)
    assert (first["transcripts"], len(first["errors"])) == (1, 1)
    second = extract.extract_pending(_ctx(fake), None, None, root=tmp_path)      # only the failed one is paid for again
    assert (second["transcripts"], fake.calls) == (1, 3)
    assert extract.extract_pending(_ctx(fake), None, None, root=tmp_path)["transcripts"] == 0
    assert {s.transcript_id for s in store.load_statements(tmp_path)} == {"tr_a", "tr_b"}
