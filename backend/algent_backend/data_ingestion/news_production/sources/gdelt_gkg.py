"""
GDELT GKG source — fetch and parse the latest 15-minute Global Knowledge Graph.

GKG is GDELT's coded view of world news: every 15 minutes it publishes a batch
(~1k+ documents, a few MB gzipped) tagging each article with themes, named
entities, locations and tone — coded the same way regardless of the article's
language. Unlike the DOC API this is a *static file download*, not a rate-limited
query endpoint, so it is the channel for heavy, unlimited discovery use.

GDELT splits its output across two parallel streams, each with its own
``lastupdate`` index: the **English** master and the **translingual** feed (the
~65 non-English languages, machine-translated and coded). They are separate
batches; ``fetch_latest`` pulls both and merges them so one digest spans every
language — which is the whole reason language is the digest's top axis.

This module does three things and nothing else:
- ``latest_batch_url`` — resolve the newest batch URL for one stream.
- ``fetch_latest`` — download + parse + merge both streams into records.
- ``parse_gkg`` — turn a batch's tab-separated rows into ``GkgRecord``s.

Each download is a single GET with a clear timeout; any failure raises with the
URL so the caller can record it verbatim.
"""

from __future__ import annotations

import io
import zipfile

from .records import GkgRecord

# The two parallel GKG streams. English is the master; translation carries the
# non-English languages (each row's source language is in its TRANSLATIONINFO).
_LASTUPDATE_URLS = (
    "http://data.gdeltproject.org/gdeltv2/lastupdate.txt",
    "http://data.gdeltproject.org/gdeltv2/lastupdate-translation.txt",
)
_TIMEOUT_S = 60.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}

# Column indices in the 27-field GKG 2.1 row (verified against a live batch).
_COL_RECORD_ID = 0
_COL_DATE = 1
_COL_SOURCE_NAME = 3
_COL_URL = 4
_COL_THEMES = 7  # V1THEMES: ";"-separated theme codes
_COL_LOCATIONS = 9
_COL_PERSONS = 11  # V1PERSONS: ";"-separated names
_COL_ORGS = 13  # V1ORGANIZATIONS: ";"-separated names
_COL_TONE = 15  # V1.5TONE: comma-separated; field [0] is the average tone
_COL_TRANSLATION = 25  # V2.1TRANSLATIONINFO: "srclc:xxx;..."  (empty => English)
_MIN_FIELDS = 26


def latest_batch_url(lastupdate_url: str, *, client: object | None = None) -> tuple[str, str]:
    """Resolve the newest GKG batch for one stream. Returns ``(batch_id, zip_url)``.

    ``batch_id`` is GDELT's 14-digit ``YYYYMMDDHHMMSS`` stamp for the batch.
    """
    text = _get(lastupdate_url, client=client).decode("utf-8", "replace")
    for line in text.strip().splitlines():
        url = line.split(" ")[-1]
        if url.endswith(".gkg.csv.zip"):
            batch_id = url.rsplit("/", 1)[-1].split(".")[0]
            return batch_id, url
    raise RuntimeError(f"no GKG line found in {lastupdate_url}:\n{text[:500]}")


def fetch_latest(*, client: object | None = None) -> tuple[str, list[GkgRecord]]:
    """Download and merge the newest English + translingual batches.

    Returns ``(batch_id, records)`` where ``batch_id`` is the English stream's
    stamp (the streams publish on near-identical 15-minute slots). One shared
    HTTP client is reused across all downloads when the caller doesn't supply
    one.
    """
    import httpx

    own_client = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS)
    try:
        batch_id = ""
        records: list[GkgRecord] = []
        for lastupdate_url in _LASTUPDATE_URLS:
            stream_id, zip_url = latest_batch_url(lastupdate_url, client=http)
            batch_id = batch_id or stream_id  # English stream is listed first
            records.extend(parse_gkg(_get(zip_url, client=http)))
        return batch_id, records
    finally:
        if own_client:
            http.close()


def parse_gkg(zip_bytes: bytes) -> list[GkgRecord]:
    """Parse a raw ``.gkg.csv.zip`` payload into records, skipping malformed rows."""
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    raw = archive.read(archive.namelist()[0]).decode("utf-8", "replace")
    records: list[GkgRecord] = []
    for line in raw.splitlines():
        record = _parse_row(line)
        if record is not None:
            records.append(record)
    return records


def _parse_row(line: str) -> GkgRecord | None:
    fields = line.split("\t")
    if len(fields) < _MIN_FIELDS:
        return None
    translation = fields[_COL_TRANSLATION] if len(fields) > _COL_TRANSLATION else ""
    return GkgRecord(
        record_id=fields[_COL_RECORD_ID],
        url=fields[_COL_URL],
        source_name=fields[_COL_SOURCE_NAME],
        language=_language_of(translation),
        themes=_split(fields[_COL_THEMES]),
        persons=_split(fields[_COL_PERSONS]),
        organizations=_split(fields[_COL_ORGS]),
        tone=_first_tone(fields[_COL_TONE]),
    )


def _language_of(translation_info: str) -> str:
    """Source language from TRANSLATIONINFO. Empty field means English source."""
    if not translation_info:
        return "eng"
    for token in translation_info.split(";"):
        if token.startswith("srclc:"):
            return token[len("srclc:") :] or "eng"
    return "eng"


def _split(field_value: str) -> tuple[str, ...]:
    """Split a ``;``-delimited GKG list, dropping empties and normalising case."""
    return tuple(part.strip() for part in field_value.split(";") if part.strip())


def _first_tone(field_value: str) -> float | None:
    head = field_value.split(",", 1)[0].strip()
    try:
        return float(head)
    except ValueError:
        return None


def _get(url: str, *, client: object | None = None) -> bytes:
    """Single GET returning raw bytes; raises with the URL on any non-200."""
    import httpx

    http = client if client is not None else httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS)
    close = client is None
    try:
        response = http.get(url)  # type: ignore[attr-defined]
        if response.status_code != 200:
            raise RuntimeError(f"GDELT GKG fetch failed: HTTP {response.status_code} for {url}")
        return response.content
    finally:
        if close:
            http.close()  # type: ignore[attr-defined]
