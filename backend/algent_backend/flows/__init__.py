"""
Flows — watching the world's circulation: ships on their lanes (our own observed AIS), and, clearly apart from them, the slower money
and grain that move between countries (public trade statistics).

    classes.py     AIS ship type + name hints -> a flow class (tanker, lng, bulk, container, cargo)
    network.py     the named places (chokepoints, port regions), the lane graph between them and its routing (pure data)
    tracker.py     the lane tracker the stream service holds: a vessel seen in a new place after another is one hop; hops fold into
                   directed lane counts per day and class (aggregates only, never tracks)
    rates.py       daily aggregates -> rolling rates, per-place anomaly against the place's own normal
    store.py       what is kept on disk (small: per-vessel last place, the daily aggregates, the trade cache)
    trade/         commodity and money flows from UN Comtrade's public preview API (annual values, a different source and cadence)
    document.py    the one published ``flows`` document the site's flow layer draws
    publish.py     push that document to the public Storage bucket the way the other live products go

Derived by Ohmega from public AIS and public trade statistics; forward-only; every judgement is in ``flags.py`` with its reason.
Docs: ``docs/architecture/flows.md``.
"""
