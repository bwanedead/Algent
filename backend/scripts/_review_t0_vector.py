"""Print t0 menu + portfolio + router pick for human greenlight (no rail)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

pool_p = sorted(Path("ingestion_data/pool").glob("pool_*.json"), key=lambda p: p.stat().st_mtime)[-1]
pool = json.loads(pool_p.read_text(encoding="utf-8"))
items = pool.get("items") or []
print("=== T0", pool_p.name, len(items), "items", dict(Counter(i.get("channel") for i in items)), "===")
bf = [i for i in items if i.get("channel") == "backfeed"]
print("backfeed items:", len(bf), "(should be 0 with default off)")
for ch in ("gkg", "x", "beat", "market", "backfeed"):
    chunk = [i for i in items if i.get("channel") == ch]
    if not chunk:
        continue
    print(f"\n-- {ch} ({len(chunk)}) --")
    for n, i in enumerate(chunk, 1):
        cryst = "[cryst] " if (i.get("signals") or {}).get("crystallized") else ""
        print(f"{n:2}. [{i.get('kind')}] {cryst}{(i.get('label') or '')[:110]}")

# latest discovery_synthesis portfolio
syn_dirs = sorted(
    Path("runs_data/discovery_synthesis").glob("*/artifacts/research_portfolio.json"),
    key=lambda p: p.stat().st_mtime,
)
port = json.loads(syn_dirs[-1].read_text(encoding="utf-8")) if syn_dirs else {}
vecs = port.get("vectors") or []
print(f"\n=== PORTFOLIO ({syn_dirs[-1].parent.parent.name if syn_dirs else '?'}) n={len(vecs)} ===")
for v in vecs:
    hits = v.get("supporting_hits") or []
    nbf = sum(1 for h in hits if str(h).startswith("backfeed:"))
    print(f"  {v.get('id')}: {(v.get('title') or '')[:90]}  hits={len(hits)} backfeed={nbf}")

# latest signal_router ranking
rank_dirs = sorted(
    Path("runs_data/signal_router").glob("*/artifacts"),
    key=lambda p: p.stat().st_mtime,
)
if rank_dirs:
    art = rank_dirs[-1]
    print(f"\n=== ROUTER ({art.parent.name}) ===")
    for name in ("ranking.json", "selected_vector.json"):
        p = art / name
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"\n-- {name} --")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:3500])
    ev = art.parent / "audit" / "events.jsonl"
    if ev.exists():
        print("\n-- cooldown events --")
        for line in ev.read_text(encoding="utf-8").splitlines():
            if "cooldown" in line:
                e = json.loads(line)
                print(e.get("type"), json.dumps(e.get("payload"), ensure_ascii=False)[:600])
