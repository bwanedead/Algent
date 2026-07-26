"""Print latest t0 + portfolio + router ranking for human greenlight."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

pool_p = sorted(Path("ingestion_data/pool").glob("pool_*.json"), key=lambda p: p.stat().st_mtime)[-1]
pool = json.loads(pool_p.read_text(encoding="utf-8"))
items = pool.get("items") or []

print("=" * 72)
print("T0 POOL", pool_p.name)
print("=" * 72)
print("total", len(items), "by_channel", dict(Counter(i.get("channel") for i in items)))
print("x_share", f"{sum(1 for i in items if i.get('channel')=='x')/max(1,len(items)):.0%}")
print("backfeed", sum(1 for i in items if i.get("channel") == "backfeed"))
print()
for ch in ("gkg", "x", "market"):
    chunk = [i for i in items if i.get("channel") == ch]
    if not chunk:
        continue
    print(f"-- {ch} ({len(chunk)}) --")
    for n, i in enumerate(chunk, 1):
        cryst = "[cryst] " if (i.get("signals") or {}).get("crystallized") else ""
        lab = (i.get("label") or "")[:100]
        print(f"{n:2}. [{i.get('kind')}] {cryst}{lab}")
    print()

syn = sorted(
    Path("runs_data/discovery_synthesis").glob("*/artifacts/research_portfolio.json"),
    key=lambda p: p.stat().st_mtime,
)[-1]
port = json.loads(syn.read_text(encoding="utf-8"))
vecs = port.get("vectors") or []
print("=" * 72)
print("PORTFOLIO", syn.parent.parent.name, f"n={len(vecs)}")
print("=" * 72)
x_primary = 0
for v in vecs:
    hits = v.get("supporting_hits") or []
    n_x = sum(1 for h in hits if str(h).startswith("x:"))
    seeds = v.get("x_seed_urls") or []
    if n_x or seeds:
        x_primary += 1
    mark = " [X]" if (n_x or seeds) else ""
    print(f"  {v.get('id')}: {(v.get('title') or '')[:88]}{mark}  hits={len(hits)} x_hits={n_x}")
print(f"\nX-linked vectors: {x_primary}/{len(vecs)}")

rank_p = sorted(
    Path("runs_data/signal_router").glob("*/artifacts/ranking.json"),
    key=lambda p: p.stat().st_mtime,
)[-1]
ranking = json.loads(rank_p.read_text(encoding="utf-8"))
sel_p = rank_p.parent / "selected_vector.json"
selected = json.loads(sel_p.read_text(encoding="utf-8")) if sel_p.exists() else {}

print()
print("=" * 72)
print("ROUTER RANKING", rank_p.parent.parent.name)
print("=" * 72)
print("note:", (ranking.get("note") or "")[:500])
print()
print(f"{'rk':>3} {'sc':>5} {'cool':>5}  id    title")
for c in ranking.get("choices") or []:
    cool = "Y" if c.get("cooldown") else ""
    reason = (c.get("cooldown_reason") or "")[:55]
    vid = c.get("candidate_id")
    title = next((v.get("title") for v in vecs if v.get("id") == vid), vid)
    line = f"{c.get('rank'):3} {c.get('score'):5.0f} {cool:>5}  {vid}  {(title or '')[:70]}"
    print(line)
    if reason:
        print(f"         ↳ {reason}")

print()
print("WOULD PROMOTE (first non-cooldown):")
print(f"  {selected.get('id')}: {selected.get('title')}")
print(f"  thesis: {(selected.get('thesis') or '')[:200]}")
print()
print("Artifacts:")
print(f"  t0:        {pool_p}")
print(f"  portfolio: {syn}")
print(f"  ranking:   {rank_p}")
