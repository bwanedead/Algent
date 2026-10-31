"""
Wikitext helpers for the elections feed: clean a cell (the same style as ``lookahead/sources/elections.py``, but keeping the text of wrapper templates such
as ``{{small|..}}``), find the tables of a page with the section heading above each, and expand a table into a grid with ``rowspan`` / ``colspan`` applied.

Tolerant by construction: a malformed row yields fewer cells, never an exception; callers keep the cleaned cells when they cannot interpret a row.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

_REF = re.compile(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>|<!--.*?-->", re.S)
_FILE = re.compile(r"\[\[(?:File|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", re.I)
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_EXT = re.compile(r"\[(?:https?:)?//\S+\s*([^\]]*)\]")
_WRAP = re.compile(r"\{\{\s*(small|smaller|nowrap|nobr|big|abbr|sort|sortname|nts|hs|center|font[^|}]*|color[^|}]*)\s*\|([^{}]*)\}\}", re.I)
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_HEADING = re.compile(r"^(=+)\s*(.*?)\s*=+\s*$")
_ATTR = {"rowspan": re.compile(r"rowspan\s*=\s*[\"']?(\d+)", re.I), "colspan": re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.I)}


def _unwrap(m: re.Match[str]) -> str:
    parts = m.group(2).split("|")
    return parts[-1] if m.group(1).lower() in ("sort", "sortname") else parts[0]


def clean(text: str) -> str:
    """Plain text of a cell: references, files, templates and markup dropped, link labels kept, white space collapsed."""
    text = _REF.sub("", text or "")
    text = _FILE.sub("", text)
    for _ in range(3):                                           # templates nest: {{small|{{nowrap|12.3}}}}
        text = _WRAP.sub(_unwrap, text)
    text = _TEMPLATE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _EXT.sub(r"\1", text).replace("'''", "").replace("''", "")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace(" ", " ").replace("−", "-")
    return " ".join(text.split())


@dataclass
class Cell:
    raw: str
    header: bool = False
    text: str = ""
    rowspan: int = 1
    colspan: int = 1


@dataclass
class Table:
    heading: str
    text: str
    start: int
    end: int
    caption: str = ""
    rows: list[list[Cell]] = field(default_factory=list)


def _top_level_split(s: str, sep: str) -> list[str]:
    """Split ``s`` on ``sep`` outside [[..]] and {{..}}."""
    out, buf, depth, i = [], [], 0, 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("[[", "{{"):
            depth += 1
            buf.append(two)
            i += 2
        elif two in ("]]", "}}"):
            depth = max(0, depth - 1)
            buf.append(two)
            i += 2
        elif depth == 0 and s.startswith(sep, i):
            out.append("".join(buf))
            buf = []
            i += len(sep)
        else:
            buf.append(s[i])
            i += 1
    out.append("".join(buf))
    return out


def _finish(cell: Cell) -> Cell:
    """Separate a cell's attributes (``style=".." | content``) from its content and read its spans."""
    parts = _top_level_split(cell.raw, "|")
    attrs, content = (parts[0], "|".join(parts[1:])) if len(parts) > 1 and "=" in parts[0] and "[[" not in parts[0] else ("", cell.raw)
    cell.text = clean(content)
    for name, pat in _ATTR.items():
        m = pat.search(attrs)
        if m:
            setattr(cell, name, max(1, min(int(m.group(1)), 40)))
    return cell


def tables(wikitext: str) -> list[Table]:
    """Every top-level table with the heading of the section it sits in (its caption, when it has one, is on ``caption``)."""
    out: list[Table] = []
    heading, depth, buf, start, pos = "", 0, [], 0, 0
    for line in wikitext.splitlines(keepends=True):
        s = line.strip()
        if depth == 0 and (m := _HEADING.match(s)):
            heading = clean(m.group(2))
        if s.startswith("{|"):
            if depth == 0:
                buf, start = [], pos
            depth += 1
        if depth:
            buf.append(line)
        if s.startswith("|}") and depth:
            depth -= 1
            if depth == 0:
                out.append(Table(heading, "".join(buf), start, pos + len(line)))
        pos += len(line)
    for t in out:
        t.rows, t.caption = _rows(t.text)
    return out


def _rows(table_text: str) -> tuple[list[list[Cell]], str]:
    rows: list[list[Cell]] = []
    cur: list[Cell] | None = None
    caption, nested = "", 0
    for line in table_text.splitlines()[1:]:
        s = line.strip()
        if s.startswith("{|"):
            nested += 1
        if nested:
            if s.startswith("|}"):
                nested -= 1
            continue                                           # a table inside a cell: not read
        if s.startswith("|}"):
            break
        if s.startswith("|+"):
            caption = clean(s[2:])
        elif s.startswith("|-"):
            cur = []
            rows.append(cur)
        elif s[:1] in ("|", "!"):
            if cur is None:
                cur = []
                rows.append(cur)
            header = s[0] == "!"
            seps = ["||", "!!"] if header else ["||"]
            parts = [s[1:]]
            for sep in seps:
                parts = [p for chunk in parts for p in _top_level_split(chunk, sep)]
            cur.extend(Cell(p, header) for p in parts)
        elif cur:
            cur[-1].raw += "\n" + line                          # a cell's content continued on the next line
    return [[_finish(c) for c in r] for r in rows if r], caption


def grid(rows: list[list[Cell]]) -> list[list[Cell]]:
    """The rows with ``rowspan`` / ``colspan`` expanded, so column ``i`` of every row is the same column."""
    carry: dict[int, tuple[Cell, int]] = {}
    out: list[list[Cell]] = []
    blank = Cell("", False, "")
    for row in rows:
        line: list[Cell] = []
        col, i = 0, 0
        while i < len(row) or any(k >= col for k in carry):
            if col in carry:
                cell, left = carry.pop(col)
                line.append(cell)
                if left > 1:
                    carry[col] = (cell, left - 1)
            elif i < len(row):
                cell = row[i]
                i += 1
                for k in range(cell.colspan):
                    line.append(cell)
                    if cell.rowspan > 1:
                        carry[col + k] = (cell, cell.rowspan - 1)
                col += cell.colspan
                continue
            else:
                line.append(blank)
            col += 1
        out.append(line)
    return out


def header_rows(g: list[list[Cell]]) -> int:
    """How many leading rows are headers: those made only of ``!`` cells (else the first row)."""
    n = 0
    for r in g:
        if r and all(c.header for c in r):
            n += 1
        else:
            break
    return n or 1


def column_names(g: list[list[Cell]], n: int) -> list[str]:
    """One name per column from the ``n`` header rows: the distinct texts down the column, joined ("Seats Total")."""
    width = max((len(r) for r in g[:n]), default=0)
    names = []
    for i in range(width):
        seen: list[str] = []
        for r in g[:n]:
            t = r[i].text if i < len(r) else ""
            if t and t not in seen:
                seen.append(t)
        names.append(" ".join(seen))
    return names
