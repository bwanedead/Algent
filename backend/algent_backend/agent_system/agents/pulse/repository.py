"""
Which Pulse store the running system uses — the single seam between Pulse logic and storage.

The file store by default (``database/flags.PULSE_BACKEND = "files"``: the worker server is the system of record and the
store is in the nightly ``data_backup`` mirror); Postgres only when the flag (or ``ALGENT_PULSE_BACKEND=postgres``) says so AND
``DATABASE_URL`` is configured and the driver is installed. Callers ask ``pulse_store()`` and
never construct a store themselves, so moving storage is a configuration change, not a code change.
Both implementations satisfy ``PulseRepository`` and are held to the same invariants: an
append-only, idempotent influence ledger; versioned definitions; one-way watch resolution.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Protocol

from .contracts import Event, Influence, Pulse, PulseDefinition, Situation, Watch
from .projection import PulseState


class PulseRepository(Protocol):
    def save_situation(self, situation: Situation) -> None: ...
    def situation(self, situation_id: str) -> Situation | None: ...
    def situations(self) -> list[Situation]: ...
    def create_pulse(self, pulse: Pulse) -> None: ...
    def add_definition(self, pulse_id: str, definition: PulseDefinition) -> int: ...
    def set_status(self, pulse_id: str, status: str) -> None: ...
    def pulse(self, pulse_id: str) -> Pulse | None: ...
    def pulses(self, situation_id: str | None = None) -> list[Pulse]: ...
    def append(self, influence: Influence) -> Influence: ...
    def log(self, pulse_id: str) -> list[Influence]: ...
    def state(self, pulse_id: str, *, as_of: str | None = None) -> PulseState: ...
    def record_event(self, event: Event) -> Event: ...
    def event(self, event_id: str) -> Event | None: ...
    def add_sightings(self, situation_id: str, rows: list[dict]) -> int: ...
    def sightings(self, situation_id: str) -> list[dict]: ...
    def propose(self, row: dict) -> None: ...
    def proposals(self) -> list[dict]: ...
    def save_watch(self, watch: Watch) -> None: ...
    def resolve_watch(self, watch_id: str, status: str, *, by: Any = None) -> Watch: ...
    def watches(self, situation_id: str | None = None) -> list[Watch]: ...


def database_configured() -> bool:
    if importlib.util.find_spec("psycopg") is None:
        return False
    try:
        from algent_backend.database.migrate import database_url

        return bool(database_url())
    except RuntimeError:
        return False


def backend() -> str:
    """"files" (the default: the server's ``pulse_store``, mirrored nightly) or "postgres": ``database/flags.PULSE_BACKEND``, overridable
    per process by ``ALGENT_PULSE_BACKEND``."""
    from algent_backend.database import flags

    return (os.environ.get("ALGENT_PULSE_BACKEND", "").strip().lower() or flags.PULSE_BACKEND)


def pulse_store() -> PulseRepository:
    """The live store: the file store (the system of record) unless the backend is switched to Postgres AND a database is configured."""
    if backend() in ("postgres", "pg") and database_configured():
        from .pg_store import PgPulseStore

        return PgPulseStore()
    from .store import PulseStore

    return PulseStore()
