"""
The profile task message — the selected signal vector handed to the research agent.

The system prompt (``prompts.py``) is fixed doctrine; this renders the one **vector**
to investigate into the run's task message: its thesis, the questions to resolve, and
the t0 grounding the synthesis agent already surfaced (supporting hit ids + any source
URLs) so research starts from real footing.
"""

from __future__ import annotations

from typing import Any

from .x_seeds import is_x_url


def build_vector_message(vector: dict[str, Any]) -> str:
    """Render a selected signal vector (a ResearchVector dict) into the task message."""
    x_seeds = [str(u) for u in (vector.get("x_seed_urls") or []) if u]
    if not x_seeds:
        x_seeds = [str(u) for u in (vector.get("sources") or []) if is_x_url(str(u))]
    x_primary = bool(vector.get("x_primary")) or bool(x_seeds) or any(
        str(h).startswith("x:") for h in (vector.get("supporting_hits") or [])
    )

    lines = [
        "# YOUR ASSIGNMENT — research this signal vector into a signal profile (t2)",
        "",
        f"vector_id: {vector.get('id', '?')}",
        f"title: {vector.get('title', '')}",
        f"type: {vector.get('vector_type', '?')}   suggested effort: {vector.get('research_effort', '?')}",
        f"pillars: {', '.join(vector.get('pillars', [])) or '-'}   "
        f"scope: {', '.join(vector.get('scope', [])) or '-'}",
        f"x_primary: {x_primary}",
        "",
        f"THESIS: {vector.get('thesis', '')}",
        f"WHY IT MATTERS: {vector.get('rationale', '')}",
        "",
        "KEY QUESTIONS TO RESOLVE:",
        *(f"  - {q}" for q in vector.get("key_questions", []) or ["(none specified — define your own)"]),
        "",
        f"t0 supporting hit ids: {', '.join(vector.get('supporting_hits', [])) or '-'}",
        "SEED SOURCES (from synthesis / t0 — verify, don't trust blindly):",
        *(f"  - {u}" for u in vector.get("sources", []) or ["(none — find your own)"]),
        "",
    ]
    if x_primary or x_seeds:
        lines += [
            "# X PRIMARY FOOTING (structural duty — not optional garnish)",
            "This vector is X-linked (supporting hit and/or seed post URL). Prestige wires alone "
            "are a failure mode for this assignment.",
            "You MUST, before finishing the profile (unless paid X budget is refused):",
            "  1) deep-read at least one X URL below via web_search(read_url=...) — the post is "
            "    first-party what-was-said;",
            "  2) run at least one web_search(query=..., source=\"x\") for related first-party / "
            "    official / OSINT posts on this story;",
            "  3) put load-bearing X posts into the source_ledger (source_type primary when the "
            "    account owns the statement) and ground claims accordingly.",
            "X SEED POST URLs:",
            *(f"  - {u}" for u in x_seeds or ["(reconstruct from supporting hit / find via source=x)"]),
            "",
        ]
    lines.append(_DIRECTIVE)
    return "\n".join(lines)


