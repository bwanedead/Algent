"""Classify provider failures that waiting cannot fix.

``reconnect`` waits out an unreachable endpoint. A 400 is the opposite: the
endpoint answered, and this request is unusable. Retrying the same payload
cannot help; the caller must clip, skip the lane, or otherwise change course.
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
