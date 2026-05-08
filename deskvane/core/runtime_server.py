from __future__ import annotations

import http.server
import json
import os
import threading
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ..log import get_logger
from .runtime_api import RuntimeApi


_logger = get_logger("runtime-server")


class RuntimeHttpServer:
    """Small localhost HTTP bridge for future Tauri sidecar calls."""

    def __init__(self, api: RuntimeApi, host: str = "127.0.0.1", port: int | None = None) -> None:
        self.api = api
        self.host = host
        self.port = int(port if port is not None else os.environ.get("DESKVANE_RUNTIME_PORT", "37655"))
        self.server: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        port = self.port
        if self.server is not None:
            port = int(self.server.server_address[1])
        return f"http://{self.host}:{port}"

    @property
    def is_running(self) -> bool:
        return self.server is not None

    def start(self) -> None:
        if self.server is not None:
            return

        api = self.api

        class ReusableServer(http.server.ThreadingHTTPServer):
            allow_reuse_address = True

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/health":
                    self._send_json(200, api.health())
                    return
                if path == "/state":
                    self._send_json(200, api.get_state())
                    return
                if path == "/actions":
                    self._send_json(200, {"actions": list(api.action_names())})
                    return
                if path == "/config":
                    self._send_json(200, api.get_config())
                    return
                if path == "/events":
                    try:
                        params = parse_qs(parsed.query)
                        after_id = self._optional_int(params.get("after_id", [None])[0])
                        limit = self._optional_int(params.get("limit", [None])[0])
                    except ValueError as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    self._send_json(200, {"events": api.get_events(after_id=after_id, limit=limit)})
                    return
                if path == "/clipboard/history":
                    try:
                        self._send_json(200, api.get_clipboard_history())
                    except Exception as exc:
                        self._send_json(500, {"error": str(exc)})
                    return
                self._send_json(404, {"error": "not_found"})

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._send_cors_headers()
                self.send_header("Access-Control-Allow-Methods", "GET, PATCH, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_PATCH(self) -> None:
                path = urlparse(self.path).path
                if path != "/config":
                    self._send_json(404, {"error": "not_found"})
                    return

                try:
                    payload = self._read_json_body()
                    config = api.update_config(payload)
                except KeyError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                except Exception as exc:
                    _logger.exception("runtime config update failed")
                    self._send_json(500, {"error": str(exc)})
                    return
                self._send_json(200, config)

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                if path == "/translator/translate":
                    try:
                        payload = self._read_json_body()
                        text = payload.get("text", "") if isinstance(payload, dict) else ""
                        if not isinstance(text, str) or not text.strip():
                            self._send_json(400, {"error": "text is required"})
                            return
                        result = api.translate_text(text)
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    except RuntimeError as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    except Exception as exc:
                        _logger.exception("runtime translation failed")
                        self._send_json(500, {"error": str(exc)})
                        return
                    self._send_json(200, result)
                    return

                if path == "/clipboard/select":
                    try:
                        payload = self._read_json_body()
                        index = payload.get("index", -1) if isinstance(payload, dict) else -1
                        result = api.select_clipboard_history_item(int(index))
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    except RuntimeError as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    except Exception as exc:
                        _logger.exception("runtime clipboard selection failed")
                        self._send_json(500, {"error": str(exc)})
                        return
                    self._send_json(200, result)
                    return

                prefix = "/actions/"
                if not path.startswith(prefix):
                    self._send_json(404, {"error": "not_found"})
                    return

                action_name = unquote(path[len(prefix):])
                try:
                    payload = self._read_json_body()
                    args = payload.get("args", []) if isinstance(payload, dict) else []
                    if not isinstance(args, list):
                        self._send_json(400, {"error": "invalid_args"})
                        return
                    api.dispatch_action(action_name, *args)
                except KeyError as exc:
                    self._send_json(404, {"error": str(exc)})
                    return
                except Exception as exc:
                    _logger.exception("runtime action failed: %s", action_name)
                    self._send_json(500, {"error": str(exc)})
                    return
                self._send_json(200, {"ok": True})

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _read_json_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))

            def _send_json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Private-Network", "true")

            @staticmethod
            def _optional_int(value: str | None) -> int | None:
                if value is None or value == "":
                    return None
                return int(value)

        try:
            self.server = ReusableServer((self.host, self.port), Handler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            _logger.info("runtime API listening on %s", self.base_url)
        except OSError as exc:
            self.server = None
            self.thread = None
            _logger.warning("runtime API unavailable on %s:%s: %s", self.host, self.port, exc)

    def stop(self) -> None:
        server = self.server
        if server is not None:
            server.shutdown()
            server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
