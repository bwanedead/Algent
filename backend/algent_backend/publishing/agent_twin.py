"""
The machine-readable twin of an article — what an AI agent should read instead of our prose.

Agents want the ledger, not the article: what is claimed, how sure we are of each claim, what it
rests on, and as of when. Every published article gets a JSON twin at
``/data/articles/<slug>.json`` and an entry in ``/data/index.json``; ``/llms.txt`` tells agents
they exist and how to cite them. Static files: nothing to run, every crawler can use them.

What goes in, and what never does:
- IN: the graded claims (text, grade, salience), and for each its sources — link, title,
  publisher, date — only for sources flagged ``safe_to_cite``; reader-facing correction notes.
- NEVER: snapshotted source text (it is the publishers', not ours to republish), internal
  research notes, open-question scaffolding, or internal vocabulary. The reader-facing-words rule
  applies to machines too: field names here are a public contract (``schema``), not our internals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "ohmega.article/1"
SITE = "https://www.ohmega.monster"
_GRADES = ("confirmed", "likely", "contested", "unconfirmed", "speculative", "opinion")


def build_twin(meta: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """The public, machine-readable record of one article."""
    sources = {s["id"]: s for s in profile.get("source_ledger") or [] if isinstance(s, dict) and s.get("id")}

    def cite(ids: list[str]) -> list[dict]:
        out = []
        for sid in ids or []:
            s = sources.get(sid)
            if s and s.get("safe_to_cite") is not False and str(s.get("url") or "").startswith("http"):
                out.append({k: s[k] for k in ("url", "title", "publisher", "published_at") if s.get(k)})
        return out

    claims = []
    for c in profile.get("claim_ledger") or []:
        if not isinstance(c, dict) or not c.get("text"):
            continue
        grade = str(c.get("status") or "")
        claims.append({
            "id": c.get("id"), "text": " ".join(str(c["text"]).split()),
            "grade": grade if grade in _GRADES else "unconfirmed",
            "salience": c.get("salience") or "",
            "sources": cite(c.get("supported_by") or []),
            "contradicted_by": cite(c.get("contradicted_by") or []),
        })
    slug = str(meta.get("slug") or "")
    return {
        "schema": SCHEMA,
        "url": f"{SITE}/articles/{slug}",
        "title": meta.get("title", ""),
        "summary": meta.get("dek", ""),
        "published_at": meta.get("published_at") or meta.get("date", ""),
        "as_of": meta.get("as_of", ""),
        "status": meta.get("status", ""),
        "grades": {g: sum(1 for c in claims if c["grade"] == g) for g in _GRADES if any(c["grade"] == g for c in claims)},
        "claims": claims,
        "corrections": [{"date": c.get("date", ""), "note": c["note"]}
                        for c in meta.get("corrections") or [] if isinstance(c, dict) and c.get("note")],
        "how_to_cite": "Cite the article URL and the claim id. Grades are Ohmega's assessment of each "
                       "claim as of the date shown, not a guarantee. Source texts belong to their publishers.",
    }


def write_twin(site_dir: Path, twin: dict[str, Any]) -> Path:
    slug = twin["url"].rsplit("/", 1)[-1]
    path = site_dir / "public" / "data" / "articles" / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(twin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_index(site_dir)
    return path


def write_index(site_dir: Path) -> Path:
    """``/data/index.json``: every twin, newest first — the entry point an agent starts from."""
    folder = site_dir / "public" / "data" / "articles"
    rows = []
    for p in folder.glob("*.json"):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.append({"url": t.get("url"), "data": f"{SITE}/data/articles/{p.name}",
                     "title": t.get("title"), "published_at": t.get("published_at"),
                     "as_of": t.get("as_of"), "claims": len(t.get("claims") or [])})
    rows.sort(key=lambda r: str(r.get("published_at") or ""), reverse=True)
    index = site_dir / "public" / "data" / "index.json"
    index.write_text(json.dumps({"schema": "ohmega.index/1", "articles": rows}, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8", newline="\n")
    return index
