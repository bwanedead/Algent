"""Summarize latest t0 for novelty/curiosity/science/story grain vs wire head."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

root = Path("ingestion_data")
ins = sorted((root / "insights").glob("*.json"), key=lambda p: p.stat().st_mtime)[-1]
pool_p = sorted((root / "pool").glob("pool_*.json"), key=lambda p: p.stat().st_mtime)[-1]

report = json.loads(ins.read_text(encoding="utf-8"))
pool = json.loads(pool_p.read_text(encoding="utf-8"))
cands = report.get("candidates") or []
items = pool.get("items") or []

print("=== INSIGHTS", ins.name, "===")
print("has_velocity_baseline", report.get("has_velocity_baseline"), "n_candidates", len(cands))
print("kinds", dict(Counter(c.get("kind") for c in cands)))
reason_ct: Counter[str] = Counter()
for c in cands:
    for r in c.get("reasons") or []:
        reason_ct[r] += 1
print("reason counts among shortlist:", dict(reason_ct))
curiosity = [c for c in cands if "curiosity" in (c.get("reasons") or [])]
novel = [c for c in cands if "novel" in (c.get("reasons") or []) or c.get("novel")]
specific = [c for c in cands if "specific" in (c.get("reasons") or [])]
print(
    f"curiosity-tagged: {len(curiosity)}  novel-tagged: {len(novel)}  "
    f"specific-tagged: {len(specific)}"
)

print("\n-- story / event / curiosity candidates --")
for c in sorted(cands, key=lambda x: -x.get("score", 0)):
    rs = c.get("reasons") or []
    if c.get("kind") in ("story", "event") or "curiosity" in rs or "specific" in rs:
        print(
            f"  score={c.get('score'):6.3f} kind={c.get('kind')} novel={c.get('novel')} "
            f"reasons={rs} | {str(c.get('key'))[:70]}"
        )

print("\n-- top 15 shortlist by score --")
for c in sorted(cands, key=lambda x: -x.get("score", 0))[:15]:
    print(
        f"  {c.get('score'):6.3f} [{c.get('kind')}] {c.get('reasons')} | "
        f"{str(c.get('key'))[:60]}"
    )

print("\n=== POOL", pool_p.name, "===")
print("by_channel", dict(Counter(i.get("channel") for i in items)), "total", len(items))
print("by_kind", dict(Counter(i.get("kind") for i in items)))

gkg = [i for i in items if i.get("channel") == "gkg"]
print("\n-- GKG labels --")
for n, i in enumerate(gkg, 1):
    rs = (i.get("signals") or {}).get("reasons") or []
    print(f"{n:2}. [{i.get('kind')}] {(i.get('label') or '')[:110]}  {rs}")

x = [i for i in items if i.get("channel") == "x"]
bands: Counter[str] = Counter()
for i in x:
    iid = str(i.get("id") or "")
    lane = str((i.get("signals") or {}).get("lane") or "")
    if "novelty" in iid:
        bands["novelty"] += 1
    elif "spectrum" in iid:
        bands["spectrum"] += 1
    elif "ai_pulse" in iid:
        bands["ai_pulse"] += 1
    elif lane.startswith("agg:"):
        bands["aggregator"] += 1
    else:
        bands["news"] += 1
print("\nX bands", dict(bands))

print("\n-- all X labels --")
for n, i in enumerate(x, 1):
    sig = i.get("signals") or {}
    iid = str(i.get("id") or "")
    lane = str(sig.get("lane") or "")
    if "novelty" in iid:
        b = "novelty"
    elif "spectrum" in iid:
        b = "spectrum"
    elif "ai_pulse" in iid:
        b = "ai_pulse"
    elif lane.startswith("agg:"):
        b = "agg"
    else:
        b = "news"
    print(f"{n:2}. [{b}] {(i.get('label') or '')[:105]}")

print("\n-- markets --")
for i in items:
    if i.get("channel") == "market":
        print(f"  {(i.get('label') or '')[:100]}")
