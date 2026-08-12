"""
Wait out a network blip instead of throwing away a paid-for run.

A rail died mid-gauntlet on a single ``APIConnectionError``. Everything upstream — the t0
pool, synthesis, the promoted vector, and a fully researched profile — had already been
bought, and the pipeline has no resume, so recovering meant re-buying all of it. The
outage itself lasted seconds.

The fix is not checkpointing (large, and the wrong layer for a transient socket). It is to
stop treating a connection error as terminal at the one boundary where it originates: hold
the call, poll the provider until it answers, then let the same call proceed. Nothing
upstream is lost because nothing upstream is unwound — the graph node never returns.

Deliberately narrow. A connection error means "the endpoint is unreachable"; it is not an
auth failure, a rate limit, a bad request or a refusal, and none of those are retried here
because waiting cannot fix them. The probe is a bare HTTP GET against the provider's base
URL, which costs nothing and consumes no tokens.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, TypeVar

_ENV_ENABLED = "ALGENT_RECONNECT_WAIT"
_ENV_INTERVAL = "ALGENT_RECONNECT_INTERVAL_S"
_ENV_MAX_WAIT = "ALGENT_RECONNECT_MAX_WAIT_S"

DEFAULT_INTERVAL_S = 30.0
#: Give up after this long. A blip is minutes; an outage is not something to sit through
#: silently for an hour holding a lock, so the run still fails eventually — just not on the
#: first dropped packet.
DEFAULT_MAX_WAIT_S = 900.0

T = TypeVar("T")


def enabled() -> bool:
    return os.environ.get(_ENV_ENABLED, "1").strip().lower() not in ("0", "false", "no", "off")


def _float_env(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.environ.get(name, "") or default))
    except ValueError:
        return default


def is_connection_error(exc: BaseException) -> bool:
    """Is this 'the endpoint is unreachable', as opposed to a real API answer?

    Matched by TYPE NAME rather than by importing provider SDKs: this module must not care
    whether the client underneath is OpenAI-shaped, Anthropic-shaped or something added
    later, and importing every SDK to catch its errors is exactly the coupling the model
    target exists to prevent.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        name = type(cur).__name__
        if name in {
            "APIConnectionError", "APITimeoutError", "ConnectionError", "ConnectTimeout",
            "ReadTimeout", "ConnectError", "RemoteProtocolError", "TimeoutException",
            "ServiceUnavailableError", "InternalServerError",
            # A gateway timeout is the provider giving up on its own slow request. It is not a
            # judgement about our input, so retrying is right — and not retrying it cost a full
            # rail run once, 31 minutes in.
            "GatewayTimeoutError", "APIStatusError", "Timeout",
        }:
            return True
        # Same shape arriving as a status code rather than a distinct class.
        if getattr(cur, "status_code", None) in (408, 502, 503, 504):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def probe(url: str, *, timeout: float = 5.0) -> bool:
    """Is the provider answering at all? Any HTTP response counts — even 401 or 404.

    We are asking "is the network path open", not "is this request valid". A 401 from the
    base URL proves the host is reachable, which is the whole question.
    """
    if not url:
        return True     # nothing to probe against; assume reachable and let the call decide
    try:
        import httpx

        with httpx.Client(timeout=timeout) as http:
            http.get(url)
        return True
    except Exception:  # noqa: BLE001 — any failure to reach it means keep waiting
        return False


def call_with_reconnect(
    fn: Callable[[], T],
    *,
    probe_url: str = "",
    on_wait: Callable[[str], None] | None = None,
) -> T:
    """Run ``fn``; on a connection error, wait for the provider to answer and run it again.

    ``fn`` must be safe to call again — it is one model request, which is already the unit
    the SDK retries internally, so re-issuing it is no different from its own retry.
    """
    if not enabled():
        return fn()

    interval = _float_env(_ENV_INTERVAL, DEFAULT_INTERVAL_S)
    deadline = time.monotonic() + _float_env(_ENV_MAX_WAIT, DEFAULT_MAX_WAIT_S)
    say = on_wait or (lambda _m: None)

    while True:
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised unless it is a connection drop
            if not is_connection_error(exc) or time.monotonic() >= deadline:
                raise
            say(f"provider unreachable ({type(exc).__name__}); waiting {interval:.0f}s to resume")
            while time.monotonic() < deadline:
                time.sleep(interval)
                if probe(probe_url):
                    say("provider reachable again; resuming")
                    break
            else:
                raise
