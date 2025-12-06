"""
Configuration defaults and helpers.

Avoid hard-coding environment details; this module can grow into a settings
system once deployment targets are known.
"""
from dataclasses import dataclass
import os


@dataclass
class Settings:
    """Minimal settings placeholder."""

    host: str = os.getenv("ALGENT_HOST", "127.0.0.1")
    port: int = int(os.getenv("ALGENT_PORT", "8000"))


def load_settings() -> Settings:
    """Load settings from environment or defaults."""
    # TODO: integrate dotenv or config files when needed.
    return Settings()

