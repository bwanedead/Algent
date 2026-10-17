"""
LMArena — human-preference Elo ratings, from the project's public Hugging Face dataset (CC BY 4.0) through the dataset-viewer JSON API.

The ``latest`` split of each config is the current leaderboard (one row per model per category, stamped with the day the board was
published). We keep the ``overall`` category and append a row per model per publish, so the history is built FORWARD from the first capture:
the ``full`` split is 1.2 M rows (a parquet download, which needs pyarrow) and is deliberately not backfilled here. Ratings are open-ended
(no ceiling); the unit is ``elo``.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, datetime

from .. import flags
from ..contracts import Benchmark, Result, slug
from ..labs import lab_of
from . import Harvest

API = "https://datasets-server.huggingface.co/filter"
DATASET = "lmarena-ai/leaderboard-dataset"
PAGE = "https://lmarena.ai/leaderboard"
SOURCE = "lmarena"
PAGE_ROWS = 100
MAX_PAGES = 20


def parse(config: str, name: str, pages: list[str], *, observed_on: str) -> Harvest:
    """``pages`` are the dataset-viewer ``/filter`` responses for one config's overall-category rows."""
    out = Harvest()
    bid = f"lmarena-{slug(config)}"
    for text in pages:
        try:
            rows = json.loads(text)["rows"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"lmarena {config}: not the dataset-viewer shape: {exc}") from exc
        for item in rows:
            r = item.get("row", {})
            rating, model, date = r.get("rating"), r.get("model_name"), str(r.get("leaderboard_publish_date") or "")[:10]
            if not isinstance(rating, (int, float)) or not model or not date:
                continue
            lab, lab_name = lab_of(str(r.get("organization") or ""))
            licence = str(r.get("license") or "")
            out.results.append(Result(benchmark=bid, model=str(model), model_id=str(model), lab=lab, lab_name=lab_name, score=round(float(rating), 2),
                                      date=date, weights=("closed" if licence.lower() == "proprietary" else "open") if licence else "unknown",
                                      source=SOURCE, url=PAGE, observed_on=observed_on,
                                      note=f"{int(r['vote_count'])} votes" if isinstance(r.get("vote_count"), (int, float)) else ""))
    if out.results:
        out.benchmarks.append(Benchmark(id=bid, name=name, source=SOURCE, source_url=PAGE, unit="elo",
                                        released=min(r.date for r in out.results)))
    return out


RETRY_WAIT_S = 20.0
RETRY_ROUNDS = 3


def _get(url: str) -> str:
    """The dataset viewer answers HTTP 500 "index is loading" for tens of seconds after it was idle; a patient retry gets the page."""
    import time

    from algent_backend import polite_http

    for round_ in range(RETRY_ROUNDS):
        try:
            return polite_http.get(url)
        except polite_http.SourceError:
            if round_ == RETRY_ROUNDS - 1:
                raise
            time.sleep(RETRY_WAIT_S)
    raise AssertionError("unreachable")


def _pages(config: str) -> list[str]:
    pages, offset = [], 0
    for _ in range(MAX_PAGES):
        query = {"dataset": DATASET, "config": config, "split": "latest", "where": f"\"category\"='{flags.LMARENA_CATEGORY}'",
                 "offset": offset, "length": PAGE_ROWS}
        text = _get(f"{API}?{urllib.parse.urlencode(query)}")
        pages.append(text)
        offset += PAGE_ROWS
        if offset >= int(json.loads(text).get("num_rows_total", 0)):
            break
    return pages


def fetch() -> Harvest:
    observed = datetime.now(UTC).date().isoformat()
    out = Harvest()
    for config, name in flags.LMARENA_CONFIGS:
        try:
            part = parse(config, name, _pages(config), observed_on=observed)
        except Exception as exc:  # noqa: BLE001 - one config down must not hide the others
            out.problems.append(f"{config}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        out.benchmarks += part.benchmarks
        out.results += part.results
    if not out.results:
        raise ValueError(f"lmarena: no config could be read: {out.problems}")
    return out
