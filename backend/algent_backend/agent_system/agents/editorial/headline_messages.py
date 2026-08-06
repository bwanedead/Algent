"""The headline task message — the finished prose + planned entry fields + surface-package task."""

from __future__ import annotations

from .draft import ArticleDraft
from .treatment import EditorialTreatment


def build_headline_message(
    draft: ArticleDraft,
    treatment: EditorialTreatment | None = None,
    *,
    surface_issues: list[str] | None = None,
) -> str:
    lines = [
        "# WRITE THE FINAL SURFACE PACKAGE — for the finished piece below",
        "",
        f"Working title (improve on it if you can): {draft.title}",
    ]
    if draft.frame:
        lines.append(f"Frame the piece was written from: {draft.frame}")
    if treatment is not None:
        lines += ["", "## Planned reader entry (revise if the final prose moved)"]
        if treatment.news_kernel:
            lines.append(f"- news_kernel: {treatment.news_kernel}")
        if treatment.reader_payoff:
            lines.append(f"- reader_payoff: {treatment.reader_payoff}")
        if treatment.key_uncertainty:
            lines.append(f"- key_uncertainty: {treatment.key_uncertainty}")
        if treatment.plain_subject:
            lines.append(f"- plain_subject: {treatment.plain_subject}")
        if treatment.reader_question:
            lines.append(f"- reader_question: {treatment.reader_question}")
        for link in treatment.causal_chain:
            note = f" ({link.note})" if link.note else ""
            lines.append(
                f"- causal: [{link.status}] {link.cause} → {link.effect}{note}"
            )
        if draft.quick_take.filled():
            lines += [
                "",
                "## Current quick_take (revise if incomplete or stale)",
                f"- what_happened: {draft.quick_take.what_happened}",
                f"- why_it_matters: {draft.quick_take.why_it_matters}",
                f"- what_is_uncertain: {draft.quick_take.what_is_uncertain}",
            ]
    if surface_issues:
        lines += [
            "",
            "## COLD-BROWSER REPAIR — fix these before emitting",
            *[f"- {issue}" for issue in surface_issues],
            "The prior surface package failed a cold-browser check. Rewrite title / standfirst "
            "/ quick_take so a reader who has never heard of this beat understands the subject "
            "and stakes. When plain_subject is set, put that plain description in the title "
            "(or dek) before any guild name.",
        ]
    lines += [
        "",
        "## The finished article",
        draft.body.strip(),
        "",
        "TASK: Write the final surface package — headline, standfirst, quick_take "
        "(what_happened / why_it_matters / what_is_uncertain), image_subject, image_hook. "
        "Cold-browser test: title + dek + hook must make sense without reading the body. "
        "Specialist names need plain_subject first. Emit a Headline.",
    ]
    return "\n".join(lines)
