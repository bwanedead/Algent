"""
Extraction: one structured model call per transcript (per chunk, for very long ones) turns a primary
text into statements on the record.

The model reads and judges; the harness validates mechanically afterward. A quote that is not a
substring of the transcript is dropped back to its paraphrase (or the statement is dropped when it
has nothing else), and identity, date fallback and ``source_url`` are stamped by the harness, never
trusted from the model.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from . import store
from .contracts import (
    QUOTE_WORD_LIMIT,
    ExtractedStatement,
    ExtractionPlan,
    Statement,
    Transcript,
    statement_id,
)
from .sources import by_id

CHUNK_CHARS = 24_000                  # ~6k tokens: a multi-hour Q&A becomes several calls, never one huge one

EXTRACTOR_ROLE = """\
You keep the record of what powers say about one another. You are given one primary text — a
transcript, press release, readout or spokesperson briefing — and you extract the statements in it
that an analyst of international relations would want on file.

Why this exists: rhetoric is a leading indicator. A threat, a new condition, a softened tone, an
offer, a reassurance aimed at a third party all show up in words before they show up in events, and
the desk can only see a shift in tone if the earlier statements were captured too. Reports built
from headlines alone read alike every day; the record of who said what is what gives them texture.

What to capture: the load-bearing statements about relations between powers, wars and ceasefires,
alliances and troop deployments, sanctions, red lines, offers and demands, accusations and denials.
Capture the subtle ones with the same care as the loud ones — a conditional that was not there
before, a conspicuous omission, a reassurance addressed to someone who was not in the room, an
offer wrapped inside a complaint. When a speaker is answering a question, the question's framing
matters to what the answer means; reflect it in the paraphrase.

What to skip: ceremonial and protocol filler (greetings, condolences, national-day wishes, thanks),
and purely domestic matters unless they bear on foreign relations, war or alliance politics. An
empty result is correct and common for such texts — an honest empty list costs nothing, and
padding the record with trivia makes the real signals harder to find.

Wording: give exact words in `quote` only where the wording itself matters (a red line, a threat, a
pointed phrase, a number or a condition) and copy them character for character from the text —
never tidy, translate or stitch two passages together. A fabricated or altered quote corrupts a
record other people will cite; when unsure, paraphrase instead. Otherwise write a faithful,
neutral `paraphrase`. Never invent: every statement must be in the text, attributed to the person
who actually said it. In a Q&A, the speaker is whoever spoke the line, not the host or the source.

