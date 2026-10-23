"""
Judging one reply. Pure functions: a probe and a reply in, a ``Result`` out (severity ``ok`` / ``warn`` / ``fail`` and the reasons), so every rule is
testable with a fake reply. The rules:

* page: status 200, a real HTML document, none of the "not published" / error copy (``flags.FALLBACK_PATTERNS``), no stale marker on the hubs (warn);
* agent API: status 200, a JSON ``{data, meta}`` envelope with a version, source, cite_as, license and a non-empty ``data``; an ``{error}`` body fails;
* redirect: a 3xx to exactly the expected place;
* freshness (``meta.as_of``): not older than ``FRESH_CADENCES`` x the product's registry cadence;
* every request: time recorded; slower than ``SLOW_MS`` warns; no answer at all fails.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from algent_backend.ops.products import views

from . import flags
from .fetch import Reply
from .probes import Probe

OK, WARN, FAIL = "ok", "warn", "fail"
_RANK = {OK: 0, WARN: 1, FAIL: 2}
_FALLBACK = re.compile("|".join(flags.FALLBACK_PATTERNS), re.IGNORECASE)
_TAGS = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ENVELOPE_META = ("as_of", "source", "version", "cite_as", "license")


@dataclass
class Result:
    path: str
    kind: str
    status: int
    ms: int
    severity: str = OK
    notes: list[str] = field(default_factory=list)
    why: str = ""

    def flag(self, severity: str, note: str) -> None:
        self.notes.append(note)
        if _RANK[severity] > _RANK[self.severity]:
            self.severity = severity

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "kind": self.kind, "status": self.status, "ms": self.ms, "severity": self.severity, "notes": self.notes, "why": self.why}


def _visible_text(html: str) -> str:
    """The page's text without scripts and styles (Next embeds its data payload in scripts; a pattern must match what a reader sees)."""
    return re.sub(r"<[^>]+>", " ", _TAGS.sub(" ", html))


def parse_stamp(stamp: str) -> tuple[datetime, bool] | None:
    """(instant, is_bare_day) of a freshness stamp, or None when unreadable."""
    s = (stamp or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.fromisoformat(s).replace(tzinfo=UTC), True
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (t if t.tzinfo else t.replace(tzinfo=UTC)), False
    except ValueError:
        return None


def cadence_minutes(product_id: str) -> float:
    """The shortest interval between runs of the product's timers (the registry's ``every_min``), 0 when it has none."""
    p = views.by_id(product_id)
    return min((j.every_min for j in p.job_list() if j.kind == "timer" and j.every_min), default=0.0) if p else 0.0


def lateness(stamp: str, product_id: str, now: datetime) -> str:
    """Why this stamp is too old for the product's cadence, or "" (fresh, or the product has no cadence). A bare day is aged from the start of today,
    the way the site reads it (lib/fresh.ts), so a report dated today is never late."""
    cad = cadence_minutes(product_id)
    got = parse_stamp(stamp)
    if not cad or got is None:
        return "" if not cad else f"freshness stamp {stamp!r} is unreadable"
    t, bare = got
    ref = now.replace(hour=0, minute=0, second=0, microsecond=0) if bare else now
    age_h = max(0.0, (ref - t).total_seconds() / 3600)
    allowed_h = flags.FRESH_CADENCES * cad / 60
    return f"{product_id} as of {stamp[:16]} is {age_h:.0f} h old; its cadence is {cad / 60:g} h, late after {allowed_h:g} h" if age_h > allowed_h else ""


def envelope_problems(doc: Any) -> list[str]:
    """What is wrong with an agent API body: ``{data, meta:{as_of, source, version, cite_as, license}}`` with non-empty data."""
    if not isinstance(doc, dict):
        return ["body is not a JSON object"]
    if "error" in doc:
        err = doc["error"] if isinstance(doc["error"], dict) else {}
        return [f"error envelope: {err.get('code', '?')}: {str(err.get('message', ''))[:100]}"]
    out = []
    meta = doc.get("meta")
    if not isinstance(meta, dict):
        out.append("no meta block")
    else:
        out += [f"meta.{k} missing" for k in _ENVELOPE_META if k not in meta]
        if meta.get("version") not in (None, "v1"):
            out.append(f"meta.version is {meta.get('version')!r}")
    if doc.get("data") in (None, [], {}, ""):
        out.append("data is empty")
    return out


def _check_page(probe: Probe, reply: Reply, res: Result) -> None:
    html = reply.text()
    if "<html" not in html[:2000].lower() or not re.search(r"<title[^>]*>[^<]+</title>", html, re.IGNORECASE):
        res.flag(FAIL, "not a complete HTML document (no <html> or no <title>)")
    if "__next_error__" in html:
        res.flag(FAIL, "Next rendered its error page")
    hit = _FALLBACK.search(_visible_text(html))
    if hit and probe.path.split("?")[0] not in flags.MAY_BE_EMPTY:
        res.flag(FAIL, f"fallback copy on a page whose data must exist: {hit.group(0)!r}")
    if probe.path in flags.STALE_MARKER_PAGES and "is-stale" in html:
        res.flag(WARN, "the page shows a stale marker (a product is late for its own cadence)")


def _check_api(probe: Probe, reply: Reply, res: Result, now: datetime) -> None:
    try:
        doc = json.loads(reply.body)
    except ValueError:
        res.flag(FAIL, "body is not JSON")
        return
    if probe.kind == "json":
        if not doc:
            res.flag(FAIL, "JSON body is empty")
        return
    for problem in envelope_problems(doc):
        res.flag(FAIL, problem)
    if probe.fresh and isinstance(doc, dict) and isinstance(doc.get("meta"), dict):
        late = lateness(str(doc["meta"].get("as_of") or ""), probe.fresh[0], now)
        if late:
            res.flag(probe.fresh[1], late)


def judge(probe: Probe, reply: Reply, *, now: datetime | None = None) -> Result:
    now = now or datetime.now(UTC)
    res = Result(probe.path, probe.kind, reply.status, reply.ms, why=probe.why)
    if reply.status == 0:
        res.flag(FAIL, f"no answer: {reply.error or 'unknown error'}")
        return res
    if probe.kind == "redirect":
        dest = urlparse(reply.headers.get("location", "")).path
        if reply.status not in (301, 302, 307, 308) or dest != probe.expect:
            res.flag(FAIL, f"expected a redirect to {probe.expect}, got {reply.status}" + (f" to {reply.headers.get('location')}" if reply.headers.get("location") else ""))
    elif reply.status != 200:
        res.flag(FAIL, f"status {reply.status}")
    elif probe.kind == "page":
        _check_page(probe, reply, res)
    elif probe.kind in ("api", "json"):
        _check_api(probe, reply, res, now)
    elif probe.kind == "xml":
        try:
            ET.fromstring(reply.body)
        except ET.ParseError as exc:
            res.flag(FAIL, f"not valid XML: {exc}")
    elif probe.kind == "text" and (len(reply.body) < 20 or (probe.expect and probe.expect not in reply.text())):
        res.flag(FAIL, "empty or missing " + (repr(probe.expect) if probe.expect else "text"))
    if reply.ms > flags.SLOW_MS:
        res.flag(WARN, f"slow: {reply.ms} ms")
    return res
