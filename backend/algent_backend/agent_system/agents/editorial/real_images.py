"""
Real photographs before drawn ones — freely licensed pictures from Wikimedia Commons.

The operator's standing preference: a real photo of the real thing beats an illustration, and an
illustration beats nothing. Until now the newsroom could only draw, so every picture on the site
wore the AI frame — including the Strait of Hormuz, which NASA astronauts have photographed and
released into the public domain.

Three steps, each honest about what it can and cannot know:
1. **Search** Commons with the planner's proper-noun query ("Strait of Hormuz"). Only bitmap
   files, only licenses that allow reuse with credit (no NC / ND), only files big enough to use.
2. **Choose.** Search results are noisy — a query for the strait returns a photo from orbit, two
   maps, a topographic render and a screenshot of a social-media post. A cheap model call picks
   the one PHOTOGRAPH that shows the thing the passage describes, or none. None is common and fine:
   the slot falls back to the illustration, which is then labelled as one.
3. **Credit.** Every photo ships with its author, licence, date and a link back to its Commons
   page, on a caption line under the image. That is the licence's condition and our brand's too:
   a reader can see where the picture came from and when it was taken.

Never raises. No network, no candidates, no pick — all mean "no photo", never a failed article.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

_API = "https://commons.wikimedia.org/w/api.php"
#: Wikimedia's user-agent policy requires a contact URL; requests without one get a 403.
_UA = "OhmegaMonsterNewsroom/0.1 (https://www.ohmega.monster/) httpx"
_TIMEOUT_S = 20.0
_WIDTH = 1280            # the size we fetch — body width at 2x is well under this
_MIN_WIDTH = 800         # smaller than this looks broken at body width
_MIMES = {"image/jpeg", "image/png", "image/webp"}
PHOTO_PREFIX = "photo_"  # the site decides "real or generated" by file name; this is "real"


@dataclass(frozen=True)
class Candidate:
    title: str
    description: str
    license: str
    license_url: str
    artist: str
    date: str
    thumb_url: str
    page_url: str
    width: int
    mime: str


def _plain(value: str) -> str:
    """Commons metadata is HTML; a caption wants the text."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(text).split())


def reusable(license_name: str) -> bool:
    """Free to publish with credit. Commons hosts only free files, but NC/ND variants and blank
    licence fields still turn up in metadata, and those we cannot use."""
    name = (license_name or "").strip().upper()
    if not name:
        return False
    return not re.search(r"\bNC\b|\bND\b|NON-?COMMERCIAL|NO ?DERIV", name)


