"""
Publish view — the reader-facing article + a transparency appendix ("the receipts").

The raw draft carries inline `[clm_…]` machine-citation markers (for the deterministic audit).
A reader shouldn't see those. This renders the clean piece, then appends an honest, organized
appendix: what the article rests on, and — crucially — HOW FAR we could actually verify each
source and claim, and where we hit a wall. It is pure + deterministic (draft + profile ledgers
in, markdown out) — no model, no cost. The spirit: give the reader the resources to double-check
and, where a wall stopped us, to go look for themselves (they may not share our wall).
"""

from __future__ import annotations

import re

from algent_backend.agent_system.agents.research.profile import SignalProfile

from .analytics_contracts import AI_ANALYTIC_LABEL
from .citations import unverified_prose_figures
from .draft import ArticleDraft

_IMAGE_SUFFIXES = (".svg", ".png")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _table_block(body_md: str) -> str:
    """The contiguous markdown table in ``body_md`` (its ``|…|`` rows), plus one heading/label line
    directly above it if present — and NOTHING else.

    The worker's markdown is grok-authored: any free-text it wraps around the table (a 'Source:'
    line, a 'hawkish momentum builds' aside) would otherwise reach the reader without passing the
    caveat gate the draft prose passes through. Bounding the inline to the table itself removes that
    vector deterministically; the residual — the cell wording — is largely pinned by the figure
    check and the receipts line. Prose-only analytics (an ``insight`` with no table) inline nothing
    here: ungated prose must not reach the reader (its provenance still shows in the receipts)."""
    lines = body_md.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        if _TABLE_ROW.match(ln):
            if start is None:
                start = i
            end = i
        elif start is not None:
            break                                  # first contiguous table run only
    if start is None:
        return ""
    head = start
    if start > 0 and lines[start - 1].strip() and not _TABLE_ROW.match(lines[start - 1]):
        head = start - 1                           # one adjacent heading/label line, if any
    return "\n".join(lines[head:end + 1]).strip()

# Inline machine markers the drafter emits. The prompt asks for the bracketed list form
# ("[clm_ab12, clm_cd34, src_ef56]"), but the model's format varies run to run — it also emits
# backtick-wrapped or bare ids ("`clm_ab12` `src_ef56`"), and sometimes markdown-link wrappers
# like `` [`[clm_ab12](#)`, `[`[ent_…](#)` ``. The reader-facing floor must strip ALL of them
# regardless of the drafter's formatting whim (ids are `clm_`/`src_`/`ent_` + hex — never prose).
_MARKER = re.compile(r"\s*\[(?:clm_|src_|ent_)[^\]]*\]")                    # [clm_ab12, src_ef56]
# Accepted edge: no trailing boundary on the hex, so a malformed id (`clm_0fd207x`) strips the hex
# run and leaves the stray `x`. That is deliberately conservative — a strict boundary risks eating
# real prose that abuts a well-formed id. Do NOT loosen this into a broader pattern to "fix" the
# stray char; a malformed marker is a drafter bug to catch upstream, not a reason to strip prose.
_MARKER_TOKEN = re.compile(r"\s*`?(?:clm_|src_|ent_)[0-9a-fA-F]+`?")       # `clm_ab12` or bare
# Markdown-link citation form (seen 2026-07): `[`[clm_hex](#)`  or  [clm_hex](#)
_MARKER_MD_LINK = re.compile(
    r"(?:\s*,)?\s*`?\[`?(?:clm_|src_|ent_)[0-9a-fA-F]+\]\(#\)`?"
)
# Stray wrapper crumbs left after link-form strip: bare `[` / trailing backticks near punctuation
_MARKER_CRUMBS = re.compile(r"(?:\s*`+\[`*)+|\s*`+(?=\s|$|[.,;:])")

_GROUNDING_WORDS = {
    "snapshotted": "read in full",
    "snippet_only": "from a source summary — we did not read the full source",
    "unsourced": "our synthesis across the evidence — no single cited source",
}

