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
    # Only a markdown heading or a bold-only label may ride above the table — never free prose.
    if start > 0:
        prev = lines[start - 1].strip()
        if prev and (
            re.match(r"^#{1,3}\s+\S", prev)
            or re.fullmatch(r"\*\*[^*]+\*\*", prev)
        ):
            head = start - 1
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

# Our own pipeline vocabulary, leaking onto the page. "The signed text was not available in
# this run" tells a reader that a research pass they know nothing about did not find something;
# the fact about the world is simply that it was not available. These exact phrases are banned in
# two doctrine files and shipped anyway, so they are removed mechanically — safe to do because
# each is a trailing prepositional phrase whose deletion leaves a correct sentence, and because
# there is no context in which either is right on a reader-facing page.
_PROCESS_PHRASE = re.compile(r"\s+in this (?:run|pass|review|iteration)\b", re.I)

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


#: Field labels the drafter sometimes emits INSIDE the body, having been asked for a titled
#: package and answered with the labels attached. A published piece opened, verbatim:
#:
#:     TITLE: The Tiny Pump That Lets Corals Breathe  and Why Heat Makes It Suffocate Them
#:     STANDFIRST: Reef corals beat microscopic hairs to spin millimetre-scale vortices...
#:
#: above a body that then said the same thing again in prose. The real title and dek were
#: already parsed out of the markdown heading, so this is pure scaffolding — the shape of the
#: request showing through the answer — and it is duplicated content as well as a tell that a
#: machine wrote the page. Anchored to line starts so a sentence mentioning a title is safe.
_SCAFFOLD_LABEL = re.compile(
    r"^[ \t]*(?:\*\*|__)?"
    r"(?:TITLE|HEADLINE|STANDFIRST|DEK|SUBTITLE|SUBHEAD|BODY|ARTICLE|DRAFT|LEDE|LEAD|"
    r"SUMMARY|QUICK[ _-]?TAKE|REVIEW[ _-]?STATUS|VERDICT|STATUS|NOTES?|OUTPUT)"
    r"(?:\*\*|__)?[ \t]*:[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_scaffold_lines(body: str) -> str:
    """Remove whole lines that are nothing but an agent field label and its value.

    A label mid-paragraph is left alone: "the paper's title: 'X'" is prose, not scaffolding.
    Only a line that STARTS with the label is machine furniture.
    """
    kept = [line for line in body.splitlines() if not _SCAFFOLD_LABEL.match(line)]
    return "\n".join(kept)


def _clean_prose(body: str) -> str:
    """Strip the machine-citation markers for the reader view (the appendix carries the trace)."""
    # Order: markdown-link form first (would otherwise leave ` [` crumbs), then bracket lists,
    # then bare/backticked ids, then residual wrapper crumbs and comma trails the model left
    # between markers ("fact. `[`[clm…](#)`, `[`[clm…](#)`" → "fact.,," without this).
    out = _strip_scaffold_lines(body)
    out = _MARKER_MD_LINK.sub("", out)
    out = _MARKER.sub("", out)
    out = _MARKER_TOKEN.sub("", out)
    out = _MARKER_CRUMBS.sub("", out)
    out = _PROCESS_PHRASE.sub("", out)
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
    all_analytics = list(analytics or [])
    produced = [a for a in all_analytics
                if a.get("status") == "produced" and (a.get("artifact_name") or a.get("body_md"))]
    skipped = [
        a for a in all_analytics
        if a.get("status") and a.get("status") != "produced"
    ]

    body = _ensure_x_embed_links(_clean_prose(draft.body), cited_sources)

    out = [f"# {draft.title or '(untitled)'}"]
    if draft.standfirst:
        out += [f"*{draft.standfirst}*"]
    out += _quick_take_block(draft)
    out += ["", *_body_with_figures(body, produced)]
    out += ["---", *_appendix(
        draft, cited_sources, cited_claims, sources, produced, skipped=skipped,
    )]
    return "\n".join(out).rstrip() + "\n"


def _quick_take_block(draft: ArticleDraft) -> list[str]:
    """Cold-reader gist between dek and body — machine-contract heading for the site converter."""
    qt = getattr(draft, "quick_take", None)
    if qt is None or not getattr(qt, "filled", lambda: False)():
        return []
    lines = ["", "## At a glance"]
    if qt.what_happened.strip():
        lines.append(f"- **What happened:** {qt.what_happened.strip()}")
    if qt.why_it_matters.strip():
        lines.append(f"- **Why it matters:** {qt.why_it_matters.strip()}")
    if qt.what_is_uncertain.strip():
        lines.append(f"- **What remains uncertain:** {qt.what_is_uncertain.strip()}")
    return lines if len(lines) > 2 else []


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
    if str(a.get("visual_class") or "") == "locator_map":
        return True
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
    """Place figures by declared placement; maps still default early.

    - after_quick_take → before the first body paragraph (quick-take already precedes body)
    - after_opening / maps → after the opening paragraph(s), never before the open
    - after_section → after the first ``##``/``###`` section body
    - mid_body → near the midpoint of the prose blocks
    - anything else → after the prose
    """
    if not produced:
        return [body, ""]

    at_qt: list[dict] = []
    early: list[dict] = []
    after_sec: list[dict] = []
    mid: list[dict] = []
    late: list[dict] = []
    for a in produced:
        place = str(a.get("placement") or "")
        if place == "after_quick_take":
            at_qt.append(a)
        elif place == "after_section":
            after_sec.append(a)
        elif place == "mid_body":
            mid.append(a)
        elif place == "after_opening" or _is_map_figure(a):
            early.append(a)
        else:
            late.append(a)

    if not (at_qt or early or after_sec or mid):
        return [body, ""] + _figures(late)

    blocks = [b for b in re.split(r"\n\n+", body.strip()) if b]
    if not blocks:
        return _figures(produced)

    # Absorb a second opening block only when it is still prose — never a section heading.
    open_at = 1
    if (
        len(blocks[0].split()) < 40
        and len(blocks) > 1
        and not re.match(r"^#{2,3}\s", blocks[1])
    ):
        open_at = 2

    section_at = open_at
    headings = [i for i, b in enumerate(blocks) if re.match(r"^#{2,3}\s", b)]
    if len(headings) >= 2:
        section_at = headings[1]
    elif len(headings) == 1:
        section_at = len(blocks)

    mid_at = max(open_at, len(blocks) // 2)

    pieces: list[str] = []
    placed = {"qt": False, "early": False, "sec": False, "mid": False}

    def _blank() -> None:
        if pieces and pieces[-1] != "":
            pieces.append("")

    def _place(bucket: list[dict], which: str) -> None:
        if not bucket or placed[which]:
            return
        _blank()
        pieces.extend(_figures(bucket))
        placed[which] = True

    for i, block in enumerate(blocks):
        if i == 0:
            _place(at_qt, "qt")
        if i == open_at:
            _place(early, "early")
        if i == section_at:
            _place(after_sec, "sec")
        if i == mid_at:
            _place(mid, "mid")
        _blank()
        pieces.append(block)

    # open_at / section_at / mid_at may equal len(blocks) — place after the body, never before it.
    if early and not placed["early"]:
        _blank()
        pieces.extend(_figures(early))
    if after_sec and not placed["sec"]:
        _blank()
        pieces.extend(_figures(after_sec))
    if mid and not placed["mid"]:
        _blank()
        pieces.extend(_figures(mid))
    if at_qt and not placed["qt"]:
        pieces[0:0] = _figures(at_qt) + ([""] if pieces else [])
    if late:
        _blank()
        pieces.extend(_figures(late))
    return pieces


# A caption that opens by explaining the figure's purpose *to us* — "This map orients a reader
# to the Canadian location…", "Gives readers immediate geographic orientation for…" — is our
# rationale for building it, printed where the reader expects to be told what they are looking
# at (style.md, machine signature 4). The doctrine now forbids writing them; this removes the
# ones that get written anyway, because the pattern is mechanical: the meta-sentence comes first
# and a genuinely useful description follows it.
_CAPTION_META = re.compile(
    r"^\s*(?:(?:This|The)\s+(?:map|chart|table|figure|graphic|analytic|visual)\b[^.]*?"
    r"\b(?:reader|readers)\b[^.]*\.|"
    r"(?:Gives|Give|Helps|Help|Shows|Orients|Allows|Lets)\s+(?:the\s+)?readers?\b[^.]*\.)\s*",
    re.I,
)


def strip_caption_meta(caption: str) -> str:
    """Drop a leading sentence that explains the figure to us instead of to the reader.

    Only ever removes a *whole* leading sentence, and never the last one standing — so a caption
    that is nothing but meta-narration is left alone rather than emptied, and the failure stays
    visible instead of turning into a bare figure.
    """
    stripped = _CAPTION_META.sub("", caption, count=1).strip()
    return stripped if stripped else caption.strip()


def _figure_explainer(a: dict) -> str:
    """Plain 'what this shows' for a cold reader — never make them reverse-engineer the chart.

    Prefer harness caption (already includes question + provenance). Fall back to question +
    AI label so a figure never lands bare.
    """
    caption = str(a.get("caption") or "").strip()
    if caption:
        return strip_caption_meta(caption)
    question = strip_caption_meta(str(a.get("question") or "").strip())
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
              produced: list[dict] | None = None, skipped: list[dict] | None = None) -> list[str]:
    # The heading is the machine contract (the site splits the receipts here) and the site's own
    # disclosure label already says what this is — so no preamble explaining the receipts to the
    # reader. Show the record; don't narrate it.
    out = ["## How we know this", ""]
    if draft.frame:
        out += [f"**How this piece is framed:** {draft.frame}", ""]

    if produced:
        out.append("**Charts & tables** — _AI-assisted; provenance on each line_")
        for a in produced:
            refs = ", ".join(a.get("data_refs", []) or [])
            asof = f" · as of {a['as_of']}" if a.get("as_of") else ""
            fc = a.get("figure_check") or {}
            if fc.get("mode") == "sourced":
                basis = "sourced for this figure"
            elif refs:
                basis = f"from claims {refs}"
            else:
                basis = "from cited evidence"
            check = ("" if fc.get("verified") else
                     f" · ⚠ figures not all matched to the cited claims: {', '.join(fc.get('unverified', []))}")
            out.append(f"- {a.get('title') or 'analytic'} — {basis}{asof}{check}")
        out.append("")

    if skipped:
        out.append("**Visuals not shipped** — _planned but not fulfilled_")
        for a in skipped:
            rid = a.get("request_id") or a.get("id") or "?"
            status = a.get("status") or "skipped"
            title = a.get("title") or rid
            note = a.get("note") or a.get("rationale") or ""
            note_bit = f" — {note}" if note else ""
            out.append(f"- {title} ({rid}): {status}{note_bit}")
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