_DIRECTIVE = (
    "TASK: Build this vector's signal profile. Search free-first and READ the sources "
    "you cite. Construct the source ledger and the claim ledger (atomic, graded claims "
    "traced to sources by id) — that is the core. Map the landscape: competing "
    "interpretations, omissions, open questions. "
    "A WIRE REPORT IS A LEAD, NOT THE STORY. When a claim reaches you through an "
    "aggregator — Reuters, AP, a market wire, a summary feed — treat that as notice that "
    "something happened, then go find where it came from. Ask: who originally said this, "
    "and where is that saying? A company statement, filing, tender or press release; a "
    "ministry or regulator document; a paper or dataset; the local-language outlet that "
    "covered it first; shipment, production or procurement figures. You can read any "
    "language, so 'it was only reported in Chinese' is not a limit. Cite the primary "
    "artifact and let the wire be a corroborating mention, not the spine. A profile whose "
    "load-bearing claims all trace to one outlet has not researched the story, it has "
    "re-read the coverage — and it inherits that outlet's framing, omissions and emphasis "
    "wholesale, which is the thing we exist not to do. Where a primary source genuinely "
    "cannot be located, say so in the claim and keep the secondary attribution: an honest "
    "fallback is fine, a default is not. "
    "GATHER THE STANDING STRUCTURE, not only the day's move. A development is only legible "
    "against the system it happens inside, and that baseline is almost never in the source "
    "that reported the news — you have to go and get it. Before you finish, ask what a reader "
    "would need to know about the underlying system for this to mean anything, and collect it "
    "as claims: the composition (what the shares are, of what total), the scale (how big in "
    "units a person can hold), the trend (where it has come from over several years), and the "
    "comparison (how this sits against peers or against its own past). A piece on Europe raising "
    "electricity from 23% to 46% of final energy is thin without the rest of that pie — how much "
    "is oil, gas, coal, nuclear, renewables — because the reader cannot otherwise tell what is "
    "being displaced, or by how much. Peripheral structural facts like these are usually cheap to "
    "source and are what separate a piece that reports an announcement from one that explains a "
    "situation. Missing them is the most common way our articles come out thin. "
    "RESEARCH THE SCOPES, not just the incident. Our default failure is depth without "
    "altitude: we return exhaustive detail about the specific event and almost nothing about "
    "the system it sits inside, so the piece ends up an instruction manual for one occurrence. "
    "Work the question a person watching the whole board would ask. For a development anywhere, "
    "deliberately gather at each of these scales — and record what you find as claims, or "
    "record its absence: "
    "  (1) THE INCIDENT — what happened, where, who did it. "
    "  (2) THE SYSTEM IT SITS IN — what larger flow, market, alliance, supply chain, ecosystem "
    "or institution does this participate in, and what share of it does this represent? "
    "  (3) DEPENDENCIES AND EXPOSURE — who or what relies on this, and how badly? Which "
    "industries, products, countries or populations feel it first, and which are insulated? "
    "  (4) WINNERS AND LOSERS — who gains, who loses, in what currency (money, leverage, "
    "security, time), including within the place it happened. "
    "  (5) THE LARGER STORY IT BELONGS TO — what ongoing contest, trend or structural shift "
    "is this an episode of, and is it a turn in that story or more of the same? "
    "  (6) ADJACENT SYSTEMS — what else moves when this moves. Second-order effects are where "
    "most of the meaning lives and where our profiles are thinnest. "
    "Worked example: a Congo export ban is not fully researched as a policy announcement. It "
    "is researched when the profile also carries Congo's share of world cobalt, which "
    "industries depend on cobalt and how substitutable it is, who holds the refining capacity "
    "the ban is trying to attract, what a buyer does next, and whether Congo has historically "
    "captured or lost value from its own ore. A reader in another country is asking exactly "
    "those questions — what does this do to supply, to prices, to the things I use — and none "
    "of them are answered by more detail about the decree itself. "
    "Not every story reaches every scale, and forcing global significance onto a local event "
    "is its own dishonesty. But you must have LOOKED, and where a scale is genuinely empty, "
    "say so rather than leaving the gap silent. "
    "A profile is not a file on one event; it is a durable piece of what we understand about "
    "the world, so the structural and relational claims you add outlive the news peg that "
    "prompted them. "
    "REQUIRED: fill countries_of_relevance with where this story HAPPENS and who it AFFECTS "
    "(iso2 + name; primary setting first — not every nation mentioned). "
    "The country of an institution that published, reported, funded or operated something is "
    "NOT a place of relevance: a European agency's image of Mars is not a story about Europe, "
    "and a Reuters dispatch from Beijing is not a story about the United Kingdom. These become "
    "the flags a reader sees beside the headline, so they must answer 'where in the world is "
    "this' — if the honest answer is nowhere on Earth (space, the deep ocean, a mathematical "
    "result, a purely online phenomenon), leave the list EMPTY rather than reaching for the "
    "home country of whoever announced it. "
    "If x_primary is true or X seed URLs are listed, fulfill the X PRIMARY FOOTING duties "
    "above so the profile is not wire-only. "
    "Flag (don't compute) analytics needs. "
    "Add derived_leads for adjacent stories. Set an honest profile_status — "
    "insufficient_evidence is a valid result. Return a SignalProfile."
)
