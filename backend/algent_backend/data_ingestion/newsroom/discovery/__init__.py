"""
Deterministic discovery digests over source records.

This is the pre-LLM signal layer: pure functions that turn a batch of parsed
records into a compact, multi-lens stats digest (volume / rarity / tone, grouped
per language and tagged by pillar). Discovery agents read this digest instead of
the raw firehose. No model and no I/O live here.
"""
