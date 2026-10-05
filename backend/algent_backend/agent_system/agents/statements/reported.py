"""
The reported lane: what leaders said, as printed by news outlets — for the voices whose own sites we
cannot read (Ukraine, Poland, Lithuania, Israel, the Gulf, ...). Secondary, so it is marked: statements
from here carry ``source_kind="secondary"`` and ``reported_by`` (the outlet), their ``source_url`` is the
article, and quotes are validated against the ARTICLE text. A primary on file for the same remark wins
(``dedupe``).

    targets -> search (library first, then free news search) -> filter -> read (library text, else the
    free reader) -> Transcript(feed="reported", outlet=...) -> the ordinary extractor (``extract``)

Targets are PEOPLE and OFFICES, in tiers: (0) the heads of state/government (from the actors store) and
the foreign/defence ministers on the ledger, of the countries named by the live theaters; (1) standing
high-signal offices (NATO, EU, UN); (2) the standing list of other states' leaders. Free throughout:
the library is local, gnews and the page reader are keyless; no model call happens here.

Budget (each WHY in the constants): the lane is bounded by targets per run, articles per target and
articles per run, a search cooldown, and the URL cache (``seen.json``: a URL read once is never read or
extracted again, and a URL that keeps failing is parked after ``MAX_ATTEMPTS``).

The network seams (``lib_search``, ``lib_text``, ``news_search``, ``read_page``, ``sleep``) are injectable
so tests run offline.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from . import store
from .collect import MAX_ATTEMPTS, _transcript_id, default_read_page
from .contracts import Transcript
from .sources import SOURCES

#: Whether ``newsroom statements collect`` runs this lane without being asked. Off: it is the one lane that
#: reads third-party articles and spends extraction calls on them; the intel refresh opts in explicitly.
RUN_BY_DEFAULT = False
#: How far back a report may be. The primary lane polls feeds fortnightly; this lane is about what was
#: SAID lately, and news search is only fresh and precise at this scale.
WINDOW_DAYS = 3
#: Searches per run. A search is cheap but not free (gnews resolves links with extra requests); 24 covers
#: the theaters' actors and the standing offices over a couple of runs thanks to the cooldown rotation.
MAX_TARGETS = 24
#: Share of a run's targets reserved for the urgent tiers (see ``_due``); the remainder rotates.
TOP_SHARE = 0.4
#: A person in the news has dozens of articles; the extractor wants the best one or two, not a pile.
MAX_PER_TARGET = 2
#: Hard ceiling on reads per run (each read is a polite page fetch and later one model call).
MAX_ARTICLES = 20
#: Re-searching the same person every refresh finds the same articles; rotate instead.
COOLDOWN_HOURS = 12
#: Below this an "article" is a paywall stub or a cookie wall, not a report of what someone said.
MIN_WORDS = 120
PACE_S = 1.5

#: The offices that matter whoever holds them (names go stale, offices do not). ``must``: any of these
#: (casefolded) must appear in a headline or snippet for the article to be read.
STANDING_OFFICES: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    ("office:nato", "NATO Secretary General", 'NATO "Secretary General"', ("nato",), "NATO"),
    ("office:eu-commission", "President of the European Commission", '"European Commission" president',
     ("commission",), "European Union"),
    ("office:eu-council", "President of the European Council", '"European Council" president',
     ("european council", "council president"), "European Union"),
    ("office:eu-foreign", "EU foreign policy chief", '"EU foreign policy chief"',
     ("eu foreign policy", "high representative"), "European Union"),
    ("office:un-sg", "UN Secretary-General", '"UN Secretary-General"', ("secretary-general", "secretary general"),
     "United Nations"),
)
#: States whose leaders the desk should hear whether or not a theater names them (the operator's list:
#: the voices that were missing from the ledger).
STANDING_STATES: tuple[str, ...] = ("UA", "PL", "LT", "LV", "EE", "FI", "FR", "DE", "TR", "JP", "IN", "IR", "IL",
                                    "SA", "QA", "AE", "KR", "AU", "CA", "BR")
_MINISTER_ROLE = re.compile(r"foreign|defen[cs]e|secretary of state|secretary of war", re.I)


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    query: str                       # search words (the library ANDs them; news search gets "<query> said")
    must: tuple[str, ...]            # any of these in a headline/snippet, casefolded
    tier: int
    affiliation: str = ""


@dataclass
class Candidate:
    url: str
    title: str
    outlet: str
    published: str = ""
    snippet: str = ""
    origin: str = "news"             # "library" | "news"


# ── who to listen for ─────────────────────────────────────────────────────────────────────────
def _person(name: str, label_extra: str, tier: int, affiliation: str) -> Target | None:
    parts = re.findall(r"\w+", name)
    if not parts or len(parts[-1]) < 3:
        return None
    return Target(key=f"person:{name.casefold()}", label=f"{name}{label_extra}", query=f'"{name}"',
                  must=(parts[-1].casefold(),), tier=tier, affiliation=affiliation)


def default_leaders() -> dict[str, list[str]]:
    """iso2 -> [head of government, head of state] names from the actors store (empty when absent)."""
    try:
        from algent_backend.actors import store as actors_store

        rows = actors_store.latest_leaders()
    except Exception:  # noqa: BLE001 - no actors store: office-title targets still work
        return {}
    return {iso: [o.name for o in (r.head_of_government, r.head_of_state) if o and o.name] for iso, r in rows.items()}


def _countries_in(text: str, resolve: Callable[[str], str | None]) -> list[str]:
    """ISO2 codes for country names appearing in ``text`` (windows of 1-3 words; the registry resolves exactly).
    The registry also knows ISO codes ("AS", "AND", "IN"), which are ordinary words in prose, so a word
    counts only when capitalised, and a short one only when written in capitals ("US", "UK")."""
    words = re.findall(r"[\w'.]+", text)
    proper = [bool(w[:1].isupper()) and (len(w) > 3 or w.isupper()) for w in words]
    out: list[str] = []
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            if not all(proper[i:i + n]):
                continue
            iso = resolve(" ".join(words[i:i + n]))
            if iso and iso not in out:
                out.append(iso)
    return out


def plan_targets(*, theaters: Sequence[str] = (), leaders: dict[str, list[str]] | None = None,
                 ledger: Sequence[Any] = (), resolve: Callable[[str], str | None] | None = None,
                 country_name: Callable[[str], str] | None = None) -> list[Target]:
    """Every target, tiered, de-duplicated. ``theaters`` are the live theaters' names/descriptions;
    ``ledger`` the statements on file (their foreign/defence ministers are named in the corpus)."""
    if resolve is None or country_name is None:
        from algent_backend.actors import registry

        resolve = resolve or registry.resolve
        country_name = country_name or (lambda iso: registry.display_name(iso, iso))
    leaders = default_leaders() if leaders is None else leaders
    live = [iso for text in theaters for iso in _countries_in(text, resolve)]
    live_names = {country_name(i).casefold() for i in live}

    out: dict[str, Target] = {}

    def add(t: Target | None) -> None:
        if t and t.key not in out:
            out[t.key] = t

    def state_targets(iso: str, tier: int) -> None:
        names = leaders.get(iso, [])
        for name in names:
            add(_person(name, f" ({country_name(iso)})", tier, country_name(iso)))
        if not names:                                         # no leader data: the offices by country
            c = country_name(iso)
            add(Target(f"state:{iso}", f"{c} leaders", f'{c} president OR "prime minister"', (c.casefold(),), tier, c))

    heard = {s.affiliation.casefold() for s in SOURCES}      # states whose own site the primary lane already reads
    for iso in dict.fromkeys(live):                           # the silent theater actors first, the heard ones last
        state_targets(iso, 3 if country_name(iso).casefold() in heard else 0)
    for s in ledger:                                          # ministers the corpus already names
        if (s.affiliation or "").casefold() in live_names and _MINISTER_ROLE.search(s.role or ""):
            add(_person(s.speaker, f" ({s.role})", 3 if s.affiliation.casefold() in heard else 0, s.affiliation))
    for key, label, query, must, aff in STANDING_OFFICES:
        add(Target(key, label, query, must, 1, aff))
    for iso in STANDING_STATES:
        state_targets(iso, 2)
    return sorted(out.values(), key=lambda t: t.tier)         # stable: tier order, discovery order within


def _due(targets: list[Target], searched: dict[str, str], now: datetime, limit: int) -> list[Target]:
    """Targets not searched within the cooldown. The first ``TOP_SHARE`` of the cap goes to the urgent tiers
    (the silent theater actors, the standing offices); the rest to whoever has waited longest, so the
    standing list of states rotates through instead of starving behind the urgent ones every run."""
    floor = (now - timedelta(hours=COOLDOWN_HOURS)).isoformat()
    ready = [t for t in targets if searched.get(t.key, "") < floor]
    top = sorted((t for t in ready if t.tier <= 1), key=lambda t: (t.tier, searched.get(t.key, "")))[:max(1, int(limit * TOP_SHARE))]
    rest = sorted((t for t in ready if t not in top), key=lambda t: (searched.get(t.key, ""), t.tier))
    return (top + rest)[:limit]


# ── finding articles ──────────────────────────────────────────────────────────────────────────
def default_lib_search(query: str, days: int) -> list[dict[str, Any]]:
    from algent_backend.library import search as lib

    return lib.search(query, days=days, limit=8)


def default_news_search(query: str) -> list[dict[str, Any]]:
    from algent_backend.agent_system.tools.sourcing.search import gnews

    return gnews.search(f"{query} when:{WINDOW_DAYS}d", max_results=8)


def default_lib_text(url: str) -> str:
    """The library's stored text for ``url`` ('' if it has none): a page we already read costs nothing."""
    from algent_backend.library import store as lib_store

    conn = lib_store.connect(create=False)
    if conn is None:
        return ""
    try:
        row = conn.execute("SELECT text FROM documents WHERE url=? AND latest=1", (url,)).fetchone()
    finally:
        conn.close()
    return row["text"] if row else ""


