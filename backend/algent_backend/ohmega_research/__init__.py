"""Ohmega Research: auditable trial records and offline analysis for reproducible studies.

The first program is the non-interference goal frontier.

An isolated subdivision. It reads local JSONL trial records (``contracts``), summarises them
descriptively under an explicit denominator policy (``analysis``), and renders offline
artefacts (``report``). ``demo`` produces a labelled synthetic set. ``strict_json`` and
``html_page`` are the shared mechanical seams for parsing and page rendering.

``benchmarks`` is a distinct source audit of third-party evidence (a local METR snapshot).
It never converts benchmark rows into trial records and never feeds the trial estimator.

No network, no model calls, no dependency on the newsroom or agent runtime.

Run ``python -m algent_backend.ohmega_research --help`` from ``backend/``; see
``docs/guides/ohmega-research.md``.
"""

from .analysis import (
    ANALYSIS_SCHEMA,
    budget_status,
    build_analysis,
    is_confirmed,
    is_credited,
    summarize,
    wilson_interval,
)
from .contracts import (
    TRIAL_SCHEMA,
    TrialRecord,
    TrialValidationError,
    decode_trials,
    load_trials,
    parse_trials,
)
from .demo import write_demo
from .report import render_html, write_report

__all__ = [
    "ANALYSIS_SCHEMA",
    "TRIAL_SCHEMA",
    "TrialRecord",
    "TrialValidationError",
    "budget_status",
    "build_analysis",
    "decode_trials",
    "is_confirmed",
    "is_credited",
    "load_trials",
    "parse_trials",
    "render_html",
    "summarize",
    "wilson_interval",
    "write_demo",
    "write_report",
]
