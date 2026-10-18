"""
UN Comtrade public preview API — keyless, rate limited, at most 500 rows a call. Exports of one commodity (an HS code) or of everything
(``TOTAL``) from one reporting country to each partner, annual, as the REPORTER filed them: value in US dollars (``primaryValue``) and
net weight in kilograms (``netWgt``, zero for ``TOTAL``). A reporter files with a lag of months to years and a few file nothing at all
(Russia stopped in 2022), so each exporter is asked for its newest year that has data. https://comtradeapi.un.org/

``parse`` and ``fetch_exports`` are the whole of it; the callers (``refresh.py``) choose the exporters and keep the best partners.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, NamedTuple

from algent_backend import polite_http

from .. import flags
from .countries import by_code

URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
SOURCE_URL = "https://comtradeplus.un.org/"
WORLD = 0


class Flow(NamedTuple):
    src: str           # exporter ISO-2
    dst: str           # partner ISO-2
    period: str        # the year the exporter reported
    usd: float
    kg: float


def parse(payload: str, reporter: str) -> list[Flow]:
    """The partner rows of one response as flows from ``reporter`` (ISO-2). The World total, partners we do not place on the map and
    rows without a value are dropped; one partner appearing twice (old and new code) is summed."""
    try:
        data = json.loads(payload).get("data") or []
    except ValueError:
        return []
    out: dict[str, Flow] = {}
    for r in data:
        code = r.get("partnerCode")
        value = r.get("primaryValue")
        if code in (None, WORLD) or not isinstance(value, (int, float)) or value <= 0:
            continue
        partner = by_code(code)
        if partner is None or partner.iso2 == reporter:
            continue
        kg = r.get("netWgt") if isinstance(r.get("netWgt"), (int, float)) else 0.0
        prev = out.get(partner.iso2)
        out[partner.iso2] = Flow(reporter, partner.iso2, str(r.get("period") or ""), float(value) + (prev.usd if prev else 0.0),
                                 float(kg) + (prev.kg if prev else 0.0))
    return list(out.values())


def fetch_exports(reporter_code: int, reporter: str, cmd: str, years: list[int], *, get: Callable[..., str] | None = None,
                  sleep: Callable[[float], None] = time.sleep) -> list[Flow]:
    """Partner flows for the newest of ``years`` the reporter has data for (empty when none). One call per year tried."""
    fetch = get or polite_http.get
    for year in years:
        body = fetch(URL, params={"reporterCode": str(reporter_code), "period": str(year), "cmdCode": cmd, "flowCode": "X"})
        flows = parse(body, reporter)
        if flows:
            return flows
        sleep(flags.COMTRADE_GAP_S)
    return []
