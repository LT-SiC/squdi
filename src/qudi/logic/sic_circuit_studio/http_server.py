"""Loopback HTTP server for the SiC Circuit Studio frontend and export API."""
from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from .backend.circuit import CircuitError, VERSION, export, normalize, summarize

LOGGER = logging.getLogger(__name__)
FRONTEND_ROOT = Path(__file__).resolve().parent / "frontend"
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/measurement_extras.js": "measurement_extras.js",
    "/styles.css": "styles.css",
    "/favicon.svg": "favicon.svg",
    "/startup.html": "startup.html",
    "/startup.js": "startup.js",
    "/manifest.webmanifest": "manifest.webmanifest",
    "/icon-192.png": "icon-192.png",
    "/icon-512.png": "icon-512.png",
}
MAX_BODY = 1024 * 1024


class StudioHTTPServer(ThreadingHTTPServer):
    """Threaded server whose listener is always restricted to loopback."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, request_handler):
        self._serving = threading.Event()
        super().__init__(server_address, request_handler)

    def service_actions(self) -> None:
        self._serving.set()

    def wait_until_serving(self, timeout: float = 5) -> bool:
        return self._serving.wait(timeout)


def create_server(
    port: int = 8765,
    on_qasm_export: Callable[[dict, str], None] | None = None,
) -> StudioHTTPServer:
    """Create, but do not start, the frontend/API server on IPv4 loopback."""

    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status: int, data: bytes, mime: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self'; script-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status: int, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_bytes(status, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/health":
                self.send_json(
                    200,
                    {"ok": True, "version": VERSION, "hardware_connected": False},
                )
                return
            if path not in STATIC_FILES:
                self.send_json(404, {"error": "Not found"})
                return

            asset = FRONTEND_ROOT / STATIC_FILES[path]
            body = asset.read_bytes()
            mime = mimetypes.guess_type(str(asset))[0] or "application/octet-stream"
            self.send_bytes(200, body, mime)

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/export":
                self.send_json(404, {"error": "Not found"})
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self.send_json(415, {"error": "Expected application/json"})
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    self.send_json(413, {"error": "Request too large or empty"})
                    return
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise CircuitError("Request body must be a JSON object.")
                circuit = normalize(payload.get("circuit"))
                fmt = payload.get("format", "qasm")
                code = export(circuit, fmt)
            except (CircuitError, ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
                self.send_json(400, {"error": str(error)})
                return

            if fmt == "qasm" and on_qasm_export is not None:
                on_qasm_export(circuit, code)
            self.send_json(
                200,
                {"circuit": circuit, "code": code, "summary": summarize(circuit)},
            )

        def log_message(self, format_string: str, *args) -> None:
            LOGGER.debug("Studio HTTP request: " + format_string, *args)

    return StudioHTTPServer(("127.0.0.1", port), Handler)
