"""
Minimal ``.env`` file loader (stdlib only).

Loads ``backend/.env`` into ``os.environ`` at config import so API keys can live
in one gitignored file. Real environment variables always win — values from the
file are applied with ``setdefault`` and never override what is already set.
This sits in front of the keyring fallback in ``credentials.py``, so the full
key precedence is: environment > .env file > keyring.

See ``backend/.env.example`` for the supported key names.
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/ — two levels up from this file (config/ -> algent_backend/ -> backend/).
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"


def load_env_file(path: Path | None = None) -> int:
    """Load ``KEY=VALUE`` lines from a .env file into the environment.

    Returns the number of variables applied. Missing file is fine (returns 0).
    Lines starting with ``#`` and blank lines are skipped; surrounding quotes on
    values are stripped; existing environment variables are never overridden.
    """
    env_path = path or DEFAULT_ENV_FILE
    if not env_path.is_file():
        return 0

    applied = 0
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value
            applied += 1
    return applied
