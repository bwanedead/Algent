"""
AI benchmark contracts — what a benchmark is and what one reported score is.

``Benchmark`` is catalog metadata learned from a source; ``Result`` is one model's score on one benchmark with its provenance. Both are
plain data: collectors produce them, the store appends them, ``derive`` reads them. ``verification`` keeps independently MEASURED scores
(a leaderboard ran or collected them) apart from SELF_REPORTED ones (a lab's own blog or model card): the two never mix in a frontier.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel

Weights = Literal["open", "closed", "unknown"]
Verification = Literal["measured", "self_reported"]


class Benchmark(BaseModel):
    id: str                          # stable slug, also the key results refer to
    name: str                        # reader-facing
    source: str                      # collector id ("epoch", "swebench", "lmarena", "self_reported")
    source_url: str                  # human page to cite
    unit: str = "fraction"           # "fraction" (0..1, shown as %), "elo", "points", "minutes", "usd" ...
    ceiling: float | None = None     # best achievable score when the scale is bounded; None = open-ended (Elo, minutes)
    baseline: float | None = None    # random-guess score, when known
    released: str = ""               # YYYY-MM-DD the benchmark appeared, when known
    superseded_by: str = ""          # id of the benchmark that replaced it, when the source says so


class Result(BaseModel):
    benchmark: str                   # Benchmark.id
    model: str                       # reader-facing model name
    model_id: str                    # the source's own identifier (keeps reasoning-effort variants apart)
    lab: str                         # canonical lab id (``labs.lab_of``)
    lab_name: str
    score: float                     # in the benchmark's unit (fractions for bounded scales)
    date: str                        # YYYY-MM-DD the model was released / the leaderboard published it: the chart's x axis
    weights: Weights = "unknown"
    verification: Verification = "measured"
    source: str = ""                 # collector id
    url: str = ""                    # where the score can be checked
    observed_on: str = ""            # YYYY-MM-DD we first saw it (forward capture is certain even where `date` is not)
    revised: bool = False            # True when this line replaced an earlier score for the same key
    note: str = ""

    @property
    def key(self) -> str:
        """Identity of a score: same benchmark, model variant, verification, source and date = the same fact (a changed score is a revision)."""
        raw = "|".join((self.benchmark, self.model_id, self.verification, self.source, self.date))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"
