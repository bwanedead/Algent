"""
Recover a profile from a published article's receipts.

Sixteen stories lost their profiles to id collisions in the store (see ``store.py``), and their
run folders had already been pruned. What survives is the article itself — and its "How we
know this" appendix is exactly the verified core of the profile: every source it cited (URL,
publisher, type, capture date, how deeply it was read) and every claim it made (text, status,
as-of). This rebuilds a profile from that.

It is honest about what it is. Threads, entities, uncited claims and excerpts are gone, and the
link from each claim to the particular source behind it was never printed, so recovered claims
carry no ``supported_by``. The profile says so in its summary and is stamped
``recovered_from_published_article`` so nothing downstream mistakes it for a full research pass.
Ids use the same content hashes as live research, so a recovered source joins the corpus as the
same node a live profile would create for that URL.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .assembly import _claim_id, _hash, _norm_url
from .profile import SignalProfile

GENERATOR = "recovered_from_published_article@v1"

_SOURCE = re.compile(
    r"^- \((primary|secondary|tertiary)\) (?P<rest>.+?) — (?P<url>https?://\S+)"
    r"(?:\s+·\s+[*_](?P<depth>[^·*_]+?)(?:\s*·\s*captured (?P<cap>\d{4}-\d{2}-\d{2}))?[*_])?\s*$"
)
_CLAIM = re.compile(
    r"^- _\[(?P<status>[a-z]+)\]_ (?P<text>.+?)(?:\s+·\s+(?P<depth>[^()]+?)(?:\s*\(as of (?P<asof>[\d-]+)\))?)?\s*$"
)
_STATUSES = {"confirmed", "likely", "unconfirmed", "contested", "speculative", "opinion"}


def parse_article(markdown: str) -> dict[str, Any]:
    """Frontmatter title/date, and the sources and claims from the receipts."""
    front: dict[str, str] = {}
    body = markdown
    if markdown.startswith("---"):
        _, fm, body = markdown.split("---", 2)
        for line in fm.splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                front[k.strip()] = v.strip().strip("'\"")
    receipts = body.split("## How we know this", 1)[1] if "## How we know this" in body else ""
    sources, claims = [], []
    for line in receipts.splitlines():
        line = line.strip()
        m = _SOURCE.match(line)
        if m:
            parts = [p.strip() for p in m.group("rest").split(" — ")]
            sources.append({
                "type": m.group(1), "title": parts[0], "publisher": parts[1] if len(parts) > 1 else "",
                "url": m.group("url"), "depth": (m.group("depth") or "").strip(),
                "captured": m.group("cap") or "",
            })
            continue
        m = _CLAIM.match(line)
        if m and m.group("status") in _STATUSES:
            claims.append({"status": m.group("status"), "text": m.group("text").strip(),
                           "depth": (m.group("depth") or "").strip(), "as_of": m.group("asof") or ""})
    return {"title": front.get("title", ""), "date": front.get("date", ""),
            "as_of": front.get("as_of", ""), "sources": sources, "claims": claims}


def rebuild(markdown: str, *, slug: str) -> SignalProfile | None:
    """A profile built from what the article kept. None when it kept nothing."""
    got = parse_article(markdown)
    if not got["sources"] and not got["claims"]:
        return None
    ledger = []
    for s in got["sources"]:
        read = "read in full" in s["depth"]
        ledger.append({
            "id": _hash(_norm_url(s["url"]) or s["title"].lower(), "src_"),
            "url": s["url"], "title": s["title"], "publisher": s["publisher"],
            "source_type": s["type"], "retrieved_at": s["captured"],
            "snapshot": {"captured_at": s["captured"]} if read and s["captured"] else None,
        })
    claims = []
    for c in got["claims"]:
        stub = type("C", (), {"text": c["text"]})()
        claims.append({
            "id": _claim_id(stub), "text": c["text"], "status": c["status"],
            "grounding": "snapshotted" if "read in full" in c["depth"] else "snippet_only",
            "note": f"recovered; as of {c['as_of']}" if c["as_of"] else "recovered",
        })
    return SignalProfile.model_validate({
        "id": _hash(slug, "prof_recovered_"),
        "title": got["title"],
        "summary": (
            "RECOVERED from the published article's receipts after the original profile was lost "
            "to an id collision in the store. Holds only what the article cited — its sources and "
            "claims. Threads, entities, uncited claims and excerpts were not recoverable, and "
            "claims are not linked to the specific source behind each."
        ),
        "as_of": got["as_of"] or got["date"],
        "source_ledger": ledger,
        "claim_ledger": claims,
        "generated_at": got["date"],
        "generator": GENERATOR,
    })


def recover_all(articles_dir: Path, lost_titles: list[str], store: Any) -> list[dict[str, Any]]:
    """Rebuild each lost story found among the published articles. Returns what was recovered."""
    want = {_key(t): t for t in lost_titles}
    out = []
    for path in sorted(articles_dir.glob("*.md")):
        md = path.read_text(encoding="utf-8")
        title = parse_article(md)["title"]
        if _key(title) not in want:
            continue
        prof = rebuild(md, slug=path.stem)
        if prof is None:
            continue
        store.save(prof)
        out.append({"id": prof.id, "title": prof.title, "sources": len(prof.source_ledger),
                    "claims": len(prof.claim_ledger)})
    return out


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())[:60]
