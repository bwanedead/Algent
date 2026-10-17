"""
Maritime behaviour — original intelligence from the AIS we already hear: which vessels went dark inside heard water, met another ship
in open water, changed identity, appeared on a sanctions list, or loitered over sensitive infrastructure.

    profile.py     the per-vessel behaviour memory (bounded, persisted): identity, last position, thin history, place activity
    watch.py       what the stream service holds: the book, and the detector passes
    detect/        one module per behaviour (gap, sts, identity, sanctioned, loiter), each a pure function over the book
    sites.py       port / coast exclusion and the sensitive zones
    store.py       events.json (current picture), log.jsonl (the record), profiles and detector state
    publish.py     maritime_events (migration 013) and the geoledger vessel link
    desk.py        the OHMEGA MARITIME evidence block for the daily

Derived by Ohmega from public AIS (provenance ``ohmega_derived``); forward-only; every threshold is in ``flags.py`` with its reason.
Docs: ``docs/architecture/maritime-behaviour.md``.
"""
