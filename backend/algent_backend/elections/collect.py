"""
The daily pass: pick the elections worth reading, fetch their pages, snapshot what they say.

Targets: elections in the electoral calendar held within ``flags.LOOKBACK_DAYS`` or due within ``LOOKAHEAD_DAYS`` (the calendar page's own links name each
election's article), then any election named by an ask (``asks``: poll / result asks of the bots, passed in by the CLI), resolved from the calendar targets
first and else by a Wikipedia search (at most ``MAX_ASK_SEARCHES`` a run). For each: the election's page and its "Opinion polling for the ..." page via
``action=raw``; a page that does not exist is an answer ("no polls page"), not an error. Fetching is injected (``Fetch``) so tests never touch the network.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote, urlencode

from algent_backend import polite_http
from algent_backend.lookahead.sources import elections as calendar_page

from . import country, flags, polls, results, store
from .contracts import Snapshot, slug_of

Fetch = Callable[[str], str]                              # URL -> body, "" when the page does not exist
_GENERIC = frozenset("poll polls polling result results final runoff vote votes count election elections seat seats projection projections generic ballot official "
                     "preliminary certified tally turnout latest current president presidential parliamentary general".split())
_REDIRECT = re.compile(r"^\s*#redirect\s*\[\[([^\]|#]+)", re.I)


@dataclass(frozen=True)
class Target:
    title: str                                            # the election's article
    country: str = ""
    date: str = ""
    via: str = "calendar"
    asked: str = ""


def default_fetch(url: str) -> str:
    return polite_http.get(url, missing_ok=True)


def page_url(title: str) -> str:
    return flags.WIKI.format(title=quote(title.replace(" ", "_"), safe="_(),:'"))


def read_page(fetch: Fetch, title: str) -> str:
    """Raw wikitext of an article; one redirect hop is followed (``action=raw`` returns the redirect line itself)."""
    for _ in range(2):
        text = fetch(flags.RAW.format(title=quote(title.replace(" ", "_"), safe="_(),:'")))
        m = _REDIRECT.match(text or "")
        if not m:
            return text or ""
        title = m.group(1).strip()
    return ""


def calendar_targets(today: date, fetch: Fetch = default_fetch) -> list[Target]:
    """Calendar elections inside the window, nearest first. A year whose calendar page is missing contributes nothing."""
    lo, hi = today - timedelta(days=flags.LOOKBACK_DAYS), today + timedelta(days=flags.LOOKAHEAD_DAYS)
    out: dict[str, Target] = {}
    for year in sorted({lo.year, hi.year}):
        text = fetch(calendar_page.RAW.format(year=year))
        for item, page in calendar_page.parse_with_pages(text or "", year):
            last = date.fromisoformat(item.end_date or item.date)
            if page and lo <= last <= hi:
                out.setdefault(slug_of(page), Target(page, item.countries[0] if item.countries else "", item.date))
    return sorted(out.values(), key=lambda t: abs((date.fromisoformat(t.date) - today).days))[:flags.MAX_ELECTIONS]


def _words(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", text.casefold()) if w not in _GENERIC}


def current(title: str, today: date) -> bool:
    """A title leading with a year older than ``flags.YEARS_BACK`` before today's is a past election: never collected, never indexed."""
    m = re.match(r"\d{4}", title)
    return not m or int(m.group(0)) >= today.year - flags.YEARS_BACK


def ask_targets(asks: Iterable[str], known: list[Target], fetch: Fetch = default_fetch, today: date | None = None) -> list[Target]:
    """Elections named by asks that no calendar target already covers: one Wikipedia search each (bounded). An ask that finds nothing adds nothing."""
    have = [(t, _words(t.title)) for t in known]
    out: dict[str, Target] = {}
    searches = 0
    for ask in asks:
        w = _words(ask)
        if not w or any(w & tw for _, tw in have):
            continue
        if searches >= flags.MAX_ASK_SEARCHES:
            break
        searches += 1
        q = " ".join(re.findall(r"[A-Za-z]{4,}", ask))
        try:
            body = fetch(f"{flags.SEARCH}?" + urlencode({"action": "query", "list": "search", "srsearch": f"{q} election opinion polling", "srlimit": 5, "format": "json"}))
            titles = [r.get("title", "") for r in (json.loads(body or "{}").get("query", {}).get("search") or [])]
        except (polite_http.SourceError, ValueError):
            continue
        prefix = flags.POLL_PAGE.format(election="")
        title = next((t[len(prefix):] for t in titles if t.startswith(prefix)), "") or next((t for t in titles if re.match(r"\d{4} .*election", t)), "")
        if title and current(title, today or date.today()) and slug_of(title) not in out and not any(slug_of(title) == slug_of(t.title) for t in known):
            out[slug_of(title)] = Target(title, via="ask", asked=ask)
    return list(out.values())


def snapshot(target: Target, fetch: Fetch = default_fetch, now: str | None = None) -> Snapshot | None:
    """What the election's pages say right now; None when neither page exists or holds anything we can read."""
    year = int(m.group(0)) if (m := re.match(r"\d{4}", target.title)) else None
    poll_title = flags.POLL_PAGE.format(election=target.title)
    poll_text, page_text = read_page(fetch, poll_title), read_page(fetch, target.title)
    pages = {}
    tables = polls.extract(poll_text, year) if poll_text else []
    if poll_text:
        pages["polling"] = page_url(poll_title)
    if not tables and page_text:                          # no separate polling page: the election's own "Opinion polling" section
        tables = polls.extract(page_text, year)
    if page_text:
        pages["election"] = page_url(target.title)
    res = results.extract(page_text) if page_text else None
    if not tables and res is None:
        return None
    return Snapshot(election=target.title, slug=slug_of(target.title), country=target.country or country.of(target.title), date=target.date, via=target.via, acquired_at=now or store.now_iso(),
                    polls=tables, results=res, pages=pages)


def run(*, today: date | None = None, asks: Iterable[str] = (), fetch: Fetch = default_fetch, now: datetime | None = None) -> dict:
    """One pass. Never raises for a bad page or a failed fetch: each election reports its own outcome."""
    now = now or datetime.now(UTC)
    today = today or now.date()
    report: dict = {"as_of": now.isoformat(timespec="seconds"), "elections": [], "appended": 0, "errors": []}
    try:
        targets = calendar_targets(today, fetch)
    except (polite_http.SourceError, ValueError) as exc:
        targets = []
        report["errors"].append(f"calendar: {str(exc)[:160]}")
    targets += ask_targets(asks, targets, fetch, today)
    for t in targets:
        try:
            snap = snapshot(t, fetch, now.isoformat(timespec="seconds"))
        except (polite_http.SourceError, ValueError) as exc:
            report["errors"].append(f"{t.title}: {str(exc)[:160]}")
            continue
        added = bool(snap) and store.append(snap)
        report["appended"] += added
        report["elections"].append({"election": t.title, "via": t.via, "polls": sum(x.n_total for x in snap.polls) if snap else 0,
                                    "results": len(snap.results.rows) if snap and snap.results else 0, "appended": added})
    ok = bool(report["elections"]) or not report["errors"]
    store.save_status(**({"last_ok": report["as_of"]} if ok else {}), last_run=report["as_of"], elections=len(report["elections"]), appended=report["appended"],
                      last_error="; ".join(report["errors"][:3]))
    return report
