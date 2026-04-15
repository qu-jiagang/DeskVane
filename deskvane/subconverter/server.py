import http.server
import threading
import traceback
import urllib.parse
import urllib.request

from .builder import build_clash_config
from .decoder import decode_subscription


class SubconverterHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path != "/sub":
            self.send_response(404)
            self.end_headers()
            return

        qs = dict(urllib.parse.parse_qsl(parsed_path.query))
        url = qs.get("url")

        if not url:
            self.send_error(400, "Missing 'url' parameter")
            return

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "DeskVane-Subconverter/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8", errors="ignore")

            proxies = decode_subscription(content)
            if not proxies:
                self.send_error(400, "No valid proxies found in subscription")
                return

            yaml_str = build_clash_config(proxies)

            self.send_response(200)
            self.send_header("Content-Type", "text/yaml; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="proxies.yaml"')
            self.end_headers()
            self.wfile.write(yaml_str.encode("utf-8"))

        except Exception as e:
            err_details = traceback.format_exc()
            self.send_error(500, f"Error generating sub: {e}\n\n{err_details}")

    def log_message(self, format: str, *args: str | int) -> None:
        pass


class SubconverterServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self.server: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.server:
            return
        
        # Avoid "Address already in use" if restarting quickly
        class ReusableServer(http.server.ThreadingHTTPServer):
            allow_reuse_address = True
            
        try:
            self.server = ReusableServer(("127.0.0.1", self.port), SubconverterHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except Exception:
            self.server = None
            pass

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
