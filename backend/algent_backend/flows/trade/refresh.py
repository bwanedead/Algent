"""
The trade picture — which exporters and commodities we ask UN Comtrade about, the best partner flows kept, and the cache between runs.

GRAIN: wheat (HS 1001), maize (HS 1005) and soybeans (HS 1201) from the large exporters that file with Comtrade: for each, its strongest
partners by value, with tonnes. MONEY: total merchandise exports of the largest economies to their strongest partners, in US dollars.
Both are ANNUAL values as the exporting country reported them (the newest year it has filed), so a flow is a year's trade, not a
shipment, and each exporter may be at a different year. Exporters that file nothing (Russia since 2022) are listed as missing, never
estimated. A refresh is ~60 rate-limited calls (a couple of minutes) and happens at most every ``TRADE_REFRESH_DAYS``; a failed exporter keeps its
previous flows. Keyed sources that would give weekly shipments (USDA FAS export sales / GATS, api.data.gov key) are listed in
docs/architecture/flows.md, not used.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import flags, store
from . import comtrade
from .countries import BY_ISO

_FILE = "trade.json"

#: commodity -> (label, HS code, exporters). Exporters are the large ones that file with Comtrade.
GRAIN: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "wheat": ("Wheat", "1001", ("US", "CA", "FR", "AU", "AR", "DE", "RO", "BG", "UA", "KZ", "PL", "HU")),
    "maize": ("Corn (maize)", "1005", ("US", "BR", "AR", "UA", "FR", "RO", "HU", "PL")),
    "soy": ("Soybeans", "1201", ("BR", "US", "AR", "PY", "UY", "CA", "UA")),
}
#: The largest merchandise exporters (order is irrelevant). Each is asked for total exports.
MONEY_EXPORTERS: tuple[str, ...] = ("US", "CN", "DE", "JP", "NL", "KR", "FR", "GB", "IT", "IN", "CA", "MX", "ES", "SA", "AE", "SG", "TR", "BR", "AU", "CH")


def _years(now: datetime) -> list[int]:
    return [now.year - 1 - i for i in range(flags.TRADE_YEARS_BACK)]


def _gather(label: str, cmd: str, exporters: tuple[str, ...], top: int, now: datetime, get: Callable[..., str] | None,
            sleep: Callable[[float], None]) -> dict[str, Any]:
    flows: list[dict[str, Any]] = []
    missing: list[str] = []
    for iso in exporters:
        country = BY_ISO[iso]
        try:
            found = comtrade.fetch_exports(country.codes[0], iso, cmd, _years(now), get=get, sleep=sleep)
        except Exception:  # noqa: BLE001 - one exporter down must not stop the rest
            found = []
        sleep(flags.COMTRADE_GAP_S)
        if not found:
            missing.append(iso)
            continue
        for f in sorted(found, key=lambda x: -x.usd)[:top]:
            flows.append({"from": f.src, "to": f.dst, "period": f.period, "usd": round(f.usd), "t": round(f.kg / 1000.0)})
    return {"label": label, "code": cmd, "flows": flows, "missing": missing}


def fetch(now: datetime | None = None, *, get: Callable[..., str] | None = None, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Ask Comtrade for the whole picture. Returns the trade document (not yet cached)."""
    now = now or datetime.now(timezone.utc)
    grain = {k: _gather(label, cmd, ex, flags.GRAIN_TOP_PARTNERS, now, get, sleep) for k, (label, cmd, ex) in GRAIN.items()}
    money = _gather("Merchandise exports", "TOTAL", MONEY_EXPORTERS, flags.MONEY_TOP_PARTNERS, now, get, sleep)
    return {"v": 1, "fetched_at": now.isoformat(timespec="seconds"), "source": "UN Comtrade (public preview API), exporter-reported annual values",
            "source_url": comtrade.SOURCE_URL, "grain": grain, "money": money}


def load() -> dict[str, Any] | None:
    return store.read_json(_FILE)


def stale(doc: dict[str, Any] | None, now: datetime) -> bool:
    if not doc or not doc.get("fetched_at"):
        return True
    return now - datetime.fromisoformat(doc["fetched_at"]) > timedelta(days=flags.TRADE_REFRESH_DAYS)


def merge(new: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
    """A commodity or exporter the new fetch missed keeps its previous flows (a provider hiccup must not blank an arc)."""
    if not old:
        return new

    def keep(fresh: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
        if not prior:
            return fresh
        have = {f["from"] for f in fresh["flows"]}
        carried = [f for f in prior.get("flows", []) if f["from"] in fresh["missing"] and f["from"] not in have]
        still_missing = [m for m in fresh["missing"] if m not in {f["from"] for f in carried}]
        return {**fresh, "flows": fresh["flows"] + carried, "missing": still_missing}

    out = dict(new)
    out["grain"] = {k: keep(v, (old.get("grain") or {}).get(k)) for k, v in new["grain"].items()}
    out["money"] = keep(new["money"], old.get("money"))
    return out


def refresh(now: datetime | None = None, *, force: bool = False, get: Callable[..., str] | None = None,
            sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """The cached trade picture, refreshed first when it is older than ``TRADE_REFRESH_DAYS`` (or ``force``). Never raises: on failure
    the previous cache stands."""
    now = now or datetime.now(timezone.utc)
    cached = load()
    if cached and not force and not stale(cached, now):
        return cached
    try:
        doc = merge(fetch(now, get=get, sleep=sleep), cached)
    except Exception:  # noqa: BLE001
        return cached or {}
    if any(c["flows"] for c in doc["grain"].values()) or doc["money"]["flows"]:
        store.write_json(_FILE, doc)
        return doc
    return cached or doc
