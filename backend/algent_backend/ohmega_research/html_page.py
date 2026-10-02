"""HTML primitives and the base stylesheet shared by the standalone Ohmega Research reports.

The pages load nothing external. ``escape`` covers every input-derived string, and
``script_json`` makes embedded JSON unable to close its script element. Page-specific
markup, styles and scripts stay with each report.
"""

from __future__ import annotations

import html
import json


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def script_json(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False)
    for char, code in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                       ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(char, code)
    return text


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def format_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def table(header: tuple[str, ...], rows: list[tuple]) -> str:
    """An escaped table inside its own horizontal scroll container."""
    head = "".join(f"<th>{escape(h)}</th>" for h in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(v)}</td>" for v in row) + "</tr>" for row in rows
    )
    return f'<div class="tablewrap"><table><tr>{head}</tr>{body}</table></div>'


# Page frame, KPIs, tables, details and the 0-100% interval scale (.scale/.ci/.pt.conf).
CSS = """
:root{--ink:#1d1f21;--muted:#6b7075;--rule:#e3e5e8;--soft:#f5f6f8}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink)}
main{max-width:1200px;margin:0 auto;padding:24px 20px 64px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:18px;margin:36px 0 6px}
h3{font-size:15px;margin:24px 0 6px}h4{font-size:13px;margin:12px 0 4px}
.muted{color:var(--muted)}
.kpis{display:flex;gap:32px;flex-wrap:wrap;margin:8px 0}.kpi b{display:block;font-size:22px}
.tablewrap{max-width:100%;overflow-x:auto}
.scale{position:relative;display:block;height:14px;border-left:1px solid var(--rule);
border-right:1px solid var(--rule);background:linear-gradient(90deg,transparent 49.8%,
var(--rule) 49.8%,var(--rule) 50.2%,transparent 50.2%)}
.ci{position:absolute;top:6px;height:2px;background:var(--ink)}
.pt{position:absolute;top:2px;width:10px;height:10px;margin-left:-5px;border-radius:50%}
.pt.conf{background:var(--ink)}
details>summary{cursor:pointer}details[open]>summary{background:var(--soft)}
table{border-collapse:collapse;font-size:13px;margin:4px 0}
td,th{padding:3px 12px 3px 0;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
td,code{overflow-wrap:anywhere}th{white-space:nowrap}
code{font-size:12px}
@media (max-width:760px){main{padding:16px 12px 48px}.kpis{gap:12px 20px}}
"""
