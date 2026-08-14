"""What an insight figure is, before anyone draws it."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Form = Literal["takeaway_bars", "takeaway_line", "growing_line_gif"]
Verdict = Literal["ship", "fix", "abandon"]


class InsightSpec(BaseModel):
    """One figure. ``takeaway`` is the title on the chart and the first line of the tweet."""

    beat: str = "world"
    form: Form = "takeaway_bars"
    takeaway: str = ""
    question: str = ""
    unit: str = ""
    highlight: str = ""
    x_key: str = "x"
    series: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
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
    verdict: Verdict = "abandon"
    reason: str = ""
    takeaway: str = ""
    highlight: str = ""
    form: Form | None = None


def spec_key(spec: InsightSpec) -> str:
    """Identity across composes: same beat + day + takeaway is one post."""
    take = " ".join((spec.takeaway or "").casefold().split())
    return f"{spec.beat}:{spec.as_of}:{take}"


def draw_payload(spec: InsightSpec, out: str) -> dict[str, Any]:
    return {
        "form": spec.form,
        "title": spec.takeaway,
        "unit": spec.unit,
        "highlight": spec.highlight,
        "x_key": spec.x_key,
        "series": spec.series,
        "rows": spec.rows,
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
    if critique.form:
        data["form"] = critique.form
    return InsightSpec.model_validate(data)
