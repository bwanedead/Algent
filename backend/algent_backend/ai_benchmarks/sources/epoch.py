"""
Epoch AI Benchmarking Hub — the bundle behind epoch.ai/benchmarks (CC BY 4.0, one free zip, no key).

``benchmark_data.zip`` holds ``benchmark_metadata.csv`` (per benchmark: file, score column, scale, ceiling, release date), one CSV per
benchmark (a row per model run, with release date and organisation), ``model_metadata.csv`` (weights accessibility, display names) and the
Epoch Capabilities Index scores. Everything is read from those files; no benchmark or model is named here, except the few files the
metadata does not point at (``SUPPLEMENT``) and one benchmark whose headline number is not the column the metadata names (``OVERRIDES``).

A scale below 1 in the metadata means the column is in percent or tenths (``value * scale`` is the fraction).
"""

from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from pathlib import Path

from .. import flags
from ..contracts import Benchmark, Result, slug
from ..labs import lab_of
from . import Harvest

URL = "https://epoch.ai/data/benchmark_data.zip"
PAGE = "https://epoch.ai/benchmarks"
SOURCE = "epoch"

#: Benchmarks the metadata lists without a file: name -> (file, score column, scale, bounded). The metadata still supplies baseline,
#: ceiling and release date; ``bounded=False`` marks an open-ended scale (Elo, dollars, speed-ups) that has no ceiling.
SUPPLEMENT: dict[str, tuple[str, str, float, bool]] = {
    "CursorBench": ("cursorbench_external.csv", "Score", 1.0, True),
    "GBAEval": ("gbaeval_external.csv", "Overall score", 1.0, True),
    "CritPt": ("critpt_external.csv", "Accuracy", 1.0, True),
    "BoolQ": ("bool_q_external.csv", "Score", 1.0, True),
    "CSQA2": ("common_sense_qa_2_external.csv", "Score", 1.0, True),
    "LiveBench": ("live_bench_external.csv", "Global average", 0.01, True),
    "VideoMME": ("video_mme_external.csv", "Overall (no subtitles)", 1.0, True),
    "FrontierMath-Erdos": ("frontiermath_erdos.csv", "Best score (across scorers)", 1.0, True),
    "GDP.pdf": ("gdp_pdf_external.csv", "GDP.pdf score", 1.0, True),
    "SciCode": ("scicode_external.csv", "Score", 1.0, True),
    "Blueprint-Bench 2": ("blueprint_bench_2_external.csv", "Score", 1.0, True),
    "MindCube": ("mindcube_external.csv", "Overall score", 1.0, True),
    "SpatialViz-Bench": ("spatialviz_bench_external.csv", "Overall score", 1.0, True),
    "EnigmaEval": ("enigma_eval_external.csv", "Accuracy", 1.0, True),
    "WeirdML v3": ("weirdml_v3_external.csv", "Score", 1.0, True),
    "SpireClimb (Slay the Spire 1, Ascension 20 Heart)": ("spireclimb_sts1_a20_heart.csv", "Best score (across scorers)", 1.0, True),
    "SpireClimb (Slay the Spire 2, Ascension 10)": ("spireclimb_sts2_a10.csv", "Best score (across scorers)", 1.0, True),
    "WebDev Arena": ("webdev_arena_external.csv", "Arena Score", 1.0, False),
    "AlgoTune": ("algotune_external.csv", "Score", 1.0, False),
    "ALE-Bench": ("ale_bench_external.csv", "Performance", 1.0, False),
    "Vending-Bench 2": ("vending_bench_2_external.csv", "Score", 1.0, False),
    "ForecastBench": ("forecastbench_external.csv", "Overall score", 1.0, False),
}
#: Benchmarks whose headline number is a different column or unit than the metadata's: name -> (column, unit, bounded). METR's metadata names
#: its success rate; the quantity people chart is the task length (minutes) at which a model succeeds half the time.
OVERRIDES: dict[str, tuple[str, str, bool]] = {"METR Time Horizons": ("Time horizon", "minutes", False)}

_UNIT = {True: "fraction", False: "points"}


