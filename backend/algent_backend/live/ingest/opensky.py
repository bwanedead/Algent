"""
OpenSky Network — the world's aircraft in one call (``GET /api/states/all``).

Anonymous access works (400 credits a day); an OpenSky account's API client gives 10x (4 000 a day): set ``ALGENT_OPENSKY_CLIENT_ID``
and ``ALGENT_OPENSKY_CLIENT_SECRET`` (OAuth2 client credentials; register at https://opensky-network.org/, then create an API client
on the Account page). A global call costs 4 credits; the cadence and its arithmetic are in ``flags.py``. The poller reads the
response's ``X-Rate-Limit-Remaining`` and backs off when credits run low or the API answers 429.

OpenSky asks that its data be cited, and its terms are for research and non-commercial use; the /live credit line names it.
State vector columns used: 0 icao24, 1 callsign, 3 time_position, 5 lon, 6 lat, 7 baro altitude (m), 8 on_ground, 9 velocity (m/s),
10 true track. Nothing is stored beyond the live sky board.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable

from .. import flags, store

STATES_URL = "https://opensky-network.org/api/states/all"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
ID_ENV, SECRET_ENV = "ALGENT_OPENSKY_CLIENT_ID", "ALGENT_OPENSKY_CLIENT_SECRET"
SIGNUP = "https://opensky-network.org/"
_M_TO_FT, _MS_TO_KN = 3.28084, 1.943844

#: ``http(method, url, headers, form) -> (status, response headers, body)`` — injectable so tests need no network.
Http = Callable[[str, str, dict[str, str], "dict[str, str] | None"], "tuple[int, dict[str, str], bytes]"]


def _httpx(method: str, url: str, headers: dict[str, str], form: dict[str, str] | None) -> tuple[int, dict[str, str], bytes]:
    import httpx

    r = httpx.request(method, url, headers=headers, data=form, timeout=60)
    return r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.content


def parse_state(row: list[Any], now: float) -> tuple[str, list[Any]] | None:
    """One state vector -> ``(icao24, [lat, lon, heading, speed_kn, seen, class 0, callsign, "", altitude_ft])`` or None when it has
    no usable position or the position is older than ``OPENSKY_MAX_AGE_S``."""
    try:
        icao, call, t_pos, lon, lat = row[0], row[1], row[3], row[5], row[6]
    except (IndexError, TypeError):
        return None
    if not icao or not isinstance(t_pos, (int, float)) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if now - t_pos > flags.OPENSKY_MAX_AGE_S or abs(lat) > 90 or abs(lon) > 180:
        return None
    alt = row[7] if isinstance(row[7], (int, float)) else (row[13] if len(row) > 13 and isinstance(row[13], (int, float)) else None)
    track, vel = row[10], row[9]
    return icao, [float(lat), float(lon), float(track) if isinstance(track, (int, float)) else -1.0,
                  float(vel) * _MS_TO_KN if isinstance(vel, (int, float)) else -1.0, float(min(t_pos, now)), 0,
                  (call or "").strip()[:10], "", 0 if row[8] else int(alt * _M_TO_FT) if alt is not None else -1]


class OpenSky:
    def __init__(self, http: Http | None = None) -> None:
        self.http = http or _httpx
        self.client_id, self.client_secret = os.environ.get(ID_ENV, ""), os.environ.get(SECRET_ENV, "")
        self._token, self._expires = "", 0.0
        self.remaining: int | None = None

    @property
    def authenticated(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def interval(self) -> float:
        """Seconds between calls: the tier's cadence (flags.py credit math), doubled while credits are low."""
        base = flags.OPENSKY_INTERVAL_AUTH_S if self.authenticated else flags.OPENSKY_INTERVAL_ANON_S
        low = self.remaining is not None and self.remaining < flags.OPENSKY_LOW_CREDITS
        return base * (2 if low else 1)

    def _auth_header(self) -> dict[str, str]:
        if not self.authenticated:
            return {}
        if not self._token or time.time() >= self._expires:
            status, _, body = self.http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                                        {"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret})
            if status != 200:
                raise RuntimeError(f"OpenSky token HTTP {status}")
            doc = json.loads(body)
            self._token, self._expires = doc["access_token"], time.time() + float(doc.get("expires_in", 1800)) - 60
        return {"Authorization": f"Bearer {self._token}"}

    def fetch(self) -> list[list[Any]]:
        """The world's state vectors. Raises on HTTP errors (a 429's wait is in the message); updates ``remaining``."""
        status, headers, body = self.http("GET", STATES_URL, {"Accept-Encoding": "gzip", "User-Agent": "ohmega-live/1.0", **self._auth_header()}, None)
        if "x-rate-limit-remaining" in headers:
            try:
                self.remaining = int(float(headers["x-rate-limit-remaining"]))
            except ValueError:
                pass
        if status == 401:
            self._token = ""
        if status != 200:
            raise RuntimeError(f"OpenSky HTTP {status} retry-after {headers.get('x-rate-limit-retry-after-seconds', '')}")
        return json.loads(body).get("states") or []


async def poll_loop(sky: Any, stop_at: float | None, client: OpenSky | None = None) -> None:
    """Fetch the world every ``interval`` seconds and merge it into the sky board. A failed call is logged and retried after the
    interval (a 429 waits what the API asks, at most an hour); the service outlives any failure."""
    cli = client or OpenSky()
    while stop_at is None or time.monotonic() < stop_at:
        wait = cli.interval
        try:
            states = await asyncio.to_thread(cli.fetch)
            n = await asyncio.to_thread(sky.ingest_opensky, states, time.time(), max(flags.CIVIL_TTL_S, 2.5 * cli.interval))
            store.record_status("opensky", last_ok=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), error="",
                                note=f"{len(states)} states, {n} merged; {'account' if cli.authenticated else 'anonymous'}, "
                                     f"credits left {cli.remaining if cli.remaining is not None else '?'}, next in {int(cli.interval)} s")
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {str(exc)[:160]}"
            store.record_status("opensky", error=msg)
            if "HTTP 429" in msg:
                try:
                    wait = min(3600.0, max(wait, float(msg.rsplit("retry-after", 1)[1].strip() or 0)))
                except (ValueError, IndexError):
                    pass
        await asyncio.sleep(wait)
