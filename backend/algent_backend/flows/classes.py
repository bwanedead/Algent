"""
Flow classes — what kind of cargo ship a vessel is, as far as AIS lets us say. Pure tables and functions.

AIS ship type 80-89 is a tanker, 70-79 a cargo ship; the second digit only says "hazardous cargo category", never bulk versus
container versus gas. The finer classes therefore come from the broadcast NAME (``LNG``, ``MAERSK``, ``BULK`` ...): a hint that is
right when it fires and silent for the many ships whose names say nothing, so ``bulk``, ``container`` and ``lng`` are floors, and
``cargo`` is "cargo ship, kind not told". Passenger, fishing, military and untyped vessels are not trade flows and are not counted.
"""

from __future__ import annotations

import re

#: Order matters: the document lists classes in this order and the site colours them by id (see components/flows/style.ts).
CLASSES: tuple[tuple[str, str], ...] = (
    ("tanker", "Tankers (oil and products)"),
    ("lng", "Gas carriers (LNG, LPG)"),
    ("bulk", "Bulk carriers (ore, coal, grain)"),
    ("container", "Container ships"),
    ("cargo", "Other cargo ships"),
)
IDS: tuple[str, ...] = tuple(c for c, _ in CLASSES)

_GAS = re.compile(r"\b(LNG|LPG|GAS|METHANE|ETHANE|ETHYLENE|PROPANE|BUTANE|CRYOGENIC)\b")
_BULK = re.compile(r"\b(BULK|BULKER|BULKERS|ORE|GRAIN|COAL|CEMENT|PANAMAX|HANDY|KAMSARMAX)\b")
_BOX = re.compile(r"\b(MAERSK|MSC|CMA|CGM|COSCO|EVER|HAPAG|ZIM|HMM|OOCL|YANG|WAN|CONTAINER|CONTAINERS|SEASPAN|XPRESS|NYK)\b")


def _words(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", (name or "").upper()).strip()


def flow_class(ship_type: int | None, name: str = "") -> str | None:
    """The flow class id for an AIS ship type and broadcast name, or None when the vessel is not a trade carrier."""
    t = ship_type or 0
    words = _words(name)
    if 80 <= t <= 89:
        return "lng" if _GAS.search(words) else "tanker"
    if 70 <= t <= 79:
        if _BOX.search(words):
            return "container"
        if _BULK.search(words):
            return "bulk"
        return "cargo"
    return None
