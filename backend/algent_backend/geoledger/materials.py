"""
The text the extractor reads, in one shape: a ``Material`` is a label plus ``Item``s, each a citable unit (a daily
development, a research claim, a statement, a slice of a library article) with its own source URLs and date.

Items are what keep extraction honest: the model cites item ids, and the harness takes sources and the date from the
items it cited, never from the model. Adapters here only reshape stored texts (no new research, no network).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
ITEM_CHARS = 2400            # a long article is cut into items of about this size on paragraph edges
BATCH_CHARS = 9000           # one extraction call reads about this much; more is split into several calls


@dataclass(frozen=True)
class Item:
    id: str
    text: str
    urls: tuple[str, ...] = ()
    when: str = ""           # YYYY-MM-DD of the item, "" when it carries none


@dataclass(frozen=True)
class Material:
    label: str               # what this is, for the prompt: "Daily report section: Ukraine war"
    via: str                 # provenance stem for events: daily:2026-10-05:thr_x | profile:<id> | statements | library:<url>
    default_date: str        # the day relative dates in the text hang from
    items: tuple[Item, ...]

    @property
    def key(self) -> str:
        """A fingerprint of what was read, so a stored text is never paid for twice."""
        h = hashlib.sha1(self.via.encode("utf-8"))
        for i in self.items:
            h.update(i.text.encode("utf-8"))
        return h.hexdigest()[:20]

    def batches(self, limit: int = BATCH_CHARS) -> list[Material]:
        out: list[list[Item]] = [[]]
        size = 0
        for i in self.items:
            if size + len(i.text) > limit and out[-1]:
                out.append([])
                size = 0
            out[-1].append(i)
            size += len(i.text)
        return [Material(self.label, self.via, self.default_date, tuple(b)) for b in out if b]


def _day(raw: Any) -> str:
    m = _DAY.search(str(raw or ""))
    return m.group(0) if m else ""


def _urls(raw: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(u for u in (raw or []) if isinstance(u, str) and u.startswith(("http://", "https://"))))


def from_section(section: dict, as_of: str) -> Material:
    """A daily report section: every development (headline, detail, what it means, who said what) with its sources."""
    items = []
    for n, d in enumerate(section.get("developments") or [], 1):
        if not isinstance(d, dict):
            continue
        said = " ".join(f"{s.get('who', '')}: {s.get('said', '')}" for s in d.get("statements") or [] if isinstance(s, dict))
        text = " ".join(x for x in (str(d.get("headline", "")).rstrip("."), str(d.get("detail", "")), str(d.get("significance", "")), said) if x.strip())
        urls = _urls(d.get("sources")) + tuple(u for s in d.get("statements") or [] if isinstance(s, dict) for u in _urls([s.get("source")]))
        if text.strip():
            items.append(Item(f"d{n}", text.strip(), tuple(dict.fromkeys(urls)), _day(d.get("when"))))
    tid = section.get("theater_id", "")
    return Material(f"Daily intelligence report, theater: {section.get('name', tid)}", f"daily:{as_of}:{tid}", as_of, tuple(items))


def from_profile(profile: Any) -> Material:
    """A research profile (``SignalProfile`` or its dict): each claim with the URLs of the sources that support it."""
    get = (lambda o, k, d="": o.get(k, d)) if isinstance(profile, dict) else (lambda o, k, d="": getattr(o, k, d))
    urls = {str(get(s, "id")): str(get(s, "url")) for s in get(profile, "source_ledger", []) or []}
    items = []
    for n, c in enumerate(get(profile, "claim_ledger", []) or [], 1):
        text = str(get(c, "text"))
        if text.strip():
            items.append(Item(f"c{n}", text.strip(), _urls([urls.get(s, "") for s in get(c, "supported_by", []) or []]), _day(get(profile, "as_of"))))
    pid = str(get(profile, "id"))
    return Material(f"Research profile: {get(profile, 'title')}", f"profile:{pid}", _day(get(profile, "as_of")), tuple(items))


def from_statements(statements: list[Any]) -> Material:
    """Statements of the ledger (who said what), each with its source URL and date."""
    items = []
    for n, s in enumerate(statements, 1):
        text = f"{s.speaker} ({s.affiliation or s.role}): {s.quote or s.paraphrase}"
        items.append(Item(f"s{n}", text, _urls([s.source_url]), _day(s.date)))
    return Material("Statements on the record", "statements", _day(statements[0].date) if statements else "", tuple(items))


def from_document(url: str, title: str, text: str, published: str, fetched_at: str = "") -> Material:
    """A library article cut into items on paragraph edges; every item carries the article's URL."""
    items, buf, n = [], "", 0
    for para in re.split(r"\n\s*\n|\n", text):
        if not para.strip():
            continue
        if buf and len(buf) + len(para) > ITEM_CHARS:
            n += 1
            items.append(Item(f"a{n}", buf.strip(), _urls([url]), _day(published)))
            buf = ""
        buf += para.strip() + "\n"
    if buf.strip():
        items.append(Item(f"a{n + 1}", buf.strip(), _urls([url]), _day(published)))
    return Material(f"Article: {title}", f"library:{url}", _day(published) or _day(fetched_at), tuple(items))
