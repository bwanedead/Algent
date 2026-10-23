"""The theme rule lives once, in views/themes.py, and mirrors lib/visual.ts categoryOf (which components still use for glyphs and tints). The two regex tables must not drift:
this compares them as text. The globe's THEMES order (legend and tie-break) is compared with lib/globe/themes.ts the same way."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.views import themes

LIB = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster" / "lib"


def _ts_rules() -> list[tuple[str, str]]:
    src = (LIB / "visual.ts").read_text(encoding="utf-8")
    block = src[src.index("const RULES"): src.index("/** The category a theater")]
    return re.findall(r'\["(\w+)", /(.+)/i\]', block)


def test_category_rules_equal_the_sites_visual_ts():
    ours = [(name, rx.pattern) for name, rx in themes._CATEGORY_RULES]          # noqa: SLF001 - the table under test
    assert ours == _ts_rules()


def test_theme_order_equals_the_sites_legend_order():
    src = (LIB / "globe" / "themes.ts").read_text(encoding="utf-8")
    block = src[src.index("export const THEMES"): src.index("/** Recency band")]
    assert tuple(re.findall(r'id: "(\w+)"', block)) == themes.THEMES
