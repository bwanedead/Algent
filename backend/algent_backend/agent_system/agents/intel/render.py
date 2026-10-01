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
                   f"</span></td><td>{_e(i.signal)}</td><td class='sub'>{_e(i.meaning)}</td></tr>" for i in brief.indicators)
    body = (
        f"<div class='sub'>Intelligence brief · {_e(theater_name)} · as of {_e(as_of)}</div><h1>{_e(brief.title)}</h1>"
        f"<div class='card bluf'>{_e(brief.bottom_line)}</div>"
        f"<div class='card'><span class='pill {esc.direction}'>{_e(esc.direction)}</span>"
        f"<span class='pill steady'>pace: {_e(esc.pace)}</span>"
        f"<span class='pill steady'>{heat.get('recent', 0)} headlines in 3 days · {_e(heat.get('trend'))}</span>"
        f"<div style='margin-top:8px'>{_e(esc.assessment)}</div></div>"
        f"<h2>Where things stand</h2><div>{_e(brief.situation)}</div>"
        + (f"<h2>Who is doing what to whom</h2><div class='card'>{actors_svg(brief)}</div>" if brief.relations else "")
        + (f"<h2>Timeline</h2><table><tr><th>Date</th><th>Event</th><th>Actors</th></tr>{tl}</table>" if tl else "")
        + (f"<h2>What follows</h2><ul>{effects(brief.second_order)}</ul>" if brief.second_order else "")
        + (f"<h2>Watch the periphery</h2><ul>{effects(brief.peripheral)}</ul>" if brief.peripheral else "")
        + (f"<h2>Indicators &amp; warnings</h2><table><tr><th>Status</th><th>Signal</th><th>What it would mean</th></tr>{inds}</table>" if inds else "")
        + (f"<h2>What we do not know</h2><ul>{''.join(f'<li>{_e(u)}</li>' for u in brief.unknowns)}</ul>" if brief.unknowns else "")
        + "<div class='note'><span class='pill researched'>researched</span> established by Ohmega's graded research. "
          "<span class='pill reported'>reported</span> other outlets' reporting, not verified by us. "
          "Assessments use estimative language and are Ohmega's judgment, not a guarantee.</div>")
    return _page(brief.title, body)
