"""
The three list providers. Each module has ``URL``, a pure ``parse(path) -> dict[ref, Entry]`` (streams the XML file so a
30 MB list never sits in memory as text) and ``fetch(workdir)`` that downloads the file and parses it. Terms: all three are
official public-sector lists published for reuse (see ``docs/architecture/sanctions-calendar.md``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET


def local(tag: str) -> str:
    """An XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def elements(path: Path, name: str) -> Iterator[ET.Element]:
    """Every ``name`` element of the file, cleared after use so memory stays flat."""
    for _ev, el in ET.iterparse(str(path), events=("end",)):
        if local(el.tag) == name:
            yield el
            el.clear()


def child(el: ET.Element, name: str) -> str:
    """Text of the first direct child called ``name`` ('' when absent)."""
    for c in el:
        if local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def descendants(el: ET.Element, name: str) -> list[str]:
    """Non-empty texts of every descendant called ``name``."""
    return [(d.text or "").strip() for d in el.iter() if local(d.tag) == name and (d.text or "").strip()]
