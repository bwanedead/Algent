"""
``newsroom corpus`` — is the knowledge base actually accumulating?

The profiles are half the value of the newsroom: each story's researched sources and claims,
meant to add up into a growing, linked body of knowledge that later stories draw on. For
months nothing showed whether that was happening, and it wasn't — id collisions were quietly
saving new stories over old ones. This is the view that would have caught it.

    newsroom corpus            # totals, growth, links between stories, integrity
    newsroom corpus --json     # the same, machine-readable

Integrity is the section to read first: collisions, profiles that are only recovered, and
stories whose read pages were not kept all show up there instead of disappearing.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from algent_backend.agent_system.agents.research.recovery import GENERATOR as RECOVERED
from algent_backend.agent_system.agents.research.store import JsonProfileStore


def add_parser(sub: Any) -> None:
    p = sub.add_parser("corpus", help="show the profile knowledge base: size, growth, links, integrity")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(handler=run_corpus)


def summarize(store: JsonProfileStore) -> dict[str, Any]:
    profiles = [p for p in (store.get(i) for i in store.list_ids()) if p is not None]
    statuses: Counter[str] = Counter()
    url_owner: dict[str, set[str]] = defaultdict(set)
    entity_owner: dict[str, set[str]] = defaultdict(set)
    by_month: dict[str, dict[str, int]] = defaultdict(lambda: {"profiles": 0, "new_sources": 0})
    seen_urls: set[str] = set()
    deep = mentions = 0

    for p in sorted(profiles, key=lambda p: p.generated_at or p.as_of or ""):
        month = (p.generated_at or p.as_of or "unknown")[:7]
        by_month[month]["profiles"] += 1
        statuses.update(c.status for c in p.claim_ledger)
        for s in p.source_ledger:
            mentions += 1
            deep += bool(s.snapshot)
            if s.url:
                url_owner[s.url].add(p.id)
                if s.url not in seen_urls:
                    seen_urls.add(s.url)
                    by_month[month]["new_sources"] += 1
        for e in p.entities:
            entity_owner[(e.canonical_name or e.name).strip().lower()].add(p.id)

    # The links that make it a graph rather than a pile: a source or entity two stories share.
    pair_links: Counter[tuple[str, str]] = Counter()
    for owners in list(url_owner.values()) + list(entity_owner.values()):
        for a, b in combinations(sorted(owners), 2):
            pair_links[(a, b)] += 1
    titles = {p.id: p.title for p in profiles}

    recovered = [p.id for p in profiles if p.generator == RECOVERED]
    no_reads = [p.id for p in profiles if p.generator != RECOVERED
                and not (store.root / f"{p.id}.reads.jsonl").exists()]
    collisions = []
    log = store.root / "_collisions.jsonl"
    if log.exists():
        collisions = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]

    return {
        "profiles": len(profiles),
        "full_research": len(profiles) - len(recovered),
        "recovered_only": len(recovered),
        "claims": sum(statuses.values()),
        "claims_by_status": dict(statuses.most_common()),
        "source_mentions": mentions,
        "distinct_sources": len(seen_urls),
        "deep_read_share": round(deep / mentions, 2) if mentions else 0.0,
        "growth_by_month": dict(sorted(by_month.items())),
        "sources_shared_by_2plus_stories": sum(1 for o in url_owner.values() if len(o) > 1),
        "entities_shared_by_2plus_stories": sum(1 for o in entity_owner.values() if len(o) > 1),
        "most_linked_story_pairs": [
            {"a": titles[a][:60], "b": titles[b][:60], "shared": n}
            for (a, b), n in pair_links.most_common(8)
        ],
        "integrity": {
            "collisions_caught": len(collisions),
            "recovered_profiles": len(recovered),
            "full_profiles_without_kept_reads": len(no_reads),
            "history_versions": sum(len(store.history(i)) for i in titles),
        },
    }


def run_corpus(args: Any) -> int:
    report = summarize(JsonProfileStore())
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    r, i = report, report["integrity"]
    print(f"PROFILES  {r['profiles']}  ({r['full_research']} full research, "
          f"{r['recovered_only']} recovered from published receipts)")
    print(f"CLAIMS    {r['claims']}  " + "  ".join(f"{k} {v}" for k, v in r["claims_by_status"].items()))
    print(f"SOURCES   {r['distinct_sources']} distinct  ({r['source_mentions']} citations, "
          f"{int(r['deep_read_share'] * 100)}% read in full)")
    print(f"LINKS     {r['sources_shared_by_2plus_stories']} sources and "
          f"{r['entities_shared_by_2plus_stories']} entities shared by 2+ stories")
    print("\nGROWTH")
    for month, g in r["growth_by_month"].items():
        print(f"  {month}  +{g['profiles']} profiles  +{g['new_sources']} new sources")
    if r["most_linked_story_pairs"]:
        print("\nMOST-LINKED STORIES")
        for pair in r["most_linked_story_pairs"]:
            print(f"  {pair['shared']:>3}  {pair['a']}  <->  {pair['b']}")
    print("\nINTEGRITY")
    print(f"  collisions caught (saved aside, not overwritten): {i['collisions_caught']}")
    print(f"  recovered-only profiles (receipts, no threads):   {i['recovered_profiles']}")
    print(f"  full profiles without kept read pages:            {i['full_profiles_without_kept_reads']}")
    print(f"  saved versions in history:                        {i['history_versions']}")
    return 0
