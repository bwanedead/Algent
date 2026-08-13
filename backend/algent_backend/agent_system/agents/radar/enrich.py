"""
The radar enrichment pass — look the lead up before saying anything about it.

The first radar posts were headline flips: a wire line went in, the same fact came out in our
own words. That is cheap and nearly worthless, and two live posts showed why.

    "At least three people died in storms across the U.S. Midwest."

A reader already knew, with high confidence, that people die in Midwest storms. No date, no
place, no scale, no cause — the post moved their picture of the world by almost nothing. Judged
as information rather than as a sentence, it carried none: it eliminated no uncertainty.

    "A steel beam fell onto a bridge on Germany's A81 autobahn..."

True, and days old. A wire line does not say when it happened, and a pool item can be stale, so
a lane that never checks will confidently report last week as though it were now.

So each candidate gets one search before it becomes a post. The model looks it up, and the search
answers the three things the wire line cannot: IS IT RECENT, WHAT ARE THE SPECIFICS, and IS IT
WORTH SAYING AT ALL. A lead that turns out to be stale or empty is dropped here rather than
padded into a sentence.

Cost is per candidate, which is the point: the sweep already narrowed a hundred pool items to a
handful, and a search each on that handful is what turns a headline flip into something a reader
gains from.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
from algent_backend.agent_system.foundation.models.resolver import ModelResolver
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt
from algent_backend.publishing.x_client import CARD, billable_length

#: One search-backed call per candidate. Low effort, but the search is the expensive half and
#: the reason the lane is worth anything.
DEFAULT_MODEL: ModelSpec = house_spec(reasoning_effort="low", temperature=0.3)
COST_CAP_USD = 0.15


class EnrichedPost(BaseModel):
    """One lead, looked up and either written properly or abandoned."""

    verdict: Literal["post", "drop"] = "drop"
    #: The finished post. Empty when dropping.
    text: str = ""
    #: What the search established that the wire line did not — for the operator, never posted.
    added: str = ""
    #: Why it was dropped: stale, unverifiable, or too thin to carry information.
    reason: str = ""
    #: URLs the search actually used, so a claim can be traced after the fact.
    sources: list[str] = Field(default_factory=list)


ENRICH_ROLE = """\
You are writing one short post for a newsroom account, from a raw wire line. Before you write it,
SEARCH THE WEB and find out what actually happened.

The wire line is a lead, not the story. It is often vague, sometimes days old, and never has the
detail that makes a post worth reading. Look it up.

WHAT THE SEARCH IS FOR, in order:

1. IS IT STILL NEWS? Find when it happened. If it is more than about two days old and nothing has
   developed since, DROP it — a stale item posted as though it were current is the fastest way to
   lose a reader's trust, and nobody needs to hear about last Tuesday's road closure.
2. WHAT ARE THE SPECIFICS? Dates, places, numbers, names, what changed, what happens next. This
   is what turns a gesture into information.
3. IS THERE ANYTHING WORTH SAYING TO THIS ACCOUNT'S READERS? Specifics are necessary, not
   sufficient. A mid-cap earnings print, a local road closure, a press-release "strong quarter"
   can be perfectly dated and numbered and still carry nothing this account exists to say.
   Drop promotional wires even when the numbers are real — they are the company talking about
   itself. A consequential company whose result changes something (a platform, a market, a
   policy) is a different case. Sometimes the answer is simply no. Drop it. There is another
   sweep.

THE TEST THE POST MUST PASS. A post must REDUCE UNCERTAINTY THAT MATTERS. Ask what the reader
believed before and what they believe after. If those are the same, or the change is a fact
about a company this account does not already have in its world-picture, the post carried no
information no matter how true it was.

    Fails:   "At least three people died in storms across the U.S. Midwest."
             A reader already assumed people die in Midwest storms. No date, no place, no scale,
             no cause. Nothing was delineated; nothing was ruled out.
    Fails:   "A mid-cap utility reported Q2 EBITDA of $131 million, up 46% year over year."
             Exact, recent, and worthless: putting a company nobody follows into the picture
             does not help anyone.
    Passes:  "Tornadoes across Illinois and Indiana on Monday killed three and left 40,000
             without power, the strongest outbreak there since 2023."
             Now they know when, where, how big, and how it compares.

So: prefer the specific over the general, the number over the adjective, the named place over the
region, and what CHANGED over what merely is. A dry official fact (a rate decision, a plant
going offline) still counts — this lane exists to say those. If after searching you still
cannot say anything specific AND consequential, that is a drop, not a vaguer sentence.

LENGTH IS A HARD BUDGET. About 240 characters, never more than a timeline card. Density is the
craft here: cut the throat-clearing, not the numbers. If it will not fit, the fix is fewer facts
stated fully — never a truncated sentence.

