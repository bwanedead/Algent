"""
Global settings representation.
"""

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 43145


@dataclass
class Settings:
    """Minimal settings placeholder."""

    host: str = os.getenv("ALGENT_HOST", DEFAULT_HOST)
    port: int = int(os.getenv("ALGENT_PORT", str(DEFAULT_PORT)))
    environment: str = os.getenv("ALGENT_ENV", "dev")


def load_settings() -> Settings:
    """Load settings from environment or defaults."""
    return Settings()
