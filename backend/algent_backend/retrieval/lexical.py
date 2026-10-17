"""BM25 over ``Doc`` rows, in process. Titles count double (a section's name is its strongest topic signal)."""

from __future__ import annotations

import math
import re
from collections import Counter

from . import flags
from .docs import Doc

_TOKEN = re.compile(r"[a-z0-9]{3,}")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


class BM25:
    def __init__(self, docs: list[Doc]) -> None:
        self.tf = [Counter(tokens(d.title) * 2 + tokens(d.text)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df: Counter[str] = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = [t for t in set(tokens(query)) if t in self.idf]
        k1, b = flags.BM25_K1, flags.BM25_B
        out = []
        for c, ln in zip(self.tf, self.len):
            s = 0.0
            for t in q:
                f = c.get(t, 0)
                if f:
                    s += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * ln / self.avg))
            out.append(s)
        return out
