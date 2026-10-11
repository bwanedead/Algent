"""
Live — continuous listening to free live data feeds, our own stats from them, and the rows the site shows.

One collector per feed (``feeds/``) behind one contract (``contracts.Feed``): fetch -> normalized ``LiveEvent`` /
``Stat`` -> store -> derived stats. Numeric results become ``live_*`` instrument series (so the numbers,
freshness and moves machinery and the daily's section writers see them); events are a current snapshot per feed
(``store.py``) and, with ``DATABASE_URL`` set, rows in ``live_events`` / ``live_stats`` for the site's /live page.
The AIS ship counter is a long-running service, not a timer job. Docs: ``docs/guides/worker-server.md`` (Live feeds).
"""
