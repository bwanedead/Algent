"""
``RawPacket`` — the uniform result of *retrieving and unpacking* one source batch.

Before any processing decision, every source can hand back the same shape: the
batch id and one-or-more unpacked text parts (a GKG batch is two parallel stream
files; an NGrams batch is a single file). The fetch surface lands these to disk
verbatim so we can look at real data and decide what to process it for.

This is deliberately dumb: decompressed text + a record (line) count, nothing
interpreted. Typed parsing and digests are downstream concerns.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawPart:
    """One unpacked file within a batch."""

    name: str  # filename to land it under, e.g. "english.gkg.csv"
    text: str  # decompressed content, verbatim
    record_count: int  # lines / records, for the summary


@dataclass(frozen=True, slots=True)
class RawPacket:
    """The latest batch of a source, retrieved and unpacked."""

    source: str  # source id, e.g. "gdelt_gkg"
    batch_id: str  # the source's batch stamp (14-digit YYYYMMDDHHMMSS)
    parts: tuple[RawPart, ...]
