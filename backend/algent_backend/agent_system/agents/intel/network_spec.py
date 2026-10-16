"""
The network contract: who backs, funds, arms, opposes or depends on whom (daily visual kind ``network``, native).

Data, never code: ``components/NativeNetwork.tsx`` lays it out and animates it. An edge is one relation between two
nodes; its direction is the arrow (``forward``: source acts on target) or a two-way link (``both``). Edges may carry
a ``start`` and an ``end`` date: the picture then has a time scrubber, and a relation that changes is two edges.

The model fills this schema directly (no unions, so it is also the wire schema: ``from_wire`` is the identity and
``ground`` enforces every size limit, trimming rather than failing).

Grounding (``ground``): an edge cites facts of the day and BOTH of its ends must be named in them; a start or end
date must be stated by a cited fact; words carry no number the facts lack. A node's size (``weight``) is a figure its
own cited facts hold and means the one thing ``weight_label`` says. What fails is dropped and named in the report; a
node no surviving edge touches goes with them; too few nodes or edges refuses the network.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .timeline_spec import Source, valid_date
from .visuals_grounding import mentions_date, mentions_entity, ungrounded, word_count

Kind = Literal["state", "group", "person", "org", "place"]
Relation = Literal["supports", "arms", "funds", "allied_with", "opposes", "attacks", "sanctions", "trades", "depends_on", "negotiates_with"]
Direction = Literal["forward", "both"]

#: The families the picture colours by: one colour per meaning (backing, hostility, exchange, talks).
FAMILY: dict[str, str] = {"supports": "backing", "arms": "backing", "funds": "backing", "allied_with": "backing",
                          "opposes": "hostile", "attacks": "hostile", "sanctions": "hostile",
                          "trades": "exchange", "depends_on": "exchange", "negotiates_with": "talks"}
PHRASE: dict[str, str] = {"supports": "supports", "arms": "arms", "funds": "funds", "allied_with": "is allied with", "opposes": "opposes",
                          "attacks": "attacks", "sanctions": "sanctions", "trades": "trades with", "depends_on": "depends on",
                          "negotiates_with": "negotiates with"}
MIN_NODES, MAX_NODES, MIN_EDGES, MAX_EDGES = 3, 16, 3, 30
LABEL_WORDS, DETAIL_WORDS = 5, 20


class Node(BaseModel):
    id: str
    label: str                      # at most LABEL_WORDS words
    kind: Kind = "group"
    iso: str = ""                   # alpha-2 code of a state (or the state a non-state belongs to), else ""
    weight: float = 0.0             # size on the picture; 0 = not sized. A figure its ``fact_ids`` hold
    fact_ids: list[str] = Field(default_factory=list)    # only for ``weight``


class Edge(BaseModel):
    id: str
    source: str                     # a ``Node.id``
    target: str
    relation: Relation
    direction: Direction = "forward"
    strength: int = 2               # 1 minor, 2 clear, 3 major: 3 only where a cited fact stresses scale
    detail: str = ""                # at most DETAIL_WORDS words, only from the cited facts
    start: str = ""                 # YYYY-MM-DD the relation begins (a fact states it), "" = already so
    end: str = ""                   # YYYY-MM-DD it ends, "" = still so
    fact_ids: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)      # filled from the cited facts by the producer


class Network(BaseModel):
    title: str
    caption: str
    weight_label: str = ""          # what node size means ("defence budget, USD bn"); "" = no node is sized
    nodes: list[Node]
    edges: list[Edge]
    alt: str = ""


NetworkWire = Network               # no unions in this schema: the strict spec is what the model fills


def from_wire(wire: Network) -> tuple[Network, list[str]]:
    return wire, []


def frame_dates(net: Network) -> list[str]:
    """The dates the picture changes on (a relation begins or ends), oldest first: the scrubber's stops."""
    return sorted({d for e in net.edges for d in (e.start, e.end) if d})


