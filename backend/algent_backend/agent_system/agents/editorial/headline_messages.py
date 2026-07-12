"""The headline task message — the finished prose + a task to convey it truthfully."""

from __future__ import annotations

from .draft import ArticleDraft


def build_headline_message(draft: ArticleDraft) -> str:
    lines = [
        "# WRITE THE HEADLINE — for the finished piece below",
        "",
        f"Working title (improve on it if you can): {draft.title}",
    ]
    if draft.frame:
        lines.append(f"Frame the piece was written from: {draft.frame}")
    lines += [
        "",
        "## The finished article",
        draft.body.strip(),
        "",
        "TASK: Write a headline + standfirst that conveys what THIS article actually says, at the "
        "confidence its evidence supports — plain, specific, no deception. Emit a Headline.",
    ]
    return "\n".join(lines)
