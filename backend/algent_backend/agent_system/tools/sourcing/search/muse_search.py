"""
Provider-side web search, via the house model's own ``web_search`` tool.

The model runs the searches itself and returns text with ``url_citation`` annotations. We take
the CITATIONS, not the synthesis: this slots into the existing provider chain returning the same
``{title, url, content}`` hits Tavily and Brave do, so nothing downstream learns a new shape and
the grounding model is untouched.

WHY IT IS LAST IN THE CHAIN. Search hits are snippet-tier evidence whoever returns them, so this
is a like-for-like substitute — but it is a substitute with a difference worth respecting: with a
keyword API we choose the query and see every result, while here the model chooses its own
queries and shows us what it decided to cite. That is fine for finding pages and wrong to lean on
when the free tiers are healthy, so it sits behind them and catches the case that would otherwise
be a dead end: every configured engine out of quota.

It reaches nothing Firecrawl reaches. This is a search provider; page reading is a separate lane
and stays on httpx + trafilatura.
"""

from __future__ import annotations

from typing import Any

#: Kept small: this is a fallback for finding pages, not a research agent.
_MAX_SEARCHES_HINT = 3


def _blocks(content: Any) -> list[dict[str, Any]]:
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _hits_from_citations(content: Any) -> list[dict[str, str]]:
    """Turn url_citation annotations into search hits, de-duplicated by URL."""
    out: dict[str, dict[str, str]] = {}
    for block in _blocks(content):
        text = str(block.get("text") or "")
        for ann in block.get("annotations") or []:
            if not isinstance(ann, dict) or ann.get("type") != "url_citation":
                continue
            url = str(ann.get("url") or "").strip()
            if not url or url in out:
                continue
            # A citation marks a span of the model's text; that span is the closest thing to a
            # snippet this API gives us, so it becomes the hit's content.
            start, end = ann.get("start_index"), ann.get("end_index")
            snippet = ""
            if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text):
                snippet = text[start:end].strip()
            out[url] = {
                "title": str(ann.get("title") or "").strip() or url,
                "url": url,
                "content": snippet or text[:400].strip(),
            }
    return list(out.values())


def search(query: str, max_results: int = 8) -> list[dict[str, str]] | dict[str, Any]:
    """Run ``query`` through the model's own web search. Returns hits, or an error dict.

    The error dict shape matches what the chain already understands, so a failure here falls
    through to the next provider exactly like any other.
    """
    try:
        from algent_backend.agent_system.foundation.models import house_spec
        from algent_backend.agent_system.foundation.models.resolver import ModelResolver

        client = ModelResolver().resolve(house_spec(reasoning_effort="low")).client
        bound = client.bind_tools([{"type": "web_search"}])
        response = bound.invoke(
            f"Search the web for: {query}\n\n"
            f"Run at most {_MAX_SEARCHES_HINT} searches. Report what the sources say and cite "
            f"each one. Do not answer from memory — if the search returns nothing useful, say so.",
        )
    except Exception as exc:  # noqa: BLE001 — a dead provider is the chain's business, not ours
        return {"error": f"muse web_search failed: {str(exc)[:160]}"}

    hits = _hits_from_citations(response.content)
    if not hits:
        return {"error": "muse web_search returned no citations"}
    return hits[:max_results]
