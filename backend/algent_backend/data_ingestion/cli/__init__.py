"""
CLI for the data-ingestion pipeline (every command prints one JSON document).

``COMMANDS`` is the single source of truth for the ingest command set; both this
package's own dispatcher and the unified ``algent_backend.cli`` entry register
the same modules under the ``ingest`` category.
"""

from __future__ import annotations

from . import digest, fetch, insights, lists, pool, sample, sources, sweep, t0, x

COMMANDS = (fetch, insights, sweep, pool, t0, sample, x, lists, digest, sources)
