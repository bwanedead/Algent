"""Where the index lives: ``<ALGENT_CORPUS_STORE or corpus_store>/corpus.db`` (the registry's ``corpus_store``; derived, never backed up)."""

from __future__ import annotations

import os
from pathlib import Path

from . import flags

STORE_ENV = "ALGENT_CORPUS_STORE"
DEFAULT_DIR = "corpus_store"


def store_dir() -> Path:
    return Path(os.environ.get(STORE_ENV) or DEFAULT_DIR)


def db_file(store: Path | str | None = None) -> Path:
    return Path(store or store_dir()) / flags.DB_NAME


def available(store: Path | str | None = None) -> bool:
    """Whether an index has been built here (a consumer falls back to reading the record itself when it has not)."""
    return db_file(store).is_file()
