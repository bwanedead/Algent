"""
Provider health + short circuit breaker for the web_search facade.

When Tavily (or another engine) is over quota, live runs used to repeat the same terminal
failure a dozen times. This module remembers recent hard failures per provider and opens a
short cooldown so the facade can fall through to an alternate engine instead of retrying a
dead one.

The cooldown ESCALATES per provider: each consecutive hard failure doubles it (120s, 240s, ...
capped at 1h) and a success resets it. A scraping engine's block (DuckDuckGo's challenge page)
outlasts two minutes, and probing it again every two minutes just extends the block; a flat
cooldown keeps knocking on a door that stays shut. Paid-quota failures escalate harmlessly too.
"""

from __future__ import annotations

import threading
import time
from typing import Any

# Hard-failure fingerprints that should trip the breaker (quota / rate / auth).
_HARD_MARKERS = (
    "429",
    "432",  # Tavily quota exhaustion seen in Amazon 0041
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "insufficient",
    "payment required",
    "unauthorized",
    "401",
    "403",
)

_COOLDOWN_S = 120.0  # first hard failure: stay off the provider for two minutes
_MAX_COOLDOWN_S = 3600.0  # escalation ceiling: one hour
_lock = threading.Lock()
_open_until: dict[str, float] = {}  # provider -> monotonic deadline
_strikes: dict[str, int] = {}  # provider -> consecutive hard failures (drives escalation)


def is_open(provider: str) -> bool:
    """True when ``provider`` is currently circuit-open (should be skipped)."""
    with _lock:
        until = _open_until.get(provider, 0.0)
        if until <= time.monotonic():
            _open_until.pop(provider, None)
            return False
        return True


def record_failure(provider: str, error: Any) -> bool:
    """Open the circuit if ``error`` looks like a hard provider failure. Returns whether opened."""
    text = str(error or "").lower()
    if not any(m in text for m in _HARD_MARKERS):
        return False
    with _lock:
        strikes = _strikes.get(provider, 0)
        _strikes[provider] = strikes + 1
        _open_until[provider] = time.monotonic() + min(_COOLDOWN_S * 2**strikes, _MAX_COOLDOWN_S)
    return True


def record_success(provider: str) -> None:
    """Clear a circuit after a successful call."""
    with _lock:
        _open_until.pop(provider, None)
        _strikes.pop(provider, None)


def reset() -> None:
    """Test helper — clear all circuits."""
    with _lock:
        _open_until.clear()
        _strikes.clear()
