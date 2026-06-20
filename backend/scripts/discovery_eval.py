"""
Discovery evaluation harness — replay a real GKG batch sequence and read out the
signal quality. The instrument behind the deterministic-tuning iterations (see
discovery/ITERATION_LOG.md).

Fetches the last N consecutive 15-minute GKG batches (caching raw records under
ingestion_data/replay_cache/ so iterating on signal code re-uses identical data
with no re-download), replays them through the pipeline with accumulating memory,
and prints what the final batch surfaces.

    ./.venv/Scripts/python.exe scripts/discovery_eval.py -n 8 --top 15
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from algent_backend.data_ingestion.news_production.discovery.replay import replay  # noqa: E402
from algent_backend.data_ingestion.news_production.sources import gdelt_gkg  # noqa: E402
from algent_backend.data_ingestion.news_production.sources.records import GkgRecord  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / "ingestion_data" / "replay_cache"


def recent_batch_ids(n: int) -> list[str]:
    """The n most recent completed 15-min batch stamps, oldest first.

    Skips the current slot (it may still be publishing).
    """
    now = datetime.now(UTC)
    base = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    ids = [(base - timedelta(minutes=15 * (i + 1))).strftime("%Y%m%d%H%M%S") for i in range(n)]
    return list(reversed(ids))


def load_or_fetch(batch_id: str) -> list[GkgRecord]:
    path = CACHE / f"{batch_id}.json"
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [_from_row(r) for r in rows]
    _, records = gdelt_gkg.fetch_batch(batch_id)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([_to_row(r) for r in records]), encoding="utf-8")
    return records


def _to_row(r: GkgRecord) -> dict:
    return {
        "record_id": r.record_id, "url": r.url, "source_name": r.source_name,
        "language": r.language, "themes": list(r.themes), "persons": list(r.persons),
        "organizations": list(r.organizations), "tone": r.tone,
    }


def _from_row(r: dict) -> GkgRecord:
    return GkgRecord(
        record_id=r["record_id"], url=r["url"], source_name=r["source_name"],
        language=r["language"], themes=tuple(r["themes"]), persons=tuple(r["persons"]),
        organizations=tuple(r["organizations"]), tone=r["tone"],
    )


def _fmt(c) -> str:
    vel = f"{c.velocity:+.2f}" if c.velocity is not None else "  -  "
    tone = f"{c.avg_tone:+.1f}" if c.avg_tone is not None else "  - "
    related = f"  +{{{', '.join(c.related[:4])}}}" if c.related else ""
    return (
        f"  [{c.kind[:5]:5}] {c.key[:34]:34} n={c.count:4} v={vel} "
        f"langs={c.language_count:2} tone={tone} score={c.score:.2f} {c.reasons}{related}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=8, help="batches in the sequence")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    ids = recent_batch_ids(args.n)
    batches = [(bid, load_or_fetch(bid)) for bid in ids]
    reports = replay(batches, source="gdelt_gkg")
    last = reports[-1]

    print(f"sequence: {ids[0]} .. {ids[-1]}  ({len(ids)} batches)")
    print(
        f"final batch {last.batch_id}: {last.total_records} records, "
        f"{len(last.candidates)} candidates, velocity_baseline={last.has_velocity_baseline}\n"
    )

    kinds = Counter(c.kind for c in last.candidates)
    reasons = Counter(r for c in last.candidates for r in c.reasons)
    print(f"kind mix:   {dict(kinds)}")
    print(f"reason mix: {dict(reasons)}")
    print(f"rising={sum(c.rising for c in last.candidates)}  novel={sum(c.novel for c in last.candidates)}\n")

    print(f"TOP {args.top} BY SCORE (the shortlist order):")
    for c in last.candidates[: args.top]:
        print(_fmt(c))

    movers = sorted(
        (c for c in last.candidates if c.velocity is not None), key=lambda c: c.velocity, reverse=True
    )
    if movers:
        print(f"\nTOP {args.top} BY VELOCITY (what's actually moving):")
        for c in movers[: args.top]:
            print(_fmt(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
