"""Operator knobs for the experiment lab (checked-in, not .env)."""

RUN_CAP_USD = 0.05          # per-call cap for a live run (the house model under the budget gate); a live run is refused unless --live is given
EVIDENCE_K = 8              # documents each protocol's retrieval policy may show the model (same for every protocol in a controlled run)
BODY_CHARS = 700            # characters of a document shown to the model
CALIBRATION_BINS = 5
DUP_JACCARD = 0.8          # origin chains: two texts sharing this much of their 4-word shingles are one voice repeated (origins.py, method origin-chain@1)
