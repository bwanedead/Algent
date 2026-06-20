"""
``sample`` — a language-stratified long-tail slice of raw records for the agent.

Streams a source's latest packet and draws a small, language-balanced random
sample (engineered serendipity — see ``discovery.sampling``). This runs *after*
the deterministic ``insights`` pass on purpose: the agent compares this raw slice
against the deterministic finds and decides whether anything here earns a place
on the list or gets tossed.

Streaming only — the raw packet is never landed; just the small sample artifact.

    python -m algent_backend.data_ingestion.cli sample gdelt_ngrams --size 150
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from ..news_production.discovery.report import LongtailSample, SampleRecord
from ..news_production.discovery.sampling import stratified_reservoir
from ..news_production.sources import gdelt_ngrams
from ._shared import print_json, prune_files, samples_dir

# Sources exposing a streamable record iterator. id -> stream -> (batch_id, iter[dict]).
_STREAMERS = {gdelt_ngrams.SOURCE_ID: gdelt_ngrams.stream_latest}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sample", help="draw a stratified long-tail raw slice")
    parser.add_argument("source", choices=sorted(_STREAMERS))
    parser.add_argument("--size", type=int, default=150, help="records in the slice (default 150)")
    parser.add_argument("--keep", type=int, default=1, help="samples to retain (default 1)")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    batch_id, records = _STREAMERS[args.source]()
    picked = stratified_reservoir(
        records, size=args.size, key=lambda r: r.get("lang", "?"), per_key_cap=5
    )
    sample_records = [_to_record(r) for r in picked]

    sample = LongtailSample(
        source=args.source,
        batch_id=batch_id,
        generated_at=datetime.now(UTC).isoformat(),
        size=len(sample_records),
        languages=len({r.lang for r in sample_records}),
        records=sample_records,
    )

    out_dir = samples_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.source}_{batch_id}.json"
    path.write_text(sample.model_dump_json(indent=2), encoding="utf-8")
    purged = prune_files(out_dir, f"{args.source}_*.json", keep=args.keep)

    print_json(
        {
            "source": args.source,
            "batch_id": batch_id,
            "size": sample.size,
            "languages": sample.languages,
            "sample_path": str(path),
            "retained": args.keep,
            "purged": purged,
        }
    )
    return 0


def _to_record(raw: dict) -> SampleRecord:
    pre, post = raw.get("pre", ""), raw.get("post", "")
    return SampleRecord(
        lang=raw.get("lang", "?"),
        ngram=raw.get("ngram", ""),
        text=f"{pre} … {post}".strip(),
        url=raw.get("url", ""),
    )
