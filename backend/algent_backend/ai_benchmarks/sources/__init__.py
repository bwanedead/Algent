"""
Benchmark sources — one module per free provider.

Each module has a pure ``parse(...) -> Harvest`` (tested against captured fixtures) and ``fetch() -> Harvest`` (the only network path, through
``algent_backend.polite_http``). A parser that no longer recognises its source's format raises ``ValueError``: the collector records that as a
broken source and appends nothing, rather than silently reading half a table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..contracts import Benchmark, Result


@dataclass
class Harvest:
    benchmarks: list[Benchmark] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)      # parts of the source that could not be read (reported, not fatal)


def registry() -> dict[str, Callable[[], Harvest]]:
    """source id -> fetch. Imported lazily so a missing optional dependency in one source cannot stop the others loading."""
    from . import epoch, lmarena, swebench

    return {"epoch": epoch.fetch, "swebench": swebench.fetch, "lmarena": lmarena.fetch}


#: Human description of each source for the site and the doc: (display name, page, licence).
INFO: dict[str, tuple[str, str, str]] = {
    "epoch": ("Epoch AI Benchmarking Hub", "https://epoch.ai/benchmarks", "CC BY 4.0, credit Epoch AI"),
    "swebench": ("SWE-bench leaderboards", "https://www.swebench.com", "public GitHub data; credit SWE-bench"),
    "lmarena": ("LMArena", "https://lmarena.ai/leaderboard", "CC BY 4.0 dataset (lmarena-ai/leaderboard-dataset on Hugging Face)"),
    "self_reported": ("Lab-claimed (blogs and model cards)", "", "claims by the lab, unverified; extracted by one capped model call a day"),
}
