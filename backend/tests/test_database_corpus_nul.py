"""Postgres JSONB rejects NUL; the corpus loader drops it at the database edge (profile files keep exact bytes)."""

import json

from algent_backend.database.corpus import _jsonb


def test_nul_is_dropped_and_the_rest_survives() -> None:
    out = _jsonb({"claim": "33.2 million tons\x00 per year", "n": 1})
    assert "\u0000" not in out and json.loads(out) == {"claim": "33.2 million tons per year", "n": 1}