# X/Twitter status URLs — receipts must name the medium, not look like a wire byline.
_X_STATUS_RE = re.compile(
    r"(?:https?://)?(?:(?:www|mobile)\.)?(?:twitter|x)\.com/"
    r"(?:(?P<handle>[A-Za-z0-9_]{1,15})/status/\d+|i/web/status/\d+)",
    re.I,
)
_WEAK_X_TITLE = re.compile(
    r"(?i)^(post by\s*@?\w+|x\s*post\b|tweet by\b)|web status wrapper",
)


def _source_label(source) -> str:
    """Reader-facing name for a source line.

    Minimize deception: an X post must read as an X post. Bare handles and titles like
    "Post by @OSINTtechnical" get rewritten so they cannot be mistaken for a known outlet.
    Prefer an already-honest ``publisher`` string from research when present.
    """
    url = (getattr(source, "url", None) or "").strip()
    title = (getattr(source, "title", None) or "").strip()
    publisher = (getattr(source, "publisher", None) or "").strip()

    m = _X_STATUS_RE.search(url)
    if m:
        handle = (m.group("handle") or "").lstrip("@")
        pub_names_medium = bool(
            publisher and re.search(r"(?i)\bx(\s*post|\.com)?\b|twitter", publisher)
        )
        if pub_names_medium:
            base = publisher
        elif handle:
            base = f"X post · @{handle}"
        else:
            base = publisher or "X post"
        # Drop weak/wrapper titles that launder a handle into institutional authority.
        if not title or _WEAK_X_TITLE.search(title):
            return base
        if title.lower() in base.lower() or (handle and title.lower() in {handle.lower(), f"@{handle.lower()}"}):
            return base
        return f"{base} — {title}"

    if title and publisher and publisher.lower() not in title.lower():
        return f"{title} — {publisher}"
    return title or publisher or url


def _clean_prose(body: str) -> str:
    """Strip the machine-citation markers for the reader view (the appendix carries the trace)."""
    # Order: markdown-link form first (would otherwise leave ` [` crumbs), then bracket lists,
    # then bare/backticked ids, then residual wrapper crumbs and comma trails the model left
    # between markers ("fact. `[`[clm…](#)`, `[`[clm…](#)`" → "fact.,," without this).
    out = _MARKER_MD_LINK.sub("", body)
    out = _MARKER.sub("", out)
    out = _MARKER_TOKEN.sub("", out)
    out = _MARKER_CRUMBS.sub("", out)
    out = re.sub(r"([.!?])\s*,+", r"\1", out)          # "end.,," → "end."
    out = re.sub(r",\s*,+", ", ", out)                   # leftover ", ," runs
    out = re.sub(r"[ \t]+,", ",", out)
    out = re.sub(r" {2,}", " ", out)
    out = re.sub(r" *\n", "\n", out)
    return out.strip()


def _capture_date(source) -> str:
    """The date a source was captured (YYYY-MM-DD), for as-of anchoring on volatile sources."""
    ca = (source.snapshot.captured_at if source.snapshot else "") or ""
    return ca[:10]


def _claim_asof(claim, sources: dict) -> str:
    """The capture date behind a deep-read claim (for fast-moving figures)."""
    for sid in claim.supported_by:
        s = sources.get(sid)
        if s and s.snapshot and s.snapshot.captured_at:
            return s.snapshot.captured_at[:10]
    return ""


def render_published_article(
    draft: ArticleDraft, profile: SignalProfile, analytics: list[dict] | None = None
) -> str:
    claims = {c.id: c for c in profile.claim_ledger}
    sources = {s.id: s for s in profile.source_ledger}
    cited_claims = [claims[c] for c in draft.cited_claim_ids if c in claims]
    cited_src_ids = set(draft.cited_source_ids) | {s for c in cited_claims for s in c.supported_by}
    cited_sources = [sources[s] for s in cited_src_ids if s in sources]
    produced = [a for a in (analytics or [])
                if a.get("status") == "produced" and (a.get("artifact_name") or a.get("body_md"))]

    body = _ensure_x_embed_links(_clean_prose(draft.body), cited_sources)

    out = [f"# {draft.title or '(untitled)'}"]
    if draft.standfirst:
        out += [f"*{draft.standfirst}*"]
    out += ["", *_body_with_figures(body, produced)]
    out += ["---", *_appendix(draft, cited_sources, cited_claims, sources, produced)]
    return "\n".join(out).rstrip() + "\n"


