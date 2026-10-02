"""python -m algent_backend.ohmega_research {validate,report,demo}

Offline only: reads a local JSONL file and writes ``analysis.json`` + ``report.html``.
Default outputs go under the runs-data root (``backend/runs_data`` or ``ALGENT_RUNS_DIR``),
and nothing is ever written into the source tree.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from .contracts import TrialValidationError, load_trials
from .demo import write_demo
from .report import write_report

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_RUNS_DIR_ENV = "ALGENT_RUNS_DIR"  # the run control plane's documented runs-data override
_OUTPUT_SUBDIR = "ohmega_research"


class _OutputRefused(Exception):
    pass


def _runs_roots() -> list[Path]:
    roots = [(_BACKEND_DIR / "runs_data").resolve()]
    override = os.environ.get(_RUNS_DIR_ENV)
    if override:
        root = Path(override).resolve()
        if Path(__file__).resolve().is_relative_to(root):
            raise _OutputRefused(f"{_RUNS_DIR_ENV}={root} contains the source tree")
        roots.insert(0, root)
    return roots


def _output_dir(requested: str | None, default_name: str) -> Path:
    roots = _runs_roots()
    target = Path(requested) if requested else roots[0] / _OUTPUT_SUBDIR / default_name
    target = target.resolve()
    inside_repo = target.is_relative_to(_REPO_ROOT)
    if inside_repo and not any(target.is_relative_to(root) for root in roots):
        raise _OutputRefused(
            f"refusing to write into the source tree: {target}\n"
            f"inside the repository, outputs belong under {roots[0]}"
        )
    return target


def _print_paths(paths: dict[str, Path]) -> None:
    print(json.dumps({name: str(path) for name, path in paths.items()}, indent=2))


def _validate(args: argparse.Namespace) -> int:
    records = load_trials(Path(args.input))
    print(json.dumps({
        "valid": True,
        "records": len(records),
        "dataset_kinds": dict(sorted(Counter(r.dataset_kind for r in records).items())),
        "studies": sorted({r.study_id for r in records}),
    }, indent=2))
    return 0


def _report(args: argparse.Namespace) -> int:
    _print_paths(write_report(Path(args.input), _output_dir(args.output, "report")))
    return 0


def _demo(args: argparse.Namespace) -> int:
    _print_paths(write_demo(_output_dir(args.output, "demo")))
    print("SYNTHETIC demo: no model was run; the report supports no capability conclusion.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m algent_backend.ohmega_research",
        description="Validate trial records and build the offline exploratory report.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    validate = verbs.add_parser("validate", help="strictly validate a trial JSONL file")
    validate.add_argument("--input", required=True, help="trial JSONL path")
    validate.set_defaults(handler=_validate)
    report = verbs.add_parser("report", help="write analysis.json and report.html")
    report.add_argument("--input", required=True, help="trial JSONL path")
    report.add_argument("--output", help="output directory (default: runs-data root)")
    report.set_defaults(handler=_report)
    demo = verbs.add_parser("demo", help="write a deterministic SYNTHETIC set and its report")
    demo.add_argument("--output", help="output directory (default: runs-data root)")
    demo.set_defaults(handler=_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except TrialValidationError as exc:
        for error in exc.errors:
            print(error, file=sys.stderr)
        print(f"rejected: {len(exc.errors)} problem(s); nothing was written", file=sys.stderr)
        return 1
    except (_OutputRefused, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
