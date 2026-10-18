"""
AI benchmark tracker — frontier model scores across every public benchmark that is freely, machine-readably published.

The AI desk's numbers layer (the sibling of ``instruments/`` for geopolitics; no model anywhere in the collectors). Free sources
(Epoch AI's benchmarking hub, SWE-bench's leaderboards, LMArena) are collected on a timer into an append-only store; the derived series
(frontier over time, open vs closed weights, per-lab best, saturation) are computed from the data alone, and one document is published
to the site. A separate, capped discovery pass records lab-claimed scores that no leaderboard carries yet, kept as ``self_reported``.
See ``docs/architecture/ai-desk.md``.
"""