def _ensure_x_embed_links(body: str, cited_sources: list) -> str:
    """If prose leans on an X status but has no status URL, add a sole-line link for site embeds.

    The site embeds a status only when a paragraph is solely a link to x.com/.../status/...
    Drafters often name @handle without the URL; receipts still hold it. Inject once per
    missing status so the reader can see the post (and the embed can fire).
    """
    out = body
    for s in cited_sources:
        url = (getattr(s, "url", None) or "").strip()
        m = _X_STATUS_RE.search(url)
        if not m:
            continue
        handle = (m.group("handle") or "").lstrip("@")
        status_id = re.search(r"/status/(\d+)", url, re.I)
        sid = status_id.group(1) if status_id else ""
        if not sid:
            continue
        if re.search(rf"/status/{re.escape(sid)}\b", out, re.I):
            continue
        # Only inject when the prose actually leans on X / this handle (avoid random receipts).
        mentions = bool(re.search(r"\bon X\b|\bpost on X\b|x\.com|twitter\.com", out, re.I))
        if handle and re.search(rf"@{re.escape(handle)}\b|\b{re.escape(handle)}\b", out, re.I):
            mentions = True
        if not mentions:
            continue
        canonical = (
            f"https://x.com/{handle}/status/{sid}" if handle else f"https://x.com/i/web/status/{sid}"
        )
        label = f"Post on X · @{handle}" if handle else "Post on X"
        out = out.rstrip() + f"\n\n[{label}]({canonical})\n"
    return out


def _is_map_figure(a: dict) -> bool:
    name = str(a.get("artifact_name") or "").lower()
    title = str(a.get("title") or "").lower()
    kind = str(a.get("kind") or "").lower()
    spec = str(a.get("spec") or a.get("question") or "").lower()
    if "map" in name or "map" in title or "map" in spec:
        return True
    if kind == "image" and any(k in title or k in spec for k in ("geo", "theater", "location", "choke")):
        return True
    return False


def _body_with_figures(body: str, produced: list[dict]) -> list[str]:
    """Put orientation maps early (after the first prose block); other figures after the body.

    Geographic figures help most when the reader still needs the landscape — not after a wall of
    text. Trajectory charts etc. still trail the prose.
    """
    if not produced:
        return [body, ""]
    early = [a for a in produced if _is_map_figure(a)]
    late = [a for a in produced if a not in early]
    if not early:
        return [body, ""] + _figures(produced)

    # Split after the first paragraph (or first two short ones if the open is a single sentence).
    parts = re.split(r"\n\n+", body.strip(), maxsplit=1)
    if len(parts) == 1:
        return [body, ""] + _figures(early) + _figures(late)

    head, tail = parts[0], parts[1]
    # If the first block is very short, take one more paragraph so the map lands after landscape setup.
    if len(head.split()) < 40 and "\n\n" in tail:
        more = re.split(r"\n\n+", tail, maxsplit=1)
        head = head + "\n\n" + more[0]
        tail = more[1] if len(more) > 1 else ""
    out = [head, ""] + _figures(early)
    if tail.strip():
        out += [tail.strip(), ""]
    out += _figures(late)
    return out


def _figure_explainer(a: dict) -> str:
    """Plain 'what this shows' for a cold reader — never make them reverse-engineer the chart.

    Prefer harness caption (already includes question + provenance). Fall back to question +
    AI label so a figure never lands bare.
    """
    caption = str(a.get("caption") or "").strip()
    if caption:
        return caption
    question = str(a.get("question") or "").strip()
    bits = [b for b in (question, AI_ANALYTIC_LABEL + ".") if b]
    return " ".join(bits)


