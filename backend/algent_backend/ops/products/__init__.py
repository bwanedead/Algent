"""
The product registry (``registry.py``) and everything derived from it. A product exists only if it is in the registry; see
docs/architecture/foundation.md and ``newsroom products``.

    model.py       the vocabulary (Product, Store, Budget, Retention, Job)
    registry.py    THE list: one entry per product
    locations.py   where each store lives (reusing the owning module's own resolver)
    views.py       derived: backup coverage, envelope budgets, timers, paid jobs, docs table, site contract
    validate.py    the rules an entry must satisfy (retention, budgets, reasons, no cycles)
    check.py       the live machine against the registry (``newsroom products check``, embedded in the doctor)
    run.py         what a timer starts: ``newsroom products run <job>``
"""
