"""
Where each store lives: one lazy resolver per directory, each reusing the owning module's own ``store_dir()`` / ``root()`` so the registry can never
disagree with the code that writes. Nothing here is imported until a resolver is called.
"""

from __future__ import annotations

from pathlib import Path

from .model import REPO, env_dir


def profile() -> Path:
    from algent_backend.agent_system.agents.research.store import JsonProfileStore

    return JsonProfileStore().root


def pulse() -> Path:
    from algent_backend.agent_system.agents.pulse import PulseStore

    return PulseStore().root


def intel() -> Path:
    from algent_backend.agent_system.agents.intel.heat import store_dir

    return store_dir()


def statements() -> Path:
    from algent_backend.agent_system.agents.statements.store import store_dir

    return store_dir()


def actors() -> Path:
    from algent_backend.actors.store import store_dir

    return store_dir()


def instruments() -> Path:
    from algent_backend.instruments.store import store_dir

    return store_dir()


def ai_benchmarks() -> Path:
    from algent_backend.ai_benchmarks.store import root

    return root()


def geoledger() -> Path:
    from algent_backend.geoledger.store import root

    return root()


def sanctions() -> Path:
    from algent_backend.sanctions.store import root

    return root()


def conflict() -> Path:
    from algent_backend.conflict.store import root

    return root()


def gnss() -> Path:
    from algent_backend.gnss.store import root

    return root()


def calendar() -> Path:
    from algent_backend.lookahead.store import root

    return root()


def markets() -> Path:
    from algent_backend.markets.store import root

    return root()


def maritime() -> Path:
    from algent_backend.maritime.store import root

    return root()


def maritime_daily() -> Path:
    return maritime() / "daily"            # the daily ship summaries; the raw positions and event log beside it are GB-scale and bounded by retention


def live() -> Path:
    from algent_backend.live.store import root

    return root()


def library() -> Path:
    from algent_backend.library.store import store_dir

    return store_dir()


def corpus() -> Path:
    from algent_backend.corpus.paths import store_dir

    return store_dir()


def views() -> Path:
    from algent_backend.views.publish import store_dir

    return store_dir()


def runs() -> Path:
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    return runs_data_root()


def fetch_cache() -> Path:
    from algent_backend.agent_system.tools.sourcing.depth.fetch_content import cache_dir

    return cache_dir()


def ingestion() -> Path:
    from algent_backend.data_ingestion.cli._shared import ingestion_dir

    return ingestion_dir()


draft = env_dir("ALGENT_DRAFT_STORE", "draft_store")
treatment = env_dir("ALGENT_TREATMENT_STORE", "treatment_store")
lead = env_dir("ALGENT_LEAD_STORE", "lead_store")
retrieval = env_dir("ALGENT_RETRIEVAL_STORE", "retrieval_store")


def _site(*parts: str) -> Path:
    from algent_backend.publishing import site_git

    return site_git.live_site_dir(REPO).joinpath(*parts)


def site_articles() -> Path:
    return _site("content", "articles")


def site_intel() -> Path:
    return _site("content", "intel")


def site_radar() -> Path:
    return _site("content", "radar")


def site_data() -> Path:
    return _site("public", "data")
