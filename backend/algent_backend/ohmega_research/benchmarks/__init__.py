"""Source audits of third-party benchmark evidence, separate from the trial estimator.

A source audit describes what an external dataset observes and what it cannot. It never
converts benchmark rows into ``ohmega.research.trial/1`` records, because the sources do not
record intervention or assigned budgets. Only METR is supported, through ``metr``.
"""

from .metr import SOURCE_AUDIT_SCHEMA, SourceValidationError, audit, load_metadata, read_snapshot
from .report import render_source_audit, write_source_audit

__all__ = [
    "SOURCE_AUDIT_SCHEMA",
    "SourceValidationError",
    "audit",
    "load_metadata",
    "read_snapshot",
    "render_source_audit",
    "write_source_audit",
]