Fields: `speaker` is the person (or the institution when no individual is named) and `role` their
office; `affiliation` is who they speak for. `about` names the actors or targets the statement
concerns, as an analyst would index them (e.g. NATO, the EU, Ukraine). `signal` is the kind of act:
threat, warning, red_line, commitment, offer, demand, reassurance, accusation, denial,
policy_announcement, tone_shift, or other. `stance` is toward `about`, from -2 (hostile) through 0
(neutral) to +2 (conciliatory). `significance` is one line: why an analyst would care. Use the date
in the text when it states one; otherwise leave `date` empty.
"""


# ── mechanical validation ─────────────────────────────────────────────────────────────────────
_QUOTE_TABLE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    """Whitespace- and typography-insensitive form for quote checking."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(_QUOTE_TABLE).split())


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries into pieces of at most ``limit`` characters (an oversized single
    paragraph is hard-cut, which is rare and only costs it its context)."""
    paragraphs = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for p in paragraphs:
        pieces = [p[i:i + limit] for i in range(0, len(p), limit)]
        for piece in pieces:
            if size + len(piece) > limit and current:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _valid_date(raw: str) -> str:
    try:
        return date.fromisoformat(raw.strip()[:10]).isoformat()
    except ValueError:
        return ""


def validate(proposed: list[ExtractedStatement], transcript: Transcript, *, source_kind: str = "primary") -> list[Statement]:
    """Stamp identity/provenance and enforce the quote rule. Statements with nothing left are dropped."""
    haystack = normalize(transcript.text)
    fallback_date = _valid_date(transcript.published) or transcript.fetched_at[:10]
    out: dict[str, Statement] = {}
    for p in proposed:
        speaker = " ".join(p.speaker.split())
        quote = " ".join(p.quote.split())
        paraphrase = " ".join(p.paraphrase.split())
        if quote and normalize(quote) not in haystack:
            quote = ""                                 # not in the source: never keep it as a quote
        words = quote.split()
        if len(words) > QUOTE_WORD_LIMIT:
            quote = " ".join(words[:QUOTE_WORD_LIMIT])  # still a verbatim prefix
        if not speaker or not (quote or paraphrase):
            continue
        s = Statement(
            id=statement_id(transcript.url, speaker, quote or paraphrase), speaker=speaker,
            role=" ".join(p.role.split()), affiliation=" ".join(p.affiliation.split()),
            date=_valid_date(p.date) or fallback_date, venue_kind=p.venue_kind, quote=quote,
            paraphrase=paraphrase, about=[a.strip() for a in p.about if a.strip()],
            topics=[t.strip() for t in p.topics if t.strip()], signal=p.signal,
            stance=max(-2, min(2, int(p.stance))), significance=" ".join(p.significance.split()),
            source_url=transcript.url, source_kind=source_kind, transcript_id=transcript.id)  # type: ignore[arg-type]
        out.setdefault(s.id, s)                        # chunk boundaries can repeat a statement
    return list(out.values())


# ── the call ──────────────────────────────────────────────────────────────────────────────────
def _task(transcript: Transcript, chunk: str, index: int, total: int, lead: str) -> str:
    source = by_id(transcript.feed)
    who = f"{source.name} ({source.affiliation})" if source else transcript.feed
    part = f"\nPART {index + 1} OF {total}. The start of the text, for who is speaking:\n{lead}\n" if total > 1 else ""
    return (f"SOURCE: {who}\nTITLE: {transcript.title}\nPUBLISHED: {transcript.published or 'unknown'}\n"
            f"URL: {transcript.url}\n{part}\nTEXT:\n{chunk}\n\n"
            "TASK: extract the statements on the record from this text.")


def extract_transcript(context: Any, config: Any, model_spec: Any, transcript: Transcript) -> list[Statement]:
    """Statements from one transcript: a call per chunk, merged and deduplicated, then validated."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    model = context.model_resolver.resolve(model_spec).client.with_structured_output(ExtractionPlan)
    system = SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, EXTRACTOR_ROLE))
    chunks = chunk_text(transcript.text)
    lead = transcript.text[:600]
    proposed: list[ExtractedStatement] = []
    for i, chunk in enumerate(chunks):
        plan = model.invoke([system, HumanMessage(content=_task(transcript, chunk, i, len(chunks), lead))], config=config)
        proposed.extend(getattr(plan, "statements", []) or [])
    source = by_id(transcript.feed)
    return validate(proposed, transcript, source_kind="primary" if source else "secondary")


def extract_pending(context: Any, config: Any, model_spec: Any, *, root: Any = None,
                    feeds: list[str] | None = None, limit: int | None = None) -> dict:
    """Extract every collected transcript that has not been extracted yet (never pays twice for one).
    Returns ``{transcripts, statements, errors}``."""
    seen = store.load_seen(root)
    report: dict[str, Any] = {"transcripts": 0, "statements": 0, "errors": []}
    for tid in store.transcript_ids(root):
        if tid in seen["extracted"] or (limit is not None and report["transcripts"] >= limit):
            continue
        t = store.load_transcript(tid, root)
        if t is None or (feeds and t.feed not in feeds):
            continue
        try:
            statements = extract_transcript(context, None, model_spec, t)
        except Exception as exc:  # noqa: BLE001 - one failed transcript is retried next run; others continue
            report["errors"].append(f"{t.url}: {type(exc).__name__}: {str(exc)[:140]}")
            continue
        added = store.append_statements(statements, root)
        seen = store.load_seen(root)
        seen["extracted"][tid] = {"statements": len(statements), "new": added}
        store.save_seen(seen, root)
        report["transcripts"] += 1
        report["statements"] += added
    return report
