"""
Minimal HTTP entrypoint for Algent.

This uses the standard library so it can run without extra dependencies. Swap
for FastAPI/Flask/etc. once the API surface stabilizes.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Tuple

from algent_backend.config import (
    load_settings,
    list_providers,
    set_provider_api_key,
)


class _HealthHandler(BaseHTTPRequestHandler):
    """Responds to `/health` with a basic payload."""

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return {}
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802 (keep handler signature)
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {"status": "ok", "service": "algent-backend"})
            return
        self._send_json(404, {"status": "not_found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path == "/credentials":
            self._handle_credential_update()
            return
        self._send_json(404, {"status": "not_found", "path": self.path})

    def _handle_credential_update(self) -> None:
        payload = self._read_json()
        provider = (payload.get("provider") or "").lower()
        api_key = payload.get("api_key")
        allowed = list_providers()
        if provider not in allowed:
            self._send_json(
                400,
                {
                    "status": "error",
                    "message": f"Unknown provider '{provider}'. Expected one of {allowed}",
                },
            )
            return
        if not api_key:
            self._send_json(400, {"status": "error", "message": "api_key is required"})
            return
        try:
            set_provider_api_key(provider, api_key)
        except Exception as exc:  # pragma: no cover - depends on keyring availability
            self._send_json(500, {"status": "error", "message": str(exc)})
            return
        self._send_json(
            200,
            {"status": "ok", "message": f"Saved credential for {provider}"},
        )

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        """Suppress default noisy logging; replace with structured logging later."""
        return


def create_server(address: Tuple[str, int] | None = None) -> HTTPServer:
    """
    Build an HTTPServer instance using Settings defaults if no address provided.
    """
    if address is None:
        settings = load_settings()
        address = (settings.host, settings.port)
    return HTTPServer(address, _HealthHandler)


def run(address: Tuple[str, int] | None = None) -> None:
    """Start the simple health server."""
    server = create_server(address)
    host, port = server.server_address
    print(f"[algent] serving health endpoint at http://{host}:{port}/health")
    server.serve_forever()


if __name__ == "__main__":
    run()
