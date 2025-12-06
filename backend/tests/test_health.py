"""Validate health payload stays stable."""
from algent_backend.api import routes


def test_health_payload_shape():
    payload = routes.health()
    assert payload.get("status") == "ok"
    assert "service" in payload