def _edge_problem(e: Edge, labels: dict[str, str], facts: dict[str, str]) -> str:
    e.fact_ids = e.fact_ids[:6]
    cited = " ".join(facts[x] for x in dict.fromkeys(e.fact_ids) if x in facts)
    if not cited or not all(x in facts for x in e.fact_ids):
        return "cites no fact of the visual (or one that is not)"
    if e.source == e.target or e.source not in labels or e.target not in labels:
        return "its ends are not two distinct nodes"
    for end in (e.source, e.target):
        if not mentions_entity(cited, labels[end]):
            return f"{labels[end]!r} is not named by its facts"
    for d in (e.start, e.end):
        if d and not (valid_date(d) and mentions_date(cited, d)):
            return f"no cited fact states {d!r}"
    if e.start and e.end and e.end < e.start:
        return "ends before it starts"
    if word_count(e.detail) > DETAIL_WORDS:
        return f"detail over {DETAIL_WORDS} words"
    if bad := ungrounded(e.detail, cited):
        return f"detail carries numbers not in its facts ({', '.join(bad[:2])})"
    return ""


def ground(net: Network, facts: dict[str, str]) -> list[str]:
    """Drop nodes and edges the cited facts do not carry (in place); return a line per drop or fix, then any
    spec-level problem prefixed ``REFUSED``. ``facts`` maps fact id to text (the visual's cited facts)."""
    notes: list[str] = []
    nodes: dict[str, Node] = {}
    for n in net.nodes:
        if not n.id.strip() or n.id in nodes or not n.label.strip() or word_count(n.label) > LABEL_WORDS:
            notes.append(f"node {n.id or n.label[:20]!r} dropped: no id, duplicate, or label empty or over {LABEL_WORDS} words")
            continue
        n.iso = n.iso.upper() if len(n.iso) == 2 and n.iso.isalpha() else ""
        n.fact_ids = n.fact_ids[:6]
        cited = " ".join(facts[x] for x in dict.fromkeys(n.fact_ids) if x in facts)
        if n.weight:
            if n.weight < 0 or not net.weight_label.strip() or not cited or ungrounded(f"{n.weight:g}", cited):
                notes.append(f"node {n.id!r}: size cleared: not a figure its facts hold")
                n.weight = 0.0
        nodes[n.id] = n
    labels = {i: n.label for i, n in nodes.items()}
    edges: list[Edge] = []
    seen: set[tuple] = set()
    for e in net.edges:
        key = (e.source, e.target, e.relation, e.start)
        if not e.id.strip() or e.id in {x.id for x in edges} or key in seen:
            notes.append(f"edge {e.id!r} dropped: no id or a duplicate")
        elif why := _edge_problem(e, labels, facts):
            notes.append(f"edge {e.id!r} ({e.source}->{e.target}) dropped: {why}")
        else:
            seen.add(key)
            e.strength = min(3, max(1, e.strength))
            edges.append(e)
    if len(edges) > MAX_EDGES:
        notes.append(f"{len(edges) - MAX_EDGES} edges over the limit of {MAX_EDGES} dropped")
        edges = edges[:MAX_EDGES]
    used = {i for e in edges for i in (e.source, e.target)}
    net.nodes = [n for i, n in nodes.items() if i in used][:MAX_NODES]
    keep = {n.id for n in net.nodes}
    net.edges = [e for e in edges if e.source in keep and e.target in keep]
    if not any(n.weight for n in net.nodes):
        net.weight_label = ""
    if len(net.nodes) < MIN_NODES or len(net.edges) < MIN_EDGES:
        notes.append(f"REFUSED: {len(net.nodes)} nodes and {len(net.edges)} grounded edges, need {MIN_NODES}+ nodes and {MIN_EDGES}+ edges")
    if bad := ungrounded(f"{net.title} {net.caption} {net.weight_label}", " ".join(facts.values())):
        notes.append(f"REFUSED: title, caption or size label carries numbers not in the facts ({', '.join(bad[:3])})")
    return notes


def alt_text(net: Network) -> str:
    """The relations as plain text: the alternative to the animated picture."""
    by = {n.id: n.label for n in net.nodes}
    lines = [f"{by.get(e.source, e.source)} {PHRASE[e.relation]} {by.get(e.target, e.target)}" +
             (f" (from {e.start})" if e.start else "") + (f" (until {e.end})" if e.end else "") +
             (f": {e.detail}" if e.detail else ".") for e in net.edges]
    return f"{net.title}. {net.caption} " + " ".join(ln if ln.endswith(".") else ln + "." for ln in lines)
