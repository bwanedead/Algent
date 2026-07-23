"""
Profile briefing — a deterministic, readable VIEW over a research profile.

The canonical object is the JSON; this renders it into a holistic markdown briefing a
consuming agent (the drafter, a future corpus-context lookup) reads instead of groveling
through raw JSON — the gist first, then the field, then the evidence, down to detail it
can drill by id. Salience orders what matters most to the top. A view, never the source
of truth. Pure: profile in, markdown out.
"""

from __future__ import annotations

from .profile import SignalProfile

_SALIENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def render_briefing(profile: SignalProfile) -> str:
    """Render a research profile into a holistic, drill-down markdown briefing."""
    ent_name = {e.id: e.name for e in profile.entities}
    src_name = {s.id: (s.title or s.url or s.id) for s in profile.source_ledger}
    out: list[str] = [
        f"# {profile.title}",
        f"_status: {profile.profile_status} · as_of: {profile.as_of or '?'} · "
        f"rev {profile.revision} · {profile.generator or '?'}_",
        "",
    ]
    if profile.summary:
        out += [profile.summary, ""]
    if profile.output_recommendations:
        out += [f"**Recommended outputs:** {', '.join(profile.output_recommendations)}", ""]

    # Grounding caveat up front — so a consuming drafter writes only to the real confidence.
    weak = sum(
        1 for c in profile.claim_ledger if c.salience == "high" and c.grounding != "snapshotted"
    )
    if weak:
        out += [
            f"> **Grounding caveat:** {weak} high-salience claim(s) rest on search snippets, "
            "not deep-read sources. Write to that confidence — do not overstate.",
            "",
        ]

    # The field — threads, most-salient first.
    if profile.threads:
        out.append("## What's going on (the field)")
        for t in sorted(profile.threads, key=lambda t: _SALIENCE_ORDER.get(t.salience, 1)):
            kind = f" ({t.kind})" if t.kind else ""
            warn = "  (!) weakly grounded" if (t.salience == "high" and t.grounding != "snapshotted") else ""
            out.append(f"### {t.title}{kind}  ·{t.salience} / {t.grounding}·{warn}")
            if t.body:
                out.append(t.body)
            links = []
            if t.entities:
                links.append("entities: " + ", ".join(ent_name.get(e, e) for e in t.entities))
            if t.claims:
                links.append("grounded in: " + ", ".join(t.claims))
            if links:
                out.append("_" + "  |  ".join(links) + "_")
            out.append("")

    if profile.countries_of_relevance:
        out.append("## Countries of relevance (feed flags)")
        for c in profile.countries_of_relevance:
            role = f" — {c.role}" if c.role else ""
            name = c.name or c.iso2
            out.append(f"- **{c.iso2.upper()}** {name}{role}")
        out.append("")

    if profile.entities:
        out.append("## Key players")
        for e in profile.entities:
            role = f" — {e.role}" if e.role else ""
            out.append(f"- **{e.name}** ({e.type}){role}  `{e.id}`")
        out.append("")

    # Evidence — claims, most-salient first.
    if profile.claim_ledger:
        out.append("## Evidence (claims)")
        for c in sorted(profile.claim_ledger, key=lambda c: _SALIENCE_ORDER.get(c.salience, 1)):
            sup = ", ".join(src_name.get(s, s) for s in c.supported_by) or "-"
            warn = "  (!) high-salience, snippet-only" if (c.salience == "high" and c.grounding != "snapshotted") else ""
            line = f"- [{c.status}/{c.grounding}] {c.text}  <- {sup}  `{c.id}`{warn}"
            if c.contradicted_by:
                line += "  (contradicted: " + ", ".join(src_name.get(s, s) for s in c.contradicted_by) + ")"
            out.append(line)
        out.append("")

    if profile.source_ledger:
        out.append("## Sources")
        for s in profile.source_ledger:
            snap = " [snapshot]" if s.snapshot else ""
            out.append(f"- ({s.source_type}) {s.title or s.url} — {s.url}{snap}  `{s.id}`")
        out.append("")

    if profile.omissions or profile.open_questions:
        out.append("## Gaps")
        out += [f"- omission: {o}" for o in profile.omissions]
        out += [f"- open question: {q}" for q in profile.open_questions]
        out.append("")

    flags = []
    if profile.data_notes:
        flags.append(f"data notes (analytics): {len(profile.data_notes)}")
    if profile.visual_opportunities:
        flags.append(f"visual opportunities: {len(profile.visual_opportunities)}")
    if profile.derived_leads:
        flags.append(f"derived leads: {len(profile.derived_leads)}")
    if flags or profile.watch_triggers:
        out.append("## Forward / flags")
        out += [f"- {f}" for f in flags]
        out += [f"- watch: {w}" for w in profile.watch_triggers]
        out.append("")

    return "\n".join(out).rstrip() + "\n"
