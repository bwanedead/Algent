"""
Treatment briefing — a deterministic, readable VIEW over an EditorialTreatment.

The canonical object is the JSON; this renders it into the markdown the treatment reviewer
and the drafter read (and a human can inspect). It is the compressed understanding made
legible — frame first, then the molecule, then the perspectives and the honesty ledger. A
view, never the source of truth. Pure: treatment in, markdown out.
"""

from __future__ import annotations

from .treatment import EditorialTreatment


def render_treatment(t: EditorialTreatment) -> str:
    out: list[str] = [
        f"# Treatment — {t.title or t.id}",
        f"_profile: {t.profile_id or '?'} · rev-of {t.generator or '?'}_",
        "",
        *_frame_block(t),
    ]
    if t.core_understanding:
        out += ["## Core understanding (the molecule the reader should end holding)",
                t.core_understanding, ""]
    if t.reader_question:
        # The drafter's sharpest test: every paragraph must earn its place answering this.
        out += ["## The question this piece answers (for the reader)", t.reader_question, ""]
    if t.read_minutes:
        # Roughly 220 words a minute. Given as a range because the point is a bound to write
        # toward, not a number to hit — and coming in under it is a good outcome, not a shortfall.
        low, high = int(t.read_minutes * 190), int(t.read_minutes * 250)
        out += [
            "## How deep a read this story merits",
            f"**~{t.read_minutes} min** (about {low}-{high} words)"
            + (f" — {t.read_minutes_why}" if t.read_minutes_why else ""),
            "A soft bound, judged from the whole profile before any prose existed. Write toward "
            "it; if the understanding lands sooner, STOP — finishing short is a good outcome, "
            "and there is nothing here to pad out to.",
            "",
        ]
    out += _entry_block(t)
    out += _concepts_block(t)
    if t.primitives:
        # The ramp — speak these in your own voice, uncited, where each concept first bears weight.
        out.append("## Primitives — textbook background to weave in (YOUR voice, no citation)")
        out += [f"- **{p.term}** — {p.plain_meaning}" for p in t.primitives]
        out.append("")
    out += _perspectives_block(t)
    if t.deception_risks:
        out.append("## Deception risks (how this story could mislead while saying true things)")
        out += [f"- {r}" for r in t.deception_risks]
        out.append("")
    if t.must_use_items:
        out += [f"**Must-use profile items:** {', '.join(t.must_use_items)}", ""]
    if t.open_questions:
        out.append("## Open questions")
        out += [f"- {q}" for q in t.open_questions]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _frame_block(t: EditorialTreatment) -> list[str]:
    out = ["## Frame (the governing vantage)", f"**{t.chosen_frame.frame or '(none)'}**"]
    if t.chosen_frame.rationale:
        out.append(f"_{t.chosen_frame.rationale}_")
    if t.rejected_frames:
        out += ["", "_Rejected frames:_"] + [f"- ~~{f.frame}~~ — {f.rationale}" for f in t.rejected_frames]
    return out + [""]


def _entry_block(t: EditorialTreatment) -> list[str]:
    """Cold-reader entry: kernel → payoff → uncertainty → causal honesty → plain subject."""
    if not any((t.news_kernel, t.reader_payoff, t.key_uncertainty, t.plain_subject, t.causal_chain)):
        return []
    out = ["## Reader entry (open with this — before landscape or methodology)"]
    if t.news_kernel:
        out.append(f"**News kernel:** {t.news_kernel}")
    if t.reader_payoff:
        out.append(f"**Why it matters:** {t.reader_payoff}")
    if t.key_uncertainty:
        out.append(f"**Key uncertainty:** {t.key_uncertainty}")
    if t.plain_subject:
        out.append(f"**Plain subject (use before specialist names):** {t.plain_subject}")
    if t.causal_chain:
        out.append("**Causal chain (do not blur these statuses):**")
        for link in t.causal_chain:
            note = f" — {link.note}" if link.note else ""
            out.append(f"- [{link.status}] {link.cause} → {link.effect}{note}")
    return out + [""]


def _concepts_block(t: EditorialTreatment) -> list[str]:
    if not t.concepts:
        return []
    order = {cid: i for i, cid in enumerate(t.reader_path)}
    out = ["## Load-bearing concepts (the molecule)"]
    for c in sorted(t.concepts, key=lambda c: order.get(c.id, len(order))):
        dep = f"  ⟵ depends on: {', '.join(c.depends_on)}" if c.depends_on else ""
        out.append(f"### {c.name}  `{c.id}`{dep}")
        if c.why_load_bearing:
            out.append(f"- load-bearing: {c.why_load_bearing}")
        if c.resolution:
            out.append(f"- resolution: {c.resolution}")
        if c.do_not_overstate:
            out.append(f"- ⚠ do not overstate: {c.do_not_overstate}")
        if c.grounds_in:
            out.append(f"- grounded in: {', '.join(c.grounds_in)}")
    return out + [""]


def _perspectives_block(t: EditorialTreatment) -> list[str]:
    if not t.perspectives:
        return []
    out = ["## Perspective map (every serious side, steelmanned)"]
    for p in t.perspectives:
        refs = f"  _({', '.join(p.grounds_in)})_" if p.grounds_in else ""
        out.append(f"- **{p.label}** `{p.id}`: {p.steelman}{refs}")
    return out + [""]
