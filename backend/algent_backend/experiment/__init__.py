"""
Experiment framework, phase 1 (docs/architecture/experiment-framework.md). ADDITIVE AND ISOLATED: nothing in the bots, the corpus index, publishing or the
site imports this package, and it only READS other products' stores (markets, corpus). It keeps its own store (``ALGENT_EXPERIMENT_STORE``), is manual
(no timer) and spends nothing unless ``newsroom lab run --live`` is given.

    contracts   the shapes: evidence (L1), observations (L2), policy versions, protocols, questions, runs
    store       write-once / append-only files under the experiment store
    access      the information-access gate (cutoff, derivation time, source closure, branch privacy)
    policies    versioned policy registry + the frozen snapshot of today's blind forecaster (P0)
    branches    isolated per-protocol state: memory namespace, fork
    sources     evidence adapters (corpus index, in-memory) and the question builder (markets)
    runner      a controlled run: one snapshot, one question, several protocols
    score       resolution (one rule for all), Brier / log / vs market / vs base rate, scoreboards per mode
"""