STYLE — the same as the rest of the account:
- The post is the news itself. No header.
- One or two sentences. Short and dense beats long.
- No "BREAKING", no "JUST IN", no emoji, no hashtags, no rhetorical questions, no hype.
- Confidence goes INSIDE the sentence. Never state something and then take it back; if a figure
  is provisional or contested, say whose figure it is.
- Attribute anything that is a claim rather than an established fact.
- A short quote is welcome when it carries something a paraphrase would lose. Quote exactly.
- Never say what the reader should feel or think about it.

HONESTY. Only state what the search actually supports. If sources disagree, either say so in one
clause or drop it. Do not fill a gap with something plausible. List the URLs you relied on in
`sources`.
"""

SYSTEM_PROMPT = compose_system_prompt(UNIVERSAL_AGENT_BASE, ENRICH_ROLE)

#: Press-release mills. A search will confirm the numbers and still produce a post nobody
#: asked for — the OPC Energy Q2 print was exact, recent, and worthless. Cheap to reject
#: here rather than spend a lookup proving a non-story.
_PR_WIRE_HOSTS = (
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
    "accesswire.com",
    "einpresswire.com",
    "newswire.ca",
)

#: Radar is a short notice on purpose, not because X refuses longer posts. The writer
#: will take 25k; this lane still aims at one thought on a timeline card.


def looks_like_wire_pr(text: str) -> bool:
    """True when the lead is a company talking about itself via a press-release wire."""
    blob = (text or "").casefold()
    return any(host in blob for host in _PR_WIRE_HOSTS)


def enrich(
    lead: str,
    *,
    today: str = "",
    url: str = "",
    model_spec: ModelSpec | None = None,
    resolver: ModelResolver | None = None,
) -> EnrichedPost:
    """Look up one lead and write the post, or decide there isn't one. Never raises."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    spec = model_spec or DEFAULT_MODEL
    if looks_like_wire_pr(lead) or looks_like_wire_pr(url):
        return EnrichedPost(verdict="drop", reason="promotional wire")
    ask = "\n".join([
        f"TODAY: {today}" if today else "",
        f"WIRE LINE: {lead}",
        f"URL: {url}" if url else "",
        "",
        "Search for what actually happened, then return an EnrichedPost. Drop it if it is stale, "
        "unverifiable, promotional, or has nothing specific and consequential to say.",
    ]).strip()

    try:
        client = (resolver or ModelResolver()).resolve(spec).client
        # The model's own web search: this pass exists to LOOK THINGS UP, so the tool is the
        # whole point rather than an optional extra.
        model = gate_chat_model(client).bind_tools([{"type": "web_search"}])
        with cost.scoped(COST_CAP_USD, spec.model):
            result = model.with_structured_output(EnrichedPost).invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=ask)],
            )
    except Exception as exc:  # noqa: BLE001 — a failed lookup is a dropped lead, never a crash
        return EnrichedPost(verdict="drop", reason=f"lookup failed: {str(exc)[:140]}")

    if not isinstance(result, EnrichedPost):
        return EnrichedPost(verdict="drop", reason="no structured result")

    text = " ".join((result.text or "").split()).strip()
    if result.verdict != "post" or not text:
        return EnrichedPost(verdict="drop", reason=result.reason or "nothing worth posting",
                            sources=result.sources)
    if billable_length(text) > CARD:
        # Re-ask rather than discard. The search has already been paid for and the facts are in
        # hand; throwing that away over a length overrun was pure waste, and it happened twice
        # in the first enriched sweep.
        shorter = _shorten(text, spec, resolver)
        if not shorter:
            return EnrichedPost(verdict="drop", reason="too long even after a shorten pass",
                                sources=result.sources)
        text = shorter
    result.text = text
    return result


def _shorten(text: str, spec: ModelSpec, resolver: ModelResolver | None) -> str:
    """One attempt at the same post, inside budget. Returns "" if it still will not fit."""
    from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

    room = CARD - 10
    try:
        model = gate_chat_model((resolver or ModelResolver()).resolve(spec).client)
        with cost.scoped(COST_CAP_USD, spec.model):
            out = model.invoke([
                SystemMessage(content=(
                    "Rewrite this post to fit a hard limit, keeping the most valuable facts and "
                    "dropping the least. Do not truncate mid-sentence, do not add anything, and "
                    "do not soften a claim. Return only the rewritten post.")),
                HumanMessage(content=f"LIMIT: {room} characters\n\nPOST: {text}"),
            ])
        candidate = " ".join(str(out.content or "").split()).strip().strip('"')
    except Exception:  # noqa: BLE001
        return ""
    return candidate if candidate and billable_length(candidate) <= room else ""