def _figures(produced: list[dict]) -> list[str]:
    """Place each produced analytic in the reader view by TYPE:

    - a chart/illustration (``.svg``/``.png``) is embedded as an image, with a plain explainer
      under it (what is measured / what it shows + provenance);
    - a table/insight (markdown) is INLINED as text — an image link to a ``.md`` file would render
      as a broken image — followed by the same style of explainer.
    """
    out: list[str] = []
    for a in produced:
        name = a.get("artifact_name", "")
        title = str(a.get("title") or "").strip()
        explainer = _figure_explainer(a)
        if name.endswith(_IMAGE_SUFFIXES):
            body = [f"![{title or 'analytic'}]({name})"]
        elif table := _table_block(str(a.get("body_md") or "")):
            body = [table]
        else:
            continue
        # Heading = what is measured; italic line under = what it shows + source/as-of.
        out += [f"**{title}**" if title else "", "", *body, "", f"*{explainer}*", ""]
    return [ln for ln in out if ln is not None]


def _appendix(draft: ArticleDraft, cited_sources: list, cited_claims: list, sources: dict,
              produced: list[dict] | None = None) -> list[str]:
    # The heading is the machine contract (the site splits the receipts here) and the site's own
    # disclosure label already says what this is — so no preamble explaining the receipts to the
    # reader. Show the record; don't narrate it.
    out = ["## How we know this", ""]
    if draft.frame:
        out += [f"**How this piece is framed:** {draft.frame}", ""]

    if produced:
        out.append("**Charts & tables** — _each built only from the cited claims below, by an AI tool_")
        for a in produced:
            refs = ", ".join(a.get("data_refs", []))
            asof = f" · as of {a['as_of']}" if a.get("as_of") else ""
            fc = a.get("figure_check") or {}
            check = ("" if fc.get("verified") else
                     f" · ⚠ figures not all matched to the cited claims: {', '.join(fc.get('unverified', []))}")
            out.append(f"- {a.get('title') or 'analytic'} — from claims {refs}{asof}{check}")
        out.append("")

    out.append("**Sources**")
    for s in sorted(cited_sources, key=lambda s: (s.snapshot is None, s.source_type)):
        if s.snapshot:
            d = _capture_date(s)
            access = "read in full" + (f" · captured {d}" if d else "")
        else:
            access = "full text not obtained — used its summary"
        label = _source_label(s)
        out.append(f"- ({s.source_type}) {label} — {s.url}  ·  _{access}_")
    out.append("")

    out.append("**Claims, and how far we tracked each down**")
    for c in cited_claims:
        asof = _claim_asof(c, sources) if c.grounding == "snapshotted" else ""
        stamp = f" (as of {asof})" if asof else ""
        out.append(f"- _[{c.status}]_ {c.text}  ·  {_GROUNDING_WORDS.get(c.grounding, c.grounding)}{stamp}")
    out.append("")

    out += _limits(draft, cited_sources, cited_claims, sources)
    return out


def _limits(draft: ArticleDraft, cited_sources: list, cited_claims: list, sources: dict) -> list[str]:
    """The honest limits: sources we didn't get in full, our-synthesis claims, and any figures
    that don't appear in the cited evidence — what to double-check."""
    no_full = [s for s in cited_sources if s.snapshot is None]
    synth = [c for c in cited_claims if c.grounding == "unsourced"]
    prose = " ".join(x for x in (draft.title, draft.standfirst, draft.body) if x)
    figures = unverified_prose_figures(prose, cited_claims, sources)
    if not (no_full or synth or figures):
        return []
    out = ["**Where we hit a limit / what to double-check**"]
    for s in no_full:
        # Neutral: snapshot-less can mean "walled" OR "not pursued" — do not claim effort we may
        # not have spent. Say what is true: we did not obtain the full text.
        out.append(
            f"- We did not obtain the full text of **{s.title or s.url}** ({s.url}); claims resting "
            "on it are from its summary — you may be able to reach it directly."
        )
    for c in synth:
        out.append(f"- \"{c.text}\" is our reading across the evidence, not a single sourced fact.")
    if figures:
        # Honest about the two possibilities: a source we read may state the figure exactly (worth
        # confirming there), OR a live source moved since. Never asserts the figure is wrong.
        out.append(
            f"- Figures we could not match to our stored evidence — worth confirming against the "
            f"source (which may state them exactly), and note live sources move: {', '.join(figures)}."
        )
    out.append("")
    return out
