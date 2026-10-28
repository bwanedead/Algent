"""
Reasoning methods for the live strategies. A strategy's mind is one of the lab's (``experiment/minds.py``), named by the lab's own id (``experiment/qset.NAMED``):

    p0b         baseline research (no addendum: the base role is the whole method)
    p0b+prior   base rate first        b   delineation        b+prior   delineation + base rate

The lab owns the instruction text and the output fields; this module only reads them (lazily: ``markets`` must not import the lab at import time), so a
change to a mind in the lab changes the live bot too. In the live loop the lab's structured answer has no place of its own, so its working fields are
written into one free-text ``basis`` on each order (stored on the ledger line), and ``probability_pct`` / ``rationale`` / ``cited`` map to the order's
``p_yes`` / ``reason`` / ``cited``.
"""

from __future__ import annotations

from dataclasses import dataclass

NAMES = {"p0b": "Baseline research", "p0b+prior": "Base rate first", "b": "Delineation", "b+prior": "Delineation + base rate"}
_MAPPED = {"probability_pct", "rationale", "cited", "evidence", "gap_topic", "gap_why"}      # carried by p_yes / reason / cited / wishes instead


@dataclass(frozen=True)
class Method:
    id: str
    name: str
    addendum: str                         # the lab's instruction text ("" for the baseline)
    fields: tuple[tuple[str, str], ...]   # (field, description) the lab asks for as working, in the lab's order


def get(method_id: str) -> Method:
    if method_id not in NAMES:
        raise KeyError(f"unknown reasoning method {method_id!r}; the lab ids are {sorted(NAMES)}")
    if method_id == "p0b":
        return Method(method_id, NAMES[method_id], "", ())
    from algent_backend.experiment import minds

    text, schema = {"p0b+prior": (minds.PRIOR_ADDENDUM, "prior"), "b": (minds.DELINEATION_ADDENDUM, "delineation"),
                    "b+prior": (minds.DELINEATION_ADDENDUM + minds.PRIOR_ADDENDUM, "delineation")}[method_id]
    fields = tuple((k, v.description or "") for k, v in minds.SCHEMAS[schema].model_fields.items() if k not in _MAPPED)
    return Method(method_id, NAMES[method_id], text, fields)


def section(method_id: str) -> str:
    """The role text that makes the agent form its own probability the lab's way. Empty for the baseline (the day book's role is unchanged)."""
    m = get(method_id)
    if not m.addendum:
        return ""
    rows = "\n".join(f"  - {k}: {d}" for k, d in m.fields)
    return (f"\nHOW YOU FORM A PROBABILITY ({m.name}). This is your method; use it for every market you buy or sell. Here p_yes is a FRACTION (0.07 means 7%) and "
            f"your reason is the `rationale`.{m.addendum}\n\nWrite your working for the market in the order's `basis` field, in plain text, covering these in this order:\n{rows}\n")
