"""
The "recipe lab" block of the track record: the best forecasting recipe the lab has found against the market, raw and recalibrated, and what recalibrating the live bots
would have done. The lab (``experiment/``) is isolated and nothing here imports it: ``newsroom lab block`` writes ``lab_block.json`` beside the lab's store, and this
module only READS that file, defensively. No file, an unreadable file or a malformed one is no block (the page then shows no such section).

Plain numbers only. ``brier_minus_market`` is our Brier minus the market's at the same moment, so below zero beats the market. Nothing in the block changes how any bot trades.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

FILE = "lab_block.json"
STORE_ENV = "ALGENT_EXPERIMENT_STORE"      # the same variable and default the lab's own store uses (experiment/store.py); not imported, to keep the lab isolated
MAX_BINS = 12


def _path() -> Path:
    return Path(os.environ.get(STORE_ENV) or "experiment_store") / FILE


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


def _bins(raw: Any) -> list[dict[str, Any]]:
    out = []
    for b in raw[:MAX_BINS] if isinstance(raw, list) else []:
        if isinstance(b, dict) and (p := _num(b.get("mean_p"))) is not None and (h := _num(b.get("hit_rate"))) is not None:
            out.append({"low": _num(b.get("low")) or 0.0, "high": _num(b.get("high")) or 1.0, "n": int(_num(b.get("n")) or 0), "mean_p": p, "hit_rate": h})
    return out


def _side(raw: Any, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or _num(raw.get("raw")) is None or _num(raw.get("calibrated")) is None:
        return None
    side = {"n": int(_num(raw.get("n")) or 0), "n_fitted": int(_num(raw.get("n_fitted")) or 0), "raw": _num(raw["raw"]), "calibrated": _num(raw["calibrated"]),
            "bins_raw": _bins(raw.get("bins_raw")), "bins_calibrated": _bins(raw.get("bins_calibrated"))}
    side.update({k: str(raw[k])[:240] for k in keys if isinstance(raw.get(k), str)})
    return side


def section() -> dict[str, Any] | None:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    best, live = _side(raw.get("best"), ("protocol",)), _side(raw.get("live"), ("text",))
    if best is None and live is None:
        return None
    return {"as_of": str(raw.get("as_of", ""))[:40], "best": best, "live": live, "basis": str(raw.get("basis", ""))[:400]}
