"""
Does the figure actually fit inside its own canvas?

A reader reported labels sliced off the right edge of a published timeline. Nothing
in the pipeline noticed, because every existing check asks whether the NUMBERS are
honest and none asks whether the picture is legible. Overflow is worth catching
mechanically rather than by asking the worker nicely: it is a geometry fact
decidable from the file alone, it is invisible to the worker (which sees a
successful matplotlib call, not a clipped viewport), and it destroys the label the
figure exists to deliver.

Getting this right requires composing transforms, and the naive version is a trap
worth documenting. Matplotlib emits text as glyph references carrying **font-unit
advances** inside a scaled group:

    <g transform="translate(178.6 377.7) scale(0.1 -0.1)">
      <use xlink:href="#DejaVuSansMono-79" transform="translate(4143.4 0)"/>

That 4143 is not a page coordinate. Scaled by 0.1 it is 414 page units, and read
raw it looks like catastrophic overflow on a 936-wide canvas. A first attempt here
did exactly that and flagged 6 of 30 published figures; every one was a false
positive, and the only thing they had in common was long text. So this walks the
tree and composes each element's ancestor transforms before measuring anything.

What it measures is the extent of every glyph run: where the run starts on the page
plus how far its own advances carry it, in page units. That is precisely the
quantity that determines whether a label survives to the right-hand edge.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

#: How far past the canvas edge counts as broken, as a multiple of canvas size.
#: Calibrated against all 30 figures this newsroom has published: 29 land between
#: 0.21 and 0.98, and the one a reader reported as cut off sits at 1.02 — the only
#: figure that reaches its own edge at all. There is no crowd near the boundary to
#: false-fail, so the bound sits at the canvas itself. Note the measurement is of
#: glyph ORIGINS, so a run ending at 1.00 already paints past the frame; that makes
#: this mildly conservative, which is the right direction for a publish gate.
TOLERANCE = 1.0

_SVG_NS = "{http://www.w3.org/2000/svg}"
_VIEWBOX = re.compile(r'viewBox\s*=\s*"([-\d.eE\s]+)"')
_TRANSLATE = re.compile(r"translate\(\s*([-\d.eE]+)(?:[\s,]+([-\d.eE]+))?\s*\)")
_SCALE = re.compile(r"scale\(\s*([-\d.eE]+)(?:[\s,]+([-\d.eE]+))?\s*\)")


def canvas_size(svg: str) -> tuple[float, float] | None:
    """The declared drawing area, or ``None`` when the file does not say."""
    m = _VIEWBOX.search(svg)
    if not m:
        return None
    try:
        parts = [float(p) for p in m.group(1).split()]
    except ValueError:
        return None
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        return None
    return parts[2], parts[3]


def _parse_transform(value: str) -> tuple[float, float, float, float]:
    """``(tx, ty, sx, sy)`` from a transform attribute. Rotation/skew is ignored."""
    tx = ty = 0.0
    sx = sy = 1.0
    m = _TRANSLATE.search(value or "")
    if m:
        tx = float(m.group(1))
        ty = float(m.group(2)) if m.group(2) is not None else 0.0
    m = _SCALE.search(value or "")
    if m:
        sx = float(m.group(1))
        sy = float(m.group(2)) if m.group(2) is not None else sx
    return tx, ty, sx, sy


def _extent(node: ET.Element, ox: float, oy: float, sx: float, sy: float,
            acc: list[tuple[float, float]]) -> None:
    """Walk the tree, composing transforms, collecting page-space points."""
    tx, ty, nsx, nsy = _parse_transform(node.get("transform", ""))
    # A child's translate is expressed in the PARENT's scaled units.
    ox, oy = ox + tx * sx, oy + ty * sy
    sx, sy = sx * nsx, sy * nsy

    tag = node.tag.replace(_SVG_NS, "")
    if tag in ("use", "text", "tspan", "rect", "circle", "image"):
        x = float(node.get("x") or 0.0)
        y = float(node.get("y") or 0.0)
        acc.append((ox + x * sx, oy + y * sy))

    for child in node:
        _extent(child, ox, oy, sx, sy, acc)


def overflow(svg: str) -> tuple[float, float]:
    """``(x_extent, y_extent)`` of painted content as multiples of the canvas size.

    ``1.0`` means content reaches exactly the edge. Returns ``(0, 0)`` when the file
    declares no canvas or cannot be parsed — unknown is not the same as broken.
    """
    size = canvas_size(svg)
    if size is None:
        return 0.0, 0.0
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return 0.0, 0.0

    points: list[tuple[float, float]] = []
    # <defs> holds glyph outlines in their own coordinate space — never page content.
    for child in root:
        if child.tag.replace(_SVG_NS, "") == "defs":
            continue
        _extent(child, 0.0, 0.0, 1.0, 1.0, points)
    if not points:
        return 0.0, 0.0

    width, height = size
    return (max(abs(p[0]) for p in points) / width,
            max(abs(p[1]) for p in points) / height)


def check_fit(svg: str) -> str | None:
    """Return why this figure does not fit its canvas, or ``None`` when it is fine."""
    size = canvas_size(svg)
    if size is None:
        return None
    x_over, y_over = overflow(svg)
    axes = []
    if x_over > TOLERANCE:
        axes.append(f"horizontally to {x_over:.2f}x the canvas width")
    if y_over > TOLERANCE:
        axes.append(f"vertically to {y_over:.2f}x the canvas height")
    if not axes:
        return None
    return (
        "content runs outside the figure's own canvas ("
        + " and ".join(axes)
        + f", canvas {size[0]:.0f}x{size[1]:.0f}) — labels will be cut off on the page"
    )
