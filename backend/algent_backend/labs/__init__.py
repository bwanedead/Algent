"""
Labs package groups domain-specific modules (algo lab, news hub, etc.).
"""
from importlib import import_module
from typing import Dict


_REGISTRY: Dict[str, str] = {
    "algo_lab": "algent_backend.labs.algo_lab",
    "news_hub": "algent_backend.labs.news_hub",
}


def load_lab(name: str):
    """Dynamically import a lab by name."""
    module_path = _REGISTRY.get(name)
    if not module_path:
        raise KeyError(f"lab '{name}' not registered")
    return import_module(module_path)
