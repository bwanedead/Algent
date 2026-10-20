"""
Conflict event log — attacks, clashes and mass-violence reports from several sources, normalised into one forward-captured, append-only record.

Keyless now: GDELT 2.0 events (machine-coded from news text; noisy, labelled so). Behind a key, built and inactive until the operator adds it:
ReliefWeb humanitarian reports (an approved ``appname``), ACLED (curated, the best source) and UCDP GED candidate events. Every event carries
``basis`` / ``coverage_note`` so a reader sees what kind of number it is. Events that land near a geoledger asset carry the asset.
See ``docs/architecture/conflict-events-gnss.md``.
"""
