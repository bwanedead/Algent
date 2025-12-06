"""
Minimal HTTP entrypoint for Algent.

This uses the standard library so it can run without extra dependencies. Swap
for FastAPI/Flask/etc. once the API surface stabilizes.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Tuple


class _HealthHandler(BaseHTTPRequestHandler):
    """Responds to `/health` with a basic payload."""

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (keep handler signature)
        if self.path.rstrip("/") == "/health":
            self._send_json(200, {"status": "ok", "service": "algent-backend"})
            return
        self._send_json(404, {"status": "not_found", "path": self.path})

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        """Suppress default noisy logging; replace with structured logging later."""
        return


def create_server(address: Tuple[str, int] = ("127.0.0.1", 8000)) -> HTTPServer:
    """
    Build an HTTPServer instance.

    Replace this with a proper ASGI/WSGI app factory once the tech choice is made.
    """
    return HTTPServer(address, _HealthHandler)


def run(address: Tuple[str, int] = ("127.0.0.1", 8000)) -> None:
    """Start the simple health server."""
    server = create_server(address)
    host, port = address
    print(f"[algent] serving health endpoint at http://{host}:{port}/health")
    server.serve_forever()


if __name__ == "__main__":
    run()
