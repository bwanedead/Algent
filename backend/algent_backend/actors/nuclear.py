"""
Nuclear status — a small curated, cited table (not fetched: no open machine-readable feed exists).

Source: Federation of American Scientists, "Status of World Nuclear Forces, 2026" (Kristensen, Korda,
Johns, Knight-Boyle), read from the page below on 2026-10-04. Estimates, not official counts. Update
``AS_OF`` and the rows together when FAS publishes a new edition. ``stockpile`` = military stockpile
(active + inactive warheads in military custody); ``inventory`` adds retired warheads awaiting
dismantlement. ``status``: ``npt_recognised`` (the five NPT nuclear-weapon states), ``outside_npt``
(India, Pakistan, North Korea) or ``undeclared`` (Israel keeps a policy of ambiguity).
"""

from __future__ import annotations

SOURCE_URL = "https://fas.org/initiatives/status-world-nuclear-forces/"
AS_OF = 2026

_ROWS: dict[str, tuple[str, int, int]] = {      # iso2 -> (status, stockpile, inventory)
    "RU": ("npt_recognised", 4400, 5420), "US": ("npt_recognised", 3700, 5042), "FR": ("npt_recognised", 290, 370),
    "CN": ("npt_recognised", 620, 620), "GB": ("npt_recognised", 225, 225), "IL": ("undeclared", 90, 90),
    "PK": ("outside_npt", 170, 170), "IN": ("outside_npt", 190, 190), "KP": ("outside_npt", 60, 60),
}


def nuclear(iso2: str) -> dict | None:
    """{"status","stockpile","inventory","year","source_url"} for a nuclear-armed state, else None."""
    row = _ROWS.get((iso2 or "").upper())
    if row is None:
        return None
    return {"status": row[0], "stockpile": row[1], "inventory": row[2], "year": AS_OF, "source_url": SOURCE_URL}


def armed_states() -> list[str]:
    return sorted(_ROWS)