def _recent(published: str, today: date) -> bool:
    try:
        return date.fromisoformat(published[:10]) >= today - timedelta(days=WINDOW_DAYS)
    except ValueError:
        return True                                           # undated: the search window already bounded it


def _outlet_name(source_id: str) -> str:
    from algent_backend.library.sources import by_id

    src = by_id(source_id)
    return src.name if src else source_id


def candidates(target: Target, *, lib_search: Callable[[str, int], list[dict[str, Any]]],
               news_search: Callable[[str], list[dict[str, Any]]], today: date, skip: Callable[[str], bool],
               errors: list[str]) -> list[Candidate]:
    """Up to ``MAX_PER_TARGET`` readable, recent, unseen articles that mention the target: the library's
    first (our trusted outlets, already on disk), then free news search. Primary-kind library documents
    are the speakers' own texts, handled by the primary lane, so they are not 'reports'."""
    from algent_backend.library.sources import PRIMARY_KINDS

    out: list[Candidate] = []
    seen: set[str] = set()

    def consider(c: Candidate) -> None:
        blob = f"{c.title} {c.snippet}".casefold()
        if (c.url and c.url not in seen and not skip(c.url) and _recent(c.published, today)
                and any(m in blob for m in target.must)):
            seen.add(c.url)
            out.append(c)

    try:
        for h in lib_search(target.query, WINDOW_DAYS):
            if h.get("kind") not in PRIMARY_KINDS:
                consider(Candidate(h["url"], h.get("title", ""), _outlet_name(h.get("source", "")),
                                   h.get("published", ""), h.get("snippet", ""), "library"))
    except Exception as exc:  # noqa: BLE001 - one lane failing must not stop the other
        errors.append(f"library {target.label}: {str(exc)[:100]}")
    if len(out) < MAX_PER_TARGET:
        try:
            for h in news_search(f"{target.query} said"):
                if h.get("resolved"):                         # an unresolved Google link cannot be read
                    consider(Candidate(h["url"], h.get("title", ""), h.get("outlet", ""), h.get("published", ""),
                                       "", "news"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"news {target.label}: {str(exc)[:100]}")
    return out[:MAX_PER_TARGET]


# ── the run ───────────────────────────────────────────────────────────────────────────────────
def collect_reported(*, theaters: Sequence[str] = (), root: Any = None, now: datetime | None = None,
                     leaders: dict[str, list[str]] | None = None, targets: list[Target] | None = None,
                     max_targets: int = MAX_TARGETS, max_articles: int = MAX_ARTICLES,
                     lib_search: Callable[[str, int], list[dict[str, Any]]] = default_lib_search,
                     news_search: Callable[[str], list[dict[str, Any]]] = default_news_search,
                     lib_text: Callable[[str], str] = default_lib_text,
                     read_page: Callable[[str], str] = default_read_page,
                     sleep: Callable[[float], None] = time.sleep,
                     resolve: Callable[[str], str | None] | None = None,
                     country_name: Callable[[str], str] | None = None) -> dict:
    """Search for reports of what the targets said, read the new ones, store them as transcripts for
    ``extract.extract_pending``. Free; no model. Returns a report with every target's finds."""
    now = now or datetime.now(UTC)
    today = now.date()
    seen = store.load_seen(root)
    if targets is None:
        targets = plan_targets(theaters=theaters, leaders=leaders, ledger=store.load_statements(root),
                               resolve=resolve, country_name=country_name)
    due = _due(targets, seen["reported"], now, max_targets)
    report: dict[str, Any] = {"targets_planned": len(targets), "targets_searched": 0, "articles_read": 0,
                              "collected": 0, "failed": 0, "errors": [], "by_target": []}

    def parked(url: str) -> bool:
        return url in seen["collected"] or seen["failed"].get(url, 0) >= MAX_ATTEMPTS

    taken: set[str] = set()                                   # one article often serves several targets
    for t in due:
        if report["articles_read"] >= max_articles:           # budget spent: the rest wait, un-stamped, for next run
            break
        row: dict[str, Any] = {"target": t.label, "tier": t.tier, "articles": []}
        report["by_target"].append(row)
        report["targets_searched"] += 1
        seen["reported"][t.key] = now.isoformat()
        for c in candidates(t, lib_search=lib_search, news_search=news_search, today=today,
                            skip=lambda u: parked(u) or u in taken, errors=report["errors"]):
            if report["articles_read"] >= max_articles:
                seen["reported"].pop(t.key, None)             # not fully served: first in line next time
                row["articles"].append({"url": c.url, "title": c.title, "outlet": c.outlet, "status": "over-budget"})
                continue
            taken.add(c.url)
            entry = {"url": c.url, "title": c.title, "outlet": c.outlet, "published": c.published, "status": ""}
            row["articles"].append(entry)
            try:
                text = lib_text(c.url) if c.origin == "library" else ""
                if len(text.split()) < MIN_WORDS:             # the library holds only a stub (or it came from news)
                    text = read_page(c.url)
                    sleep(PACE_S)
                report["articles_read"] += 1
                if len(text.split()) < MIN_WORDS:
                    raise RuntimeError(f"only {len(text.split())} words")
            except Exception as exc:  # noqa: BLE001 - one unreadable article must not stop the run
                seen["failed"][c.url] = seen["failed"].get(c.url, 0) + 1
                report["failed"] += 1
                entry["status"] = f"failed: {str(exc)[:80]}"
                continue
            tid = _transcript_id(c.url)
            store.save_transcript(Transcript(id=tid, feed="reported", url=c.url, title=c.title, published=c.published[:10],
                                             text=text, fetched_at=now.isoformat(), outlet=c.outlet or "a news outlet"), root)
            seen["collected"][c.url] = tid
            seen["failed"].pop(c.url, None)
            report["collected"] += 1
            entry["status"] = "collected"
    store.save_seen(seen, root)
    return report
