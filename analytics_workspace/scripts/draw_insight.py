"""Draw one insight figure from a JSON spec. Invoked by the insight lane, not by grok-build.

    python scripts/draw_insight.py spec.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.insight import growing_line_gif, takeaway_bars, takeaway_line  # noqa: E402


def draw(spec: dict) -> Path:
    form = spec.get("form") or "takeaway_bars"
    out = Path(spec["out"])
    title = spec.get("title") or spec.get("takeaway") or ""
    unit = spec.get("unit") or ""
    source = spec.get("source") or ""
    as_of = spec.get("as_of") or ""
    rows = spec.get("rows") or []
    if form == "takeaway_bars":
        return takeaway_bars(
            rows, title=title, unit=unit, out=out,
            highlight=spec.get("highlight") or "",
            source=source, as_of=as_of,
        )
    if form == "takeaway_line":
        return takeaway_line(
            rows, title=title, unit=unit, out=out,
            x_key=spec.get("x_key") or "x",
            series=spec.get("series") or [],
            source=source, as_of=as_of,
            callout=spec.get("callout") or "",
        )
    if form == "growing_line_gif":
        return growing_line_gif(
            rows, title=title, unit=unit, out=out,
            x_key=spec.get("x_key") or "x",
            series=spec.get("series") or [],
            source=source, as_of=as_of,
        )
    raise ValueError(f"unknown insight form: {form}")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: draw_insight.py spec.json", file=sys.stderr)
        return 2
    spec = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    path = draw(spec)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