def search_commons(query: str, *, limit: int = 8, http: Any = None) -> list[Candidate]:
    """Usable photo candidates for ``query``. Empty on any failure."""
    if not (query or "").strip():
        return []
    if http is None:
        import httpx as http
    try:
        r = http.get(_API, params={
            "action": "query", "format": "json", "formatversion": 2,
            "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6, "gsrlimit": limit,
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": _WIDTH,
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ImageDescription|DateTimeOriginal",
        }, headers={"User-Agent": _UA}, timeout=_TIMEOUT_S)
        pages = (r.json().get("query") or {}).get("pages") or []
    except Exception:  # noqa: BLE001 — no network is no photo
        return []
    out: list[Candidate] = []
    for page in sorted(pages, key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        val = lambda k: str((meta.get(k) or {}).get("value") or "")  # noqa: E731
        lic = _plain(val("LicenseShortName"))
        if not reusable(lic) or info.get("mime") not in _MIMES:
            continue
        if int(info.get("width") or 0) < _MIN_WIDTH or not info.get("thumburl"):
            continue
        out.append(Candidate(
            title=str(page.get("title") or "").removeprefix("File:"),
            description=_plain(val("ImageDescription"))[:300],
            license=lic, license_url=_plain(val("LicenseUrl")),
            artist=_plain(val("Artist"))[:120] or "unknown",
            date=_plain(val("DateTimeOriginal"))[:40],
            thumb_url=str(info["thumburl"]), page_url=str(info.get("descriptionurl") or ""),
            width=int(info.get("width") or 0), mime=str(info.get("mime") or ""),
        ))
    return out


class PhotoChoice(BaseModel):
    index: int = -1        # which candidate, or -1 for none
    why: str = ""          # one line, for the run record


CHOOSE_ROLE = """\
You pick a real photograph for a news article, from a list of freely licensed files found by a
search. You see each file's title, description and date — not the image itself — so judge from
those, and when they do not make it clear, pick nothing.

Pick a candidate ONLY if it is a PHOTOGRAPH of the specific real thing or place the passage
describes. Reject:
- maps, diagrams, charts, infographics, renders, logos, flags, documents and screenshots of posts;
- a different place or thing that merely shares a word with it;
- a portrait of an identifiable private person;
- anything whose description suggests it is staged, edited or an illustration.
An older photograph is fine when the thing has not changed in a way the passage is about; the
caption will carry its date.

Return the candidate's index, or -1 for none. None is a common, correct answer — the article then
uses an illustration labelled as one, which is better than a photo of the wrong thing.
"""


def choose(context: Any, config: Any, *, subject: str, passage: str, candidates: list[Candidate],
           model_spec: Any) -> tuple[Candidate | None, str]:
    """The candidate that shows the thing, or (None, why). Never raises."""
    if not candidates:
        return None, "no usable candidates"
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    listing = "\n".join(
        f"[{i}] {c.title} — {c.description or '(no description)'} — taken: {c.date or 'unknown'}"
        for i, c in enumerate(candidates))
    task = (f"THE PASSAGE WANTS A PHOTO OF: {subject}\n\nPASSAGE: {passage[:900]}\n\n"
            f"CANDIDATES:\n{listing}\n\nTASK: return the index of the photograph that shows it, or -1.")
    try:
        model = context.model_resolver.resolve(model_spec).client.with_structured_output(PhotoChoice)
        out = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, CHOOSE_ROLE)),
                            HumanMessage(content=task)], config=config)
    except Exception as exc:  # noqa: BLE001
        return None, f"chooser failed: {type(exc).__name__}"
    if not isinstance(out, PhotoChoice) or not 0 <= out.index < len(candidates):
        return None, (getattr(out, "why", "") or "none fit")[:160]
    return candidates[out.index], out.why[:160]


def fetch(candidate: Candidate, *, http: Any = None) -> bytes:
    """The picture's bytes at body size. Empty on failure."""
    if http is None:
        import httpx as http
    try:
        r = http.get(candidate.thumb_url, headers={"User-Agent": _UA}, timeout=_TIMEOUT_S,
                     follow_redirects=True)
        return r.content if r.status_code == 200 and r.content else b""
    except Exception:  # noqa: BLE001
        return b""


def find_photo(context: Any, config: Any, *, query: str, subject: str, passage: str,
               model_spec: Any, http: Any = None) -> tuple[Candidate | None, bytes, str]:
    """Search → choose → fetch. Returns (candidate, bytes, note); candidate None means draw."""
    candidates = search_commons(query or subject, http=http)
    pick, why = choose(context, config, subject=subject, passage=passage,
                       candidates=candidates, model_spec=model_spec)
    if pick is None:
        return None, b"", why
    data = fetch(pick, http=http)
    if not data:
        return None, b"", "download failed"
    return pick, data, why


def suffix(candidate: Candidate) -> str:
    return {"image/png": ".png", "image/webp": ".webp"}.get(candidate.mime, ".jpg")


def _year(candidate: Candidate) -> str:
    found = re.search(r"\b(1[89]\d\d|20\d\d)\b", candidate.date or "")
    return found.group(1) if found else ""


def credit_line(candidate: Candidate) -> str:
    """The caption under an in-body photo: who, which licence, when, and where it lives.

    A wholly italic line on its own — the site renders that as a figure caption."""
    lic = (f"[{candidate.license}]({candidate.license_url})" if candidate.license_url
           else candidate.license)
    parts = [f"Photo: {_md(candidate.artist)}", f"[Wikimedia Commons]({candidate.page_url})", lic]
    return "*" + " · ".join([*parts, _year(candidate)] if _year(candidate) else parts) + "*"


def credit_text(candidate: Candidate) -> str:
    """The same credit as plain text, for a caption the site links to the source itself."""
    parts = [f"Photo: {_md(candidate.artist)}", candidate.license, _year(candidate)]
    return " · ".join(p for p in parts if p)


def _md(text: str) -> str:
    """Keep a credit from breaking the markdown it sits in."""
    return re.sub(r"[*_\[\]()`]", "", text).strip() or "unknown"
