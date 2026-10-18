"""
Collector — fetch each source, append what is new, record the source's health.

Failure-isolated: a source being down, or its format changing so that parsing breaks, is recorded in ``status.json`` (and so in the doctor and
the site's "as of") and never stops the others. A fetch that parses to far fewer rows than the source once gave is REFUSED (a truncated download
or a changed format): nothing is appended and the source is flagged ``broken``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from algent_backend.polite_http import SourceError

from . import flags, store
from .sources import Harvest, registry


def collect(sources: list[str] | None = None, *, fetchers: dict[str, Callable[[], Harvest]] | None = None) -> dict[str, Any]:
    fetchers = fetchers or registry()
    rows = []
    for src in sources or list(fetchers):
        row: dict[str, Any] = {"source": src}
        try:
            harvest = fetchers[src]()
            n = len(harvest.results)
            best = int(store.load_status().get(src, {}).get("best_rows", 0))
            if best and n < best * flags.MIN_KEEP_FRACTION:
                raise ValueError(f"{src}: parsed {n} rows against {best} seen before (below {flags.MIN_KEEP_FRACTION:.0%}); format changed or truncated")
            store.save_benchmarks(harvest.benchmarks)
            added = store.append(harvest.results, existing=store.log())
            newest = max((r.date for r in harvest.results), default="")
            row.update(status="ok", benchmarks=len(harvest.benchmarks), rows=n, new=added.new, revised=added.revised, newest_result=newest,
                       problems=harvest.problems[:10])
            store.save_status(src, last_ok=store.now_iso(), last_error="", broken=False, rows=n, best_rows=max(best, n), newest_result=newest,
                              benchmarks=len(harvest.benchmarks), problems=harvest.problems[:10], last_new=added.new)
        except (SourceError, OSError) as exc:                   # the network or the host: transient
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            store.save_status(src, last_error=row["error"], last_error_at=store.now_iso())
        except Exception as exc:  # noqa: BLE001 - a parse surprise (ValueError: format changed) must not take the other sources down
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}", broken=True)
            store.save_status(src, last_error=row["error"], last_error_at=store.now_iso(), broken=True)
        rows.append(row)
    return {"sources": rows}
