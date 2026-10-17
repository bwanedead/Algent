"""
Markets — a reality feedback loop. Ohmega's intelligence is paper-traded against Polymarket so it is scored by the world, not by itself.

    polymarket.py   read-only client for the public Gamma (markets, events) and CLOB (price history) APIs; no key, no wallet, no orders
    mapping.py      which of our theaters / countries a market is about (soft: it picks evidence, it never gates a score)
    store.py        markets, price snapshots, forecasts (immutable), paper trades: all append-only on disk
    mirror.py       the collector: discover, snapshot prices, record resolutions
    evidence.py     the BLIND evidence a forecast sees (never the market price)
    forecast.py     one cheap structured model call per market per day -> our probability
    paper.py        the paper portfolio: edge rule, capped Kelly sizing, daily mark-to-market, settlement
    score.py        Brier / log loss of us vs the market at the same instants, calibration, P&L, hit rate
    publish.py      the track-record document the site reads
    desk.py         the short "where we disagree with the market" lines for the daily

PAPER ONLY. Nothing here can place an order: there is no wallet, no key and no write endpoint in the client. Every judgement
number lives in ``flags.py`` with its reason. Docs: ``docs/architecture/markets-track-record.md``.
"""
