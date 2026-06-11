"""
Configuration package.

Importing this package loads ``backend/.env`` (if present) before any credential
lookups, so keys dropped in that file are visible process-wide.
"""

from .env_file import load_env_file

load_env_file()

from .credentials import (  # noqa: E402, F401
    get_provider_api_key,
    get_service_api_key,
    list_providers,
    set_provider_api_key,
)
from .settings import Settings, load_settings  # noqa: E402, F401
