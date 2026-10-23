"""The smoke test's one HTTP call: stdlib only, redirects NOT followed (a redirect is a result), every failure a reply and never an exception."""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from . import flags


@dataclass
class Reply:
    status: int                       # 0 when no HTTP answer came back (timeout, DNS, TLS)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    ms: int = 0
    error: str = ""

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


#: ``fetch(url) -> Reply``: injectable so tests need no network.
Fetch = Callable[[str], Reply]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201 - urllib's signature
        return None


def default_fetch(url: str) -> Reply:
    opener = urllib.request.build_opener(_NoRedirect)
    headers = {"User-Agent": flags.USER_AGENT, "Accept": "*/*"}
    if (secret := os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET", "").strip()):          # lets the check through a preview's deployment protection
        headers["x-vercel-protection-bypass"] = secret
    req = urllib.request.Request(url, headers=headers)
    t0 = time.monotonic()
    try:
        with opener.open(req, timeout=flags.TIMEOUT_S) as resp:      # noqa: S310 - the URL is the operator's own site
            body = resp.read()
            return Reply(resp.status, {k.lower(): v for k, v in resp.headers.items()}, body, int((time.monotonic() - t0) * 1000))
    except urllib.error.HTTPError as exc:                            # 3xx (not followed), 4xx, 5xx: an answer
        body = exc.read() if exc.fp else b""
        return Reply(exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, body, int((time.monotonic() - t0) * 1000))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return Reply(0, error=f"{type(exc).__name__}: {str(getattr(exc, 'reason', exc))[:120]}", ms=int((time.monotonic() - t0) * 1000))
