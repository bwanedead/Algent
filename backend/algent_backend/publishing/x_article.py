"""
Announcing a published article on X.

Publishing to the site and saying so are two different acts, and only the first was automated:
articles went live and the timeline never mentioned them. This closes that, as part of publishing
rather than as a thing to remember afterwards.

The post is a framing line plus the link. It does NOT carry the image: the site already emits
`twitter:card = summary_large_image` with the hero, so X fetches the picture from the page itself
and an upload here would only duplicate it — and would drift the moment a hero was replaced.

Never fatal. A distribution failure must not retroactively fail an article the newsroom already
produced and published honestly, which is the same rule the site publish step follows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SITE_URL = "https://www.ohmega.monster"
#: Which articles we have already announced. Publishing is retryable and `resume` can run twice
#: over the same run, so without this an article gets announced every time it is re-published.
LEDGER = Path("runs_data") / "x_announced.jsonl"

_COMPOSE_CAP_USD = 0.05


def article_url(slug: str) -> str:
    return f"{SITE_URL}/articles/{slug}"


def already_announced(slug: str) -> bool:
    if not slug or not LEDGER.exists():
        return False
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("slug") == slug:
                return True
        except json.JSONDecodeError:
            continue
    return False


def _record(slug: str, url: str, post_url: str) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "slug": slug, "article_url": url, "post_url": post_url,
            "announced_at": datetime.now(UTC).isoformat(),
        }, ensure_ascii=False) + "\n")


COMPOSE_ROLE = """\
Write the X post announcing one of our articles. It is one or two plain sentences plus nothing
else — the link is appended for you, so do not write a URL.

Say what the piece FOUND, not that a piece exists. "We look at what China's renewable target
means" is an announcement of an announcement; "China's 3,500 GW target is a pivot to making wind
and solar behave like firm power" is the finding.

Rules, the same ones the rest of the account follows:
- No "BREAKING", no "JUST IN", no emoji, no hashtags, no "thread below", no rhetorical questions.
- No hype, and no telling the reader what to feel or think about it.
- Confidence goes INSIDE the sentence. Never state a thing and then take it back — if a claim is
  contested or thin, phrase it as what someone says or what the evidence so far shows.
- Do not oversell past what the article supports. The headline and dek are your ceiling.
- One thought. Two sentences at most, and one is often better.

You are given the title, the dek and the article's own gist. Prefer the concrete finding — a
number, a change, a mechanism — over a summary of the topic.
"""


def compose(title: str, dek: str, gist: str = "") -> str:
    """A framing line for the post. Falls back to the title, which is always publishable."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from algent_backend.agent_system.foundation import cost
        from algent_backend.agent_system.foundation.models import house_spec
        from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model
        from algent_backend.agent_system.foundation.models.resolver import ModelResolver
        from algent_backend.agent_system.prompting import (
            UNIVERSAL_AGENT_BASE,
            compose_system_prompt,
        )

        spec = house_spec(reasoning_effort="low", temperature=0.3)
        model = gate_chat_model(ModelResolver().resolve(spec).client)
        prompt = compose_system_prompt(UNIVERSAL_AGENT_BASE, COMPOSE_ROLE)
        body = "\n".join([f"TITLE: {title}", f"DEK: {dek}", f"GIST: {gist}" if gist else ""])
        with cost.scoped(_COMPOSE_CAP_USD, spec.model):
            out = model.invoke([SystemMessage(content=prompt), HumanMessage(content=body)])
        text = out.content if isinstance(out.content, str) else ""
        text = " ".join(str(text).split()).strip().strip('"')
        return text or title
    except Exception:  # noqa: BLE001 — the title alone is a perfectly good announcement
        return title


def announce(slug: str, title: str, dek: str = "", gist: str = "") -> dict[str, Any]:
    """Post the article link. Returns a small report; never raises."""
    from .x_client import LIMIT, XWriteError, billable_length, post, write_configured

    if not slug:
        return {"announced": False, "reason": "no slug"}
    if already_announced(slug):
        return {"announced": False, "reason": "already announced"}
    if not write_configured():
        return {"announced": False, "reason": "X write credentials not configured"}

    url = article_url(slug)
    line = compose(title, dek, gist)
    text = f"{line}\n\n{url}"
    if billable_length(text) > LIMIT:
        # Trim to the title rather than truncating mid-sentence: a clipped framing line reads
        # as a broken post, while the title is a complete thought by construction.
        text = f"{title}\n\n{url}"
        if billable_length(text) > LIMIT:
            return {"announced": False, "reason": "title too long for a post"}

    try:
        result = post(text)
    except XWriteError as exc:
        return {"announced": False, "reason": str(exc)[:200]}
    _record(slug, url, result.url)
    return {"announced": True, "post_url": result.url, "text": text}
