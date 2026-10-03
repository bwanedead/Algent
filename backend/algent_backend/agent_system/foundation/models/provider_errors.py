"""Classify provider failures that waiting cannot fix.

``reconnect`` waits out an unreachable endpoint. A 400 is the opposite: the
endpoint answered, and this request is unusable. Retrying the same payload
cannot help; the caller must clip, skip the lane, or otherwise change course.

A third kind sits between the two: the provider will not serve THIS request in non-streaming
mode (a 504 saying the request "exceeded the non-streaming server time limit"). It looks like
a transient gateway timeout and is not: the identical request will time out identically, so
waiting is futile — the fix is to send it again as a stream.
"""

from __future__ import annotations

_REJECTED_NAMES = frozenset({
    "BadRequestError",
    "InvalidRequestError",
    "BadRequest",
})


def is_rejected_request(exc: BaseException) -> bool:
    """Did the provider refuse this request body (400 / context overflow)?"""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if type(cur).__name__ in _REJECTED_NAMES:
            return True
        if getattr(cur, "status_code", None) == 400:
            return True
        msg = str(cur).lower()
        if "invalid_request_error" in msg or "context_length" in msg or "maximum context" in msg:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


_STREAM_REQUIRED_MARKERS = ("non-streaming server time limit", "use the streaming api")


def is_stream_required(exc: BaseException) -> bool:
    """Did the provider refuse a non-streaming request as too slow/large to serve unstreamed?

    Matched on the message (the status is a plain 504, indistinguishable from a transient one)
    and walked along the cause chain, since SDK/LangChain wrappers bury it.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = str(cur).lower()
        if any(marker in msg for marker in _STREAM_REQUIRED_MARKERS):
            return True
        cur = cur.__cause__ or cur.__context__
    return False