def _num(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def weights_of(accessibility: str) -> str:
    a = (accessibility or "").strip().lower()
    if a.startswith("open weights"):
        return "open"
    return "closed" if a else "unknown"


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _model_meta(text: str) -> dict[str, dict[str, str]]:
    return {r["model_version"]: r for r in _rows(text) if r.get("model_version")}


def parse(files: dict[str, str], *, observed_on: str) -> Harvest:
    """Every benchmark in the bundle -> a catalog entry plus one Result per model run. ``files`` maps the zip's file names to their text."""
    if "benchmark_metadata.csv" not in files:
        raise ValueError("epoch bundle has no benchmark_metadata.csv (format changed)")
    meta = _rows(files["benchmark_metadata.csv"])
    if not meta or "benchmark" not in meta[0] or "score_column" not in meta[0]:
        raise ValueError("epoch benchmark_metadata.csv lost its columns (format changed)")
    models = _model_meta(files.get("model_metadata.csv", ""))
    out = Harvest()
    attempted = 0
    for m in meta:
        name = m["benchmark"]
        file, column, scale, bounded = m.get("source_file", ""), m.get("score_column", ""), _num(m.get("scale")) or 1.0, True
        unit_override = ""
        if not file and name in SUPPLEMENT:
            file, column, scale, bounded = SUPPLEMENT[name]
        if name in OVERRIDES:
            column, unit_override, bounded = OVERRIDES[name]
            scale = 1.0
        if not file or not column:
            continue                                            # listed by Epoch with no public per-model file
        attempted += 1
        text = files.get(file)
        if text is None:
            out.problems.append(f"{name}: {file} missing from the bundle")
            continue
        rows = _rows(text)
        if not rows or "Model version" not in rows[0] or column not in rows[0]:
            out.problems.append(f"{name}: {file} lost 'Model version' or '{column}'")
            continue
        bid = f"epoch-{slug(name)}"
        ceiling = _num(m.get("score_ceiling")) if bounded else None
        out.benchmarks.append(Benchmark(id=bid, name=name, source=SOURCE, source_url=PAGE, unit=unit_override or _UNIT[bounded],
                                        ceiling=ceiling, baseline=_num(m.get("random_baseline")) if bounded else None,
                                        released=m.get("release_date", ""), superseded_by=(f"epoch-{slug(m['superseded_by'])}" if m.get("superseded_by") else "")))
        for r in rows:
            mv, raw = (r.get("Model version") or "").strip(), _num(r.get(column))
            date = (r.get("Release date") or r.get("Started at") or "")[:10]
            if not mv or raw is None or not date:
                continue
            meta_row = models.get(mv, {})
            lab, lab_name = lab_of(r.get("Organization") or meta_row.get("organization", ""))
            out.results.append(Result(
                benchmark=bid, model=meta_row.get("display_name") or meta_row.get("model_group") or mv, model_id=mv, lab=lab, lab_name=lab_name,
                score=round(raw * scale, 6), date=date, weights=weights_of(meta_row.get("accessibility", "")),  # type: ignore[arg-type]
                source=SOURCE, url=(r.get("Log viewer") or PAGE), observed_on=observed_on))
    if attempted and len(out.problems) > attempted * flags.MAX_BAD_BENCHMARK_FRACTION:
        raise ValueError(f"epoch: {len(out.problems)} of {attempted} benchmark files unreadable (format changed): {out.problems[:3]}")
    _eci(files.get("epoch_capabilities_index/eci_scores.csv"), out, observed_on)
    return out


def _eci(text: str | None, out: Harvest, observed_on: str) -> None:
    """The Epoch Capabilities Index: one composite score per model across benchmarks (open-ended scale)."""
    if not text:
        out.problems.append("eci_scores.csv missing")
        return
    rows = _rows(text)
    if not rows or "eci" not in rows[0] or "date" not in rows[0]:
        out.problems.append("eci_scores.csv lost its columns")
        return
    out.benchmarks.append(Benchmark(id="epoch-eci", name="Epoch Capabilities Index", source=SOURCE, source_url="https://epoch.ai/benchmarks/eci",
                                    unit="points"))
    for r in rows:
        score, date = _num(r.get("eci")), (r.get("date") or "")[:10]
        if score is None or not date:
            continue
        lab, lab_name = lab_of(r.get("Organization", ""))
        group = (r.get("Accessibility group") or "").lower()
        out.results.append(Result(benchmark="epoch-eci", model=r.get("Display name") or r.get("Model", ""), model_id=r.get("Model", ""), lab=lab,
                                  lab_name=lab_name, score=score, date=date, weights="open" if group.startswith("open") else "closed" if group else "unknown",
                                  source=SOURCE, url="https://epoch.ai/benchmarks/eci", observed_on=observed_on))


def read_zip(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as z:
        return {i.filename: z.read(i).decode("utf-8", errors="replace") for i in z.infolist()
                if i.filename.endswith(".csv") and i.file_size < 20_000_000}


def fetch() -> Harvest:
    from datetime import UTC, datetime

    from algent_backend import polite_http

    with tempfile.TemporaryDirectory(prefix="aibench_") as tmp:
        files = read_zip(polite_http.download(URL, Path(tmp) / "epoch.zip"))
    return parse(files, observed_on=datetime.now(UTC).date().isoformat())
