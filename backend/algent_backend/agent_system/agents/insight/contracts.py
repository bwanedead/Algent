"""What an insight figure is, before anyone draws it."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Form = Literal["takeaway_bars", "takeaway_line", "growing_line_gif"]
Verdict = Literal["ship", "fix", "abandon"]

# Muse structured output requires additionalProperties: false on every object.
# Open dict rows were rejected (400) and the daemon retried every tick.
_CLOSED = ConfigDict(extra="forbid")


class InsightRow(BaseModel):
    """One plotted observation. Bars: label+value. Lines: x plus y/y2/y3."""

    model_config = _CLOSED
    label: str = ""
    value: float | None = None
    x: str = ""
    y: float | None = None
    y2: float | None = None
    y3: float | None = None


class InsightSpec(BaseModel):
    """One figure. ``takeaway`` is the title on the chart and the first line of the tweet."""

    model_config = _CLOSED
    beat: str = "world"
    form: Form = "takeaway_bars"
    takeaway: str = ""
    question: str = ""
    unit: str = ""
    highlight: str = ""
    x_key: str = "x"
    series: list[str] = Field(default_factory=list)
    rows: list[InsightRow] = Field(default_factory=list)
    source_name: str = ""
    source_url: str = ""
    as_of: str = ""
    callout: str = ""
    note: str = ""
    warranted: bool = True

    @field_validator("beat", mode="before")
    @classmethod
    def _slug_beat(cls, value: object) -> str:
        raw = str(value or "world")
        slug = re.sub(r"[^a-z0-9_]+", "_", raw.casefold()).strip("_")
        return slug or "world"


class Critique(BaseModel):
    model_config = _CLOSED
    verdict: Verdict = "abandon"
    reason: str = ""
    takeaway: str = ""
    highlight: str = ""
    form: str = ""


def spec_key(spec: InsightSpec) -> str:
    """Identity across composes: same beat + day + takeaway is one post."""
    take = " ".join((spec.takeaway or "").casefold().split())
    return f"{spec.beat}:{spec.as_of}:{take}"


def draw_rows(spec: InsightSpec) -> list[dict[str, Any]]:
    """Closed rows → the dicts ``lib.insight`` templates already draw.

    Critique may change the form without rewriting cells, so bars also accept
    x/y and lines also accept label/value.
    """
    if spec.form == "takeaway_bars":
        out: list[dict[str, Any]] = []
        for r in spec.rows:
            val = r.value if r.value is not None else r.y
            if val is None:
                val = r.y2 if r.y2 is not None else r.y3
            out.append({"label": (r.label or r.x).strip(), "value": val})
        return out
    names = list(spec.series)
    out = []
    for r in spec.rows:
        row: dict[str, Any] = {spec.x_key: r.x or r.label}
        ys = (r.y, r.y2, r.y3)
        if names:
            for name, val in zip(names, ys, strict=False):
                if val is not None:
                    row[name] = val
        elif r.value is not None:
            row[r.label or "value"] = r.value
        out.append(row)
    return out


def draw_payload(spec: InsightSpec, out: str) -> dict[str, Any]:
    return {
        "form": spec.form,
        "title": spec.takeaway,
        "unit": spec.unit,
        "highlight": spec.highlight,
        "x_key": spec.x_key,
        "series": spec.series,
        "rows": draw_rows(spec),
        "source": spec.source_name,
        "as_of": spec.as_of,
        "callout": spec.callout,
        "out": out,
    }


def apply_critique(spec: InsightSpec, critique: Critique) -> InsightSpec:
    data = spec.model_dump()
    if critique.takeaway:
        data["takeaway"] = critique.takeaway
    if critique.highlight:
        data["highlight"] = critique.highlight
    if critique.form in ("takeaway_bars", "takeaway_line", "growing_line_gif"):
        data["form"] = critique.form
    return InsightSpec.model_validate(data)
