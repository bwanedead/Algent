"""The operator's journal, ``~/ops-log.md``: one dated heading and one bullet per entry. Shared by every unattended job that reports there."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def append(who: str, line: str, *, home: Path | None = None, now: datetime | None = None) -> None:
    """Never raises: a journal that cannot be written must not fail the job it describes."""
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%MZ")
    try:
        with ((home or Path.home()) / "ops-log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {stamp} · {who}\n- {line}\n")
    except OSError:
        pass
