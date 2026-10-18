"""
SWE-bench leaderboards — the submissions behind swebench.com, published as one JSON file in the project's GitHub repo (public, no key).

``leaderboards.json`` lists each split (Verified, Lite, Multimodal, Multilingual, Test = the full set) with every submitted agent system: its
model, the model's organisation, whether the model/system is open, the date and the percent of issues resolved. A submission is an AGENT plus
a model, so these scores are reported separately from Epoch's own SWE-bench Verified runs (different scaffold, different benchmark id).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ..contracts import Benchmark, Result, slug
from ..labs import lab_of
from . import Harvest

URL = "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json"
PAGE = "https://www.swebench.com"
SOURCE = "swebench"
#: The site's name for the unsuffixed split is "Test"; readers know it as the full benchmark.
DISPLAY = {"Test": "Full"}


def parse(text: str, *, observed_on: str) -> Harvest:
    try:
        boards = json.loads(text)["leaderboards"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"swebench leaderboards.json is not the expected shape: {exc}") from exc
    out = Harvest()
    for board in boards:
        split = str(board.get("name", ""))
        rows = board.get("results")
        if not split or not isinstance(rows, list):
            out.problems.append(f"leaderboard without name/results: {str(board)[:80]}")
            continue
        name = f"SWE-bench {DISPLAY.get(split, split)} (agent submissions)"
        bid = f"swebench-{slug(DISPLAY.get(split, split))}"
        dates = []
        for r in rows:
            resolved, date = r.get("resolved"), str(r.get("date") or "")[:10]
            if not isinstance(resolved, (int, float)) or not date:
                continue
            org = r.get("model_org") or r.get("agent_org") or ""
            lab, lab_name = lab_of(org)
            dates.append(date)
            out.results.append(Result(
                benchmark=bid, model=str(r.get("model_display") or r.get("name") or r.get("folder") or "?"),
                model_id=str(r.get("folder") or r.get("name") or ""), lab=lab, lab_name=lab_name, score=round(float(resolved) / 100.0, 6), date=date,
                weights="open" if r.get("os_model") else "closed", source=SOURCE, url=str(r.get("site") or PAGE), observed_on=observed_on,
                note=f"agent: {r.get('agent', '')}" if r.get("agent") else ""))
        if dates:
            out.benchmarks.append(Benchmark(id=bid, name=name, source=SOURCE, source_url=PAGE, unit="fraction", ceiling=1.0, released=min(dates)))
    if not out.results:
        raise ValueError("swebench: no submission could be read (format changed)")
    return out


def fetch() -> Harvest:
    from algent_backend import polite_http

    return parse(polite_http.get(URL), observed_on=datetime.now(UTC).date().isoformat())
