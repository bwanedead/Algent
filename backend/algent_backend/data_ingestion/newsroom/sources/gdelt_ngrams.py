"""
GDELT Web News NGrams 3.0 source — fetch and unpack the latest minute-packet.

NGrams 3.0 is GDELT's most granular, most multilingual channel: every minute it
emits one gzipped newline-delimited-JSON file (~2MB gz, ~23MB / ~70k records
unpacked) of individual ngram occurrences across all 150+ languages, each with
its surrounding text snippet and source URL. Unlike GKG it has *no* coded themes
— it is raw lexical signal, which is exactly why we land it raw for now and
decide processing later.

There is no ``lastupdate`` index for NGrams; files are named purely by minute
(``YYYYMMDDHHMMSS.webngrams.json.gz``) and publish in clusters with gaps, lagging
real time by ~15 minutes. So "latest" means: walk back minute-by-minute from now
until a file resolves. We download exactly one packet.
"""

from __future__ import annotations

import gzip
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from .packet import RawPacket, RawPart

SOURCE_ID = "gdelt_ngrams"

_BASE_URL = "http://data.gdeltproject.org/gdeltv3/webngrams/"
_TIMEOUT_S = 60.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}
# How far back to look for the most recent published minute. Publishing lags
# ~15 min and clusters with gaps, so a ~40-minute window reliably finds one.
_MAX_LOOKBACK_MINUTES = 40


def latest_packet_url(
    *, client: object | None = None, now: datetime | None = None
) -> tuple[str, str]:
    """Resolve the newest available NGrams packet. Returns ``(batch_id, url)``.

    Walks back minute-by-minute from ``now`` (UTC) and returns the first minute
    whose file exists. ``now`` is injectable for testing.
    """
    own = client is None
    http = client or _new_client()
    try:
        start = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
        for back in range(_MAX_LOOKBACK_MINUTES + 1):
            batch_id = (start - timedelta(minutes=back)).strftime("%Y%m%d%H%M%S")
            url = f"{_BASE_URL}{batch_id}.webngrams.json.gz"
            if http.head(url).status_code == 200:  # type: ignore[attr-defined]
                return batch_id, url
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]
    raise RuntimeError(
        f"no NGrams packet found in the last {_MAX_LOOKBACK_MINUTES} minutes before "
        f"{(now or datetime.now(UTC)).isoformat()}"
    )


def fetch_latest_raw(*, client: object | None = None) -> RawPacket:
    """Download and unpack the newest NGrams packet (one file)."""
    own = client is None
    http = client or _new_client()
    try:
        batch_id, url = latest_packet_url(client=http)
        response = http.get(url)  # type: ignore[attr-defined]
        if response.status_code != 200:
            raise RuntimeError(f"NGrams fetch failed: HTTP {response.status_code} for {url}")
        return _build_packet(batch_id, response.content)
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]


def stream_latest(*, client: object | None = None) -> tuple[str, Iterator[dict]]:
    """Download the newest packet and yield its records one at a time.

    The gzip (~2MB) is held in memory and decompressed *incrementally* line by
    line, so the full ~140MB of decompressed JSON never materialises and nothing
    is written to disk — exactly the streaming, no-retention path the processing
    layer wants. Malformed lines are skipped.
    """
    own = client is None
    http = client or _new_client()
    try:
        batch_id, url = latest_packet_url(client=http)
        response = http.get(url)  # type: ignore[attr-defined]
        if response.status_code != 200:
            raise RuntimeError(f"NGrams fetch failed: HTTP {response.status_code} for {url}")
        gz_bytes = response.content
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]
    return batch_id, _iter_records(gz_bytes)


def _iter_records(gz_bytes: bytes) -> Iterator[dict]:
    with gzip.GzipFile(fileobj=io.BytesIO(gz_bytes)) as stream:
        for raw_line in stream:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _build_packet(batch_id: str, gz_bytes: bytes) -> RawPacket:
    """Decompress a packet's gzip payload into a one-part :class:`RawPacket`."""
    text = gzip.decompress(gz_bytes).decode("utf-8", "replace")
    count = sum(1 for line in text.splitlines() if line.strip())
    part = RawPart(name="webngrams.ndjson", text=text, record_count=count)
    return RawPacket(source=SOURCE_ID, batch_id=batch_id, parts=(part,))


def _new_client() -> object:
    import httpx

    return httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS, follow_redirects=True)
