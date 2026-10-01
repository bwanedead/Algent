"""
Render the heat board and briefs as self-contained HTML (inline SVG, light + dark, no scripts).

Charts must be obvious, not decodable (newsroom rule): numbers and relationship words sit ON the
marks — no legends to learn. Verification is visible everywhere: a researched item and a reported
headline never look the same.
"""

from __future__ import annotations

import html
import math
from typing import Any

from .contracts import Brief

_CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b19;--muted:#6b6862;--rule:#e2dfd8;--card:#fff;--accent:#b4541a;
--hot:#c2410c;--warm:#d97706;--cool:#0e7490;--good:#15803d;--rep:#8a8580}
@media (prefers-color-scheme:dark){:root{--bg:#141412;--fg:#ecebe8;--muted:#a29e97;--rule:#2d2c29;
--card:#1c1b19;--accent:#f0955a;--hot:#fb923c;--warm:#fbbf24;--cool:#22d3ee;--good:#4ade80;--rep:#8f8a83}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}h2{font-size:17px;margin:30px 0 10px;
text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.sub{color:var(--muted);font-size:13px}.card{background:var(--card);border:1px solid var(--rule);
border-radius:8px;padding:14px 16px;margin:10px 0}.bluf{border-left:4px solid var(--accent);font-size:16px}
.pill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid currentColor;
margin-right:6px;white-space:nowrap}.researched{color:var(--good)}.reported{color:var(--rep)}
.rising{color:var(--hot)}.easing{color:var(--cool)}.steady,.unclear{color:var(--muted)}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:7px 6px;border-bottom:1px solid var(--rule);
vertical-align:top;font-size:14px}th{font-size:12px;color:var(--muted);font-weight:600}
svg text{fill:var(--fg);font:12px ui-sans-serif,system-ui,sans-serif}svg .m{fill:var(--muted)}
a{color:var(--accent)}ul{margin:6px 0 0;padding-left:20px}li{margin:3px 0}
.note{font-size:12px;color:var(--muted);margin-top:28px;border-top:1px solid var(--rule);padding-top:10px}
"""


def _e(s: Any) -> str:
    return html.escape(str(s or ""))


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{_e(title)}</title><style>{_CSS}</style>"
            f"</head><body><main>{body}</main></body></html>")


# ── heat board ────────────────────────────────────────────────────────────────────────────────
_TREND = {"heating": ("▲ heating", "var(--hot)"), "new": ("● new", "var(--warm)"),
          "steady": ("● steady", "var(--muted)"), "cooling": ("▼ cooling", "var(--cool)")}


def heat_svg(heat: list[dict], *, top: int = 12) -> str:
    rows = heat[:top]
    if not rows:
        return "<p class='sub'>No theaters found in this window.</p>"
    w, row_h, name_w, spark_w = 900, 34, 330, 250
    peak = max((p["count"] for h in rows for p in h["series"]), default=1) or 1
    max_heat = max(h["heat"] for h in rows) or 1
    parts = [f"<svg viewBox='0 0 {w} {row_h * len(rows) + 22}' width='100%' role='img' "
             f"aria-label='Theater heat board'>"]
    days = rows[0]["series"]
    for i, p in enumerate(days):
        x = name_w + 10 + i * (spark_w / len(days))
        parts.append(f"<text class='m' x='{x:.0f}' y='12' font-size='10'>{_e(p['day'][5:])}</text>")
    for r, h in enumerate(rows):
        y = 22 + r * row_h
        label, colour = _TREND.get(h["trend"], ("", "var(--muted)"))
        parts.append(f"<text x='0' y='{y + 20}'>{_e(h['name'][:46])}</text>")
        bw = spark_w / len(h["series"])
        for i, p in enumerate(h["series"]):
            bh = 0 if not p["count"] else max(3, 22 * p["count"] / peak)
            x = name_w + 10 + i * bw
            parts.append(f"<rect x='{x:.1f}' y='{y + 26 - bh:.1f}' width='{bw - 4:.1f}' height='{bh:.1f}' "
                         f"fill='{colour}' opacity='.85'><title>{_e(p['day'])}: {p['count']}</title></rect>")
            if p["count"]:
                parts.append(f"<text x='{x + bw / 2 - 5:.0f}' y='{y + 24 - bh:.0f}' font-size='10'>{p['count']}</text>")
        hx = name_w + spark_w + 30
        hw = 200 * h["heat"] / max_heat
        parts.append(f"<rect x='{hx}' y='{y + 10}' width='{hw:.0f}' height='12' rx='3' fill='{colour}'/>"
                     f"<text x='{hx + hw + 6:.0f}' y='{y + 21}' font-size='11'>{h['recent']} in 3d · {label}</text>")
    parts.append("</svg>")
    return "".join(parts)


def render_board(board: dict) -> str:
    body = (f"<h1>Heat board</h1><div class='sub'>{board['headlines']} headlines over the {board['window_days']} "
            f"days to {_e(board['as_of'])}, grouped into the dynamics they belong to. Bars: headlines per day. "
            f"Heat: recent volume, weighted up when accelerating or new.</div><div class='card'>"
            f"{heat_svg(board['heat'])}</div><h2>Theaters</h2>")
    names = {t["id"]: t for t in board["theaters"]}
    for h in board["heat"]:
        t = names.get(h["theater_id"], {})
        body += (f"<div class='card'><b>{_e(h['name'])}</b> <span class='sub'>· {_e(t.get('domain'))} · "
                 f"{h['total']} headlines · first seen {_e(h['first_seen'])}</span><div>{_e(t.get('why'))}</div></div>")
    body += ("<div class='note'>Heat is measured from the daily headline radar — what other outlets are "
             "reporting, not verified by us. It says where to look, not what is true.</div>")
    return _page("Heat board", body)


# ── brief ─────────────────────────────────────────────────────────────────────────────────────
_KIND = {"strikes": "var(--hot)", "sabotage": "var(--hot)", "coerces": "var(--warm)", "sanctions": "var(--warm)",
         "deters": "var(--cool)", "supports": "var(--good)", "negotiates": "var(--good)", "other": "var(--muted)"}


_CHANGE = {"escalated": "rising", "eased": "easing", "new": "rising", "resolved": "easing", "unchanged": "steady"}


def actors_svg(brief: Brief) -> str:
    rels = brief.relations
    actors = list(dict.fromkeys([a for r in rels for a in (r.source, r.target)]))
    if len(actors) < 2:
        return ""
    w, h, cx, cy = 900, 440, 450, 220
    rad = 165
    pos = {a: (cx + rad * math.cos(2 * math.pi * i / len(actors) - math.pi / 2),
               cy + rad * math.sin(2 * math.pi * i / len(actors) - math.pi / 2)) for i, a in enumerate(actors)}
    parts = [f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='Who is doing what to whom'>",
             "<defs><marker id='ar' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' "
             "orient='auto-start-reverse'><path d='M0,0L10,5L0,10z' fill='context-stroke'/></marker></defs>"]
    for r in rels:
        (x1, y1), (x2, y2) = pos[r.source], pos[r.target]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1
        sx, sy, ex, ey = x1 + dx / d * 34, y1 + dy / d * 34, x2 - dx / d * 34, y2 - dy / d * 34
        col = _KIND.get(r.kind, "var(--muted)")
        parts.append(f"<line x1='{sx:.0f}' y1='{sy:.0f}' x2='{ex:.0f}' y2='{ey:.0f}' stroke='{col}' "
                     f"stroke-width='2' marker-end='url(#ar)'><title>{_e(r.note)}</title></line>"
                     f"<text x='{(sx + ex) / 2:.0f}' y='{(sy + ey) / 2 - 4:.0f}' font-size='11' "
                     f"text-anchor='middle' style='fill:{col}'>{_e(r.kind)}</text>")
    for a, (x, y) in pos.items():
        parts.append(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='30' fill='var(--card)' stroke='var(--fg)' "
                     f"stroke-width='1.5'/><text x='{x:.0f}' y='{y + 4:.0f}' text-anchor='middle' "
                     f"font-size='11' font-weight='600'>{_e(a[:16])}</text>")
    parts.append("</svg>")
    return "".join(parts)


def render_brief(brief: Brief, *, theater_name: str, heat: dict, as_of: str) -> str:
    esc = brief.escalation
    tl = "".join(
        f"<tr><td class='sub'>{_e(t.date)}</td><td><span class='pill {t.verification}'>{t.verification}</span>"
        f"{_e(t.what)}{f' <a href={_e(t.source)!r}>source</a>' if t.source.startswith('http') else ''}</td>"
        f"<td class='sub'>{_e(', '.join(t.actors))}</td></tr>" for t in sorted(brief.timeline, key=lambda t: t.date))
    effects = lambda items: "".join(  # noqa: E731
        f"<li><b>{_e(x.likelihood)}:</b> {_e(x.effect)}{f' <span class=sub>— watch for {_e(x.watch_for)}</span>' if x.watch_for else ''}</li>"
        for x in items)
    inds = "".join(f"<tr><td><span class='pill {'rising' if i.status == 'observed' else 'steady'}'>{_e(i.status)}"
                   f"</span>{f' <span class=sub>was {_e(i.previous_status)}</span>' if i.previous_status and i.previous_status != i.status else ''}"
                   f"</td><td>{_e(i.signal)}</td><td class='sub'>{_e(i.meaning)}</td></tr>" for i in brief.indicators)
    changes = "".join(f"<li><span class='pill {_CHANGE.get(c.kind, 'steady')}'>{_e(c.kind)}</span>{_e(c.what)}"
                      f"{f' <span class=sub>— {_e(c.basis)}</span>' if c.basis else ''}</li>" for c in brief.changes)
    judgments = "".join(f"<tr><td><b>{j.probability}%</b><div class='sub'>by {_e(j.horizon)}</div></td>"
                        f"<td>{_e(j.statement)}<div class='sub'>{_e(j.basis)}</div></td>"
                        f"<td class='sub'>Yes if: {_e(j.resolves_yes_if)}<br>No if: {_e(j.resolves_no_if)}</td></tr>"
                        for j in brief.judgments)
    alts = "".join(f"<div class='card'><span class='pill {'rising' if a.plausibility == 'leading' else 'steady'}'>"
                   f"{_e(a.plausibility)}</span><b>{_e(a.hypothesis)}</b>"
                   f"<div class='sub'>Fits: {_e(a.consistent_with)}</div>"
                   f"<div class='sub'>Cuts against: {_e(a.inconsistent_with)}</div></div>" for a in brief.alternatives)
    body = (
        f"<div class='sub'>Intelligence brief · {_e(theater_name)} · as of {_e(as_of)}</div><h1>{_e(brief.title)}</h1>"
        f"<div class='card bluf'>{_e(brief.bottom_line)}</div>"
        f"<div class='card'><span class='pill {esc.direction}'>{_e(esc.direction)}</span>"
        f"<span class='pill steady'>pace: {_e(esc.pace)}</span>"
        f"<span class='pill steady'>{heat.get('recent', 0)} headlines in 3 days · {_e(heat.get('trend'))}</span>"
        f"<div style='margin-top:8px'>{_e(esc.assessment)}</div></div>"
        + (f"<h2>What changed since the last brief</h2><ul>{changes}</ul>" if changes else "")
        + f"<h2>Where things stand</h2><div>{_e(brief.situation)}</div>"
        + (f"<h2>Who is doing what to whom</h2><div class='card'>{actors_svg(brief)}</div>" if brief.relations else "")
        + (f"<h2>Timeline</h2><table><tr><th>Date</th><th>Event</th><th>Actors</th></tr>{tl}</table>" if tl else "")
        + (f"<h2>Key judgments</h2><table><tr><th>Odds</th><th>Judgment</th><th>How it will be settled</th></tr>{judgments}</table>" if judgments else "")
        + (f"<h2>Competing explanations</h2>{alts}" if alts else "")
        + (f"<h2>What would change our mind</h2><ul>{''.join(f'<li>{_e(u)}</li>' for u in brief.would_change_our_mind)}</ul>" if brief.would_change_our_mind else "")
        + (f"<h2>What follows</h2><ul>{effects(brief.second_order)}</ul>" if brief.second_order else "")
        + (f"<h2>Watch the periphery</h2><ul>{effects(brief.peripheral)}</ul>" if brief.peripheral else "")
        + (f"<h2>Indicators &amp; warnings</h2><table><tr><th>Status</th><th>Signal</th><th>What it would mean</th></tr>{inds}</table>" if inds else "")
        + (f"<h2>Pulses</h2><div class='sub'>{_e(', '.join(brief.pulses))}</div>" if brief.pulses else "")
        + (f"<h2>What we do not know</h2><ul>{''.join(f'<li>{_e(u)}</li>' for u in brief.unknowns)}</ul>" if brief.unknowns else "")
        + "<div class='note'><span class='pill researched'>researched</span> established by Ohmega's graded research. "
          "<span class='pill reported'>reported</span> other outlets' reporting, not verified by us. "
          "Assessments use estimative language and are Ohmega's judgment, not a guarantee.</div>")
    return _page(brief.title, body)


# ── daily report ──────────────────────────────────────────────────────────────────────────────
def _link(url: str, label: str = "source") -> str:
    return f" <a href='{_e(url)}'>{label}</a>" if str(url).startswith("http") else ""


def _num(v: Any, signed: bool = False) -> str:
    return "–" if v is None else (f"{v:+.1f}" if signed else f"{v:.0f}")


def _statement(s: dict) -> str:
    role = f" ({_e(s.get('role'))})" if s.get("role") else ""
    when = f" · {_e(s.get('when'))}" if s.get("when") else ""
    said = "“" + _e(s["said"]) + "”" if s.get("quote") else _e(s["said"])
    return f"<li><b>{_e(s['who'])}</b>{role}{when}: {said}{_link(s.get('source', ''))}</li>"


def _development(d: dict) -> str:
    stmts = "".join(_statement(s) for s in d.get("statements") or [])
    meta = " · ".join(x for x in (_e(d.get("when")), _e(d.get("where")), _e(", ".join(d.get("actors") or []))) if x)
    srcs = "".join(_link(u, f"[{i + 1}]") for i, u in enumerate(d.get("sources") or []))
    why = f"<div class='sub'>Why it matters: {_e(d.get('significance'))}</div>" if d.get("significance") else ""
    return (f"<div class='card'><span class='pill {d['verification']}'>{_e(d['verification'])}</span>"
            f"<b>{_e(d['headline'])}</b>"
            + (f"<div class='sub'>{meta}</div>" if meta else "") + f"<div>{_e(d.get('detail'))}</div>" + why
            + (f"<ul>{stmts}</ul>" if stmts else "")
            + (f"<div class='sub'>Sources:{srcs}</div>" if srcs else "") + "</div>")


def _context_item(c: dict) -> str:
    why = f" <span class='sub'>— {_e(c.get('why_relevant'))}</span>" if c.get("why_relevant") else ""
    return f"<li><span class='sub'>{_e(c.get('when'))}</span> {_e(c['what'])}{why}{_link(c.get('source', ''))}</li>"


def _daily_theater(t: dict) -> str:
    temp, esc = t["temperature"], t["escalation"]
    pulses = "".join(f"<tr><td>{_e(p['name'])}</td><td>{_num(p['position'])}</td><td>{_e(p['band'])}</td>"
                     f"<td>{_num(p['change_24h'], True)}</td><td>{_num(p['change_7d'], True)}</td></tr>"
                     for p in t["pulses"])
    since = "".join(f"<li><span class='pill {_CHANGE.get(c['kind'], 'steady')}'>{_e(c['kind'])}</span>{_e(c['what'])}</li>"
                    for c in t["since_yesterday"])
    ctx = "".join(_context_item(c) for c in t["context"])
    watch = "".join(f"<li>{_e(w)}</li>" for w in t["watch_next"])
    brief = f"<div class='sub'>Deep brief: {_e(t['brief_slug'])}</div>" if t.get("brief_slug") else ""
    return (f"<h2>{_e(t['name'])}</h2><div class='card bluf'>{_e(t['bottom_line'])}</div>"
            f"<div><span class='pill {esc['direction']}'>{_e(esc['direction'])}</span>"
            f"<span class='pill steady'>pace: {_e(esc['pace'])}</span>"
            f"<span class='pill steady'>{_e(temp['trend'])} · {temp['recent_share'] * 100:.0f}% of coverage "
            f"(was {temp['prior_share'] * 100:.0f}%)</span></div>"
            + (f"<h2>Since yesterday</h2><ul>{since}</ul>" if since else "")
            + "".join(_development(d) for d in t["developments"])
            + (f"<h2>Context</h2><ul>{ctx}</ul>" if ctx else "")
            + ("<h2>Pulses</h2><table><tr><th>Pulse</th><th>Now</th><th>Band</th><th>24h</th><th>7d</th></tr>"
               f"{pulses}</table>" if pulses else "")
            + (f"<h2>Outlook</h2><div>{_e(t['outlook'])}</div>" if t.get("outlook") else "")
            + (f"<h2>Watch next</h2><ul>{watch}</ul>" if watch else "") + brief)


def render_daily(record: dict) -> str:
    """The daily report as a self-contained page (operator preview; the site renders the JSON itself)."""
    bullets = "".join(f"<li>{_e(b)}</li>" for b in record["summary"]["the_day"])
    cross = "".join(f"<li><b>{_e(' ↔ '.join(c['theaters']))}</b>: {_e(c['link'])}</li>" for c in record["cross_theater"])
    body = (f"<div class='sub'>Daily report · {_e(record['domain'])} · {_e(record['date'])}</div>"
            f"<h1>{_e(record['summary']['headline'])}</h1>"
            + (f"<div class='card'><ul>{bullets}</ul></div>" if bullets else "")
            + (f"<h2>Across theaters</h2><ul>{cross}</ul>" if cross else "")
            + "".join(_daily_theater(t) for t in record["theaters"])
            + (f"<h2>Pulses we may be missing</h2><ul>" + "".join(
                f"<li><b>{_e(p['name'])}</b> ({_e(p['theater'])}): {_e(p['question'])} "
                f"<span class='sub'>{_e(p['low_end'])} → {_e(p['high_end'])}. {_e(p['why'])}</span></li>"
                for p in record["pulse_proposals"]) + "</ul>" if record["pulse_proposals"] else "")
            + "<div class='note'><span class='pill researched'>researched</span> established by Ohmega's graded "
              "research. <span class='pill reported'>reported</span> other outlets' reporting, not verified by us. "
              "Outlooks are Ohmega's judgment in estimative language, not a guarantee.</div>")
    return _page(f"Daily report — {record['domain']} — {record['date']}", body)
