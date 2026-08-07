"""
A dropped connection must not throw away a paid-for run.

A rail died mid-gauntlet on one APIConnectionError. The t0 pool, synthesis, the promoted
vector and a fully researched profile had all been bought; the pipeline has no resume, so
recovery meant re-buying them. The outage lasted seconds.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.foundation.models import reconnect


class _ConnDrop(Exception):
    """Stands in for openai.APIConnectionError — matched by NAME, not by import."""


_ConnDrop.__name__ = "APIConnectionError"


def test_a_connection_error_is_recognised() -> None:
    assert reconnect.is_connection_error(_ConnDrop("boom")) is True


def test_a_wrapped_connection_error_is_recognised() -> None:
    """Providers bury the socket failure under their own exception."""
    outer = RuntimeError("call failed")
    outer.__cause__ = _ConnDrop("boom")
    assert reconnect.is_connection_error(outer) is True


def test_a_real_api_answer_is_not_retried() -> None:
    """Auth failures, rate limits and refusals cannot be fixed by waiting."""
    for exc in (ValueError("bad request"), PermissionError("401"), KeyError("nope")):
        assert reconnect.is_connection_error(exc) is False


def test_the_call_is_reissued_once_the_provider_answers(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RECONNECT_INTERVAL_S", "1")
    monkeypatch.setattr(reconnect.time, "sleep", lambda _s: None)
    monkeypatch.setattr(reconnect, "probe", lambda url, timeout=5.0: True)

    calls: list[int] = []

    def _flaky():
        calls.append(1)
        if len(calls) == 1:
            raise _ConnDrop("dropped")
        return "ok"

    said: list[str] = []
    assert reconnect.call_with_reconnect(_flaky, probe_url="http://x", on_wait=said.append) == "ok"
    assert len(calls) == 2
    assert any("waiting" in m for m in said)
    assert any("resuming" in m for m in said)


def test_a_non_connection_error_propagates_immediately(monkeypatch) -> None:
    monkeypatch.setattr(reconnect.time, "sleep", lambda _s: None)

    def _bad():
        raise ValueError("malformed request")

    with pytest.raises(ValueError, match="malformed"):
        reconnect.call_with_reconnect(_bad, probe_url="http://x")


def test_it_gives_up_rather_than_waiting_forever(monkeypatch) -> None:
    """A blip is minutes; an outage should not hold a run — and the lock — for an hour."""
    monkeypatch.setenv("ALGENT_RECONNECT_INTERVAL_S", "1")
    monkeypatch.setenv("ALGENT_RECONNECT_MAX_WAIT_S", "1")
    monkeypatch.setattr(reconnect.time, "sleep", lambda _s: None)
    monkeypatch.setattr(reconnect, "probe", lambda url, timeout=5.0: False)

    def _always_down():
        raise _ConnDrop("still down")

    with pytest.raises(Exception, match="still down"):
        reconnect.call_with_reconnect(_always_down, probe_url="http://x")


def test_the_wait_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_RECONNECT_WAIT", "0")

    def _down():
        raise _ConnDrop("dropped")

    with pytest.raises(Exception, match="dropped"):
        reconnect.call_with_reconnect(_down, probe_url="http://x")


def test_any_http_answer_counts_as_reachable(monkeypatch) -> None:
    """We ask 'is the path open', not 'is this request valid' — a 401 proves reachability."""
    import httpx

    class _Client:
        def __init__(self, **_kw): ...
        def __enter__(self): return self
        def __exit__(self, *_a): return False
        def get(self, _url):
            return httpx.Response(401)

    monkeypatch.setattr(httpx, "Client", _Client)
    assert reconnect.probe("http://x") is True
