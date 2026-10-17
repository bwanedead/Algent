"""
"Where we disagree with the market" — the short, labelled line set the daily carries when our forecast and a market's price are far apart.

Mechanical (no model) and attached AFTER the day's sections are written, so the daily's writers never see a market price: the daily informs
our forecasts, and the market is never allowed to inform the daily. Each line says whose number is whose and when ours was made; it is our
forecast, not advice, and the document says so. A disagreement can be OUR error as easily as the market's, and the line does not pretend
otherwise: the track-record page shows who has been right so far.
"""

from __future__ import annotations

from typing import Any

from . import flags, score

NOTE = ("Ohmega's own forecasts set against Polymarket prices, as an internal accuracy check. Paper trading only, not financial advice. "
        "A gap means we disagree, not that we are right: see the track record for who has been closer.")
PAGE = "/intel/track-record"


def daily_view(*, now_iso: str | None = None) -> dict[str, Any] | None:
    """{"note", "page", "lines": [...]} for the daily record, or None when nothing is far enough apart. Never raises."""
    try:
        rows = score.disagreements(now_iso)[:flags.DISAGREE_LINES]
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None
    lines = [{"market_id": r["market_id"], "question": r["question"], "ours": r["ours"], "market": r["market"], "made_at": r["made_at"], "url": r["url"],
              "text": f"{r['question']} Our forecast {r['ours']:.0%} (made {r['made_at']}); the market prices it at {r['market']:.0%}."}
             for r in rows]
    return {"note": NOTE, "page": PAGE, "lines": lines}
