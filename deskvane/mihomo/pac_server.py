"""Lightweight HTTP server that serves the PAC script."""

from __future__ import annotations

import http.server
import threading
from typing import Callable

from ..log import get_logger

_logger = get_logger("pac_server")


class _PacHandler(http.server.BaseHTTPRequestHandler):
    """Handle ``GET /pac`` and ``GET /pac.js`` requests."""

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in ("/pac", "/pac.js"):
            self.send_response(404)
            self.end_headers()
            return

        generator: Callable[[], str] | None = getattr(self.server, "_pac_generator", None)
        if generator is None:
            self.send_error(503, "PAC generator not available")
            return

        try:
            script = generator()
        except Exception as exc:
            _logger.error("PAC generation failed: %s", exc)
            self.send_error(500, f"PAC generation error: {exc}")
            return

        body = script.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Silence the default stderr logging.
        pass


class PacServer:
    """Serve a PAC file over HTTP on ``127.0.0.1:<port>``.

    Parameters
    ----------
    port:
        TCP port to listen on.
    pac_generator:
        A callable that returns the PAC JavaScript as a string.
        Called on every request so the script is always up-to-date.
    """

    def __init__(self, port: int, pac_generator: Callable[[], str]) -> None:
        self.port = port
        self._pac_generator = pac_generator
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def pac_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/pac"

    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running():
            return True

        class _ReusableServer(http.server.ThreadingHTTPServer):
            allow_reuse_address = True

        try:
            server = _ReusableServer(("127.0.0.1", self.port), _PacHandler)
            server._pac_generator = self._pac_generator  # type: ignore[attr-defined]
            self._server = server
            self._thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._thread.start()
            _logger.info("PAC server started on port %d", self.port)
            return True
        except Exception as exc:
            _logger.error("PAC server start failed: %s", exc)
            self._server = None
            self._thread = None
            return False

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception as exc:
                _logger.debug("PAC server shutdown error: %s", exc)
            self._server = None
        if self._thread is not None:
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
            self._thread = None
        _logger.info("PAC server stopped")

    def restart(self, port: int | None = None) -> bool:
        """Stop and re-start the server, optionally on a new port."""
        self.stop()
        if port is not None:
            self.port = port
        return self.start()
