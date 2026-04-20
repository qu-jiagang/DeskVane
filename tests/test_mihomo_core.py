import signal
import socket
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from deskvane.mihomo.api import MihomoApiClient, MihomoRuntimeState
from deskvane.mihomo.core_manager import MihomoCoreManager
from deskvane.mihomo.manager import MihomoManager
from deskvane.mihomo.pac import rewrite_pac_proxy


class _Notifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def show(self, title: str, body: str = "", timeout_ms: int = 4000) -> None:
        self.messages.append((title, body))


def _cfg(tmpdir: str, backend: str = "core") -> SimpleNamespace:
    return SimpleNamespace(
        backend=backend,
        autostart=False,
        core_binary="mihomo",
        core_home_dir=tmpdir,
        subscription_url="",
        external_controller="127.0.0.1:19090",
        secret="top-secret",
        external_ui="/opt/metacubexd",
        external_ui_name="metacubexd",
        external_ui_url="",
        startup_timeout_s=8,
        tun_enabled=False,
        tun_direct_processes="",
        pac_enabled=False,
        pac_port=7893,
        pac_remote_url="",
        pac_proxy_domains="",
        pac_direct_domains="",
        pac_default_action="PROXY",
    )


def _sample_proxy(name: str = "Node-A") -> dict:
    return {
        "name": name,
        "type": "ss",
        "server": "127.0.0.1",
        "port": 8388,
        "cipher": "aes-128-gcm",
        "password": "pwd",
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_fake_mihomo_binary(base: Path) -> Path:
    script_path = base / "fake-mihomo"
    script_path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import signal
            import sys
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
            from pathlib import Path

            import yaml


            def main() -> None:
                args = sys.argv[1:]
                home_dir = Path(".")
                if "-d" in args:
                    idx = args.index("-d")
                    home_dir = Path(args[idx + 1])

                config = yaml.safe_load((home_dir / "config.yaml").read_text(encoding="utf-8")) or {}
                controller = str(config.get("external-controller", "127.0.0.1:9090"))
                if "://" in controller:
                    controller = controller.split("://", 1)[1]
                host, port = controller.rsplit(":", 1)
                state = {
                    "mode": str(config.get("mode", "rule")),
                    "mixed-port": config.get("mixed-port", 7890),
                    "socks-port": config.get("socks-port"),
                }
                proxies = {
                    "DESKVANE-PROXY": {
                        "type": "Selector",
                        "now": "Node-A",
                        "all": ["Node-A", "Node-B", "DIRECT"],
                    }
                }

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, fmt: str, *args) -> None:
                        return None

                    def _send(self, code: int, payload=None) -> None:
                        self.send_response(code)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        if payload is not None:
                            self.wfile.write(json.dumps(payload).encode("utf-8"))

                    def do_GET(self) -> None:
                        if self.path == "/configs":
                            self._send(200, state)
                            return
                        if self.path == "/proxies":
                            self._send(200, {"proxies": proxies})
                            return
                        if self.path == "/version":
                            self._send(200, {"version": "test"})
                            return
                        self._send(200, {"hello": "mihomo"})

                    def do_PATCH(self) -> None:
                        if self.path != "/configs":
                            self._send(404, {"error": "not found"})
                            return
                        length = int(self.headers.get("Content-Length", "0"))
                        payload = json.loads(self.rfile.read(length) or b"{}")
                        state["mode"] = payload.get("mode", state["mode"])
                        self._send(204)

                    def do_PUT(self) -> None:
                        self._send(204)

                server = ThreadingHTTPServer((host, int(port)), Handler)

                def _shutdown(*_args) -> None:
                    server.shutdown()

                signal.signal(signal.SIGTERM, _shutdown)
                signal.signal(signal.SIGINT, _shutdown)
                server.serve_forever()


            if __name__ == "__main__":
                main()
            """
        ),
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    return script_path


def _write_fast_exit_binary(base: Path, exit_code: int = 23) -> Path:
    script_path = base / "fast-exit-mihomo"
    script_path.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            echo "fatal: bad config" >&2
            exit {exit_code}
            """
        ),
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    return script_path


def test_core_manager_syncs_runtime_config() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        path = manager.ensure_runtime_config()

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["external-controller"] == "127.0.0.1:19090"
        assert data["secret"] == "top-secret"
        assert data["external-ui"] == "/opt/metacubexd"
        assert data["external-ui-name"] == "metacubexd"
        assert data["mixed-port"] == 7890


def test_core_manager_preserves_existing_proxy_ports() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump({"mixed-port": 17890, "mode": "global"}),
            encoding="utf-8",
        )

        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        path = manager.ensure_runtime_config()

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["mixed-port"] == 17890
        assert data["mode"] == "global"
        assert data["external-controller"] == "127.0.0.1:19090"


def test_core_manager_preserves_custom_config_when_writing_provider() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.tun_enabled = True
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "mixed-port": 17890,
                    "dns": {"enable": True},
                    "tun": {"enable": True},
                    "proxy-groups": [{"name": "CUSTOM", "type": "select", "proxies": ["DIRECT"]}],
                    "rules": ["MATCH,CUSTOM"],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        manager.write_subscription_provider([_sample_proxy()], "https://example.com/sub")

        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["mixed-port"] == 17890
        assert data["dns"]["enable"] is True
        assert data["dns"]["default-nameserver"] == ["223.5.5.5", "1.1.1.1"]
        assert data["tun"]["enable"] is True
        assert data["rules"] == ["MATCH,CUSTOM"]
        assert any(group["name"] == "CUSTOM" for group in data["proxy-groups"])
        assert any(group["name"] == "DESKVANE-PROXY" for group in data["proxy-groups"])
        assert data["proxy-providers"]["deskvane-subscription"]["path"] == "providers/deskvane-subscription.yaml"

        provider_data = yaml.safe_load((Path(temp_dir) / "providers" / "deskvane-subscription.yaml").read_text(encoding="utf-8"))
        assert provider_data["proxies"][0]["name"] == "Node-A"


def test_rewrite_pac_proxy_rewrites_hostname_based_proxy_targets() -> None:
    pac_js = 'function FindProxyForURL(){ return "PROXY proxy.example.com:8080; SOCKS5 gateway.example.net:1080; DIRECT"; }'

    rewritten = rewrite_pac_proxy(pac_js, 7890)

    assert "proxy.example.com:8080" not in rewritten
    assert "gateway.example.net:1080" not in rewritten
    assert rewritten.count("PROXY 127.0.0.1:7890") == 2


def test_core_manager_remote_pac_mode_removes_managed_pac_rules() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.pac_enabled = True
        cfg.pac_remote_url = "https://example.com/pac.js"
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "rules": [
                        "DOMAIN-SUFFIX,old-proxy.example,DESKVANE-PROXY # pac-proxy",
                        "DOMAIN-SUFFIX,old-direct.example,DIRECT # pac-direct",
                        "MATCH,DESKVANE-PROXY",
                    ]
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        data = yaml.safe_load(manager.ensure_runtime_config().read_text(encoding="utf-8"))

        assert data["rules"] == ["MATCH,DESKVANE-PROXY"]


def test_core_manager_removes_managed_dns_defaults_when_tun_disabled() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "mixed-port": 17890,
                    "tun": {
                        "enable": False,
                        "stack": "mixed",
                        "auto-route": True,
                        "auto-detect-interface": True,
                    },
                    "dns": {
                        "enable": True,
                        "default-nameserver": [
                            "223.5.5.5",
                            "1.1.1.1",
                        ],
                        "listen": ":1053",
                        "enhanced-mode": "fake-ip",
                        "fake-ip-range": "198.18.0.1/16",
                        "nameserver": [
                            "https://dns.alidns.com/dns-query",
                            "https://doh.pub/dns-query",
                        ],
                        "fallback": [
                            "https://1.0.0.1/dns-query",
                            "https://dns.google/dns-query",
                        ],
                    },
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        path = manager.ensure_runtime_config()

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "dns" not in data
        assert data["tun"]["enable"] is False


def test_core_manager_switch_mode_persists_runtime_config() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump({"mode": "rule"}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        with mock.patch.object(MihomoApiClient, "switch_mode", return_value=True) as switch_mode:
            assert manager.switch_mode("global") is True

        switch_mode.assert_called_once_with("global")
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["mode"] == "global"


def test_core_manager_writes_process_bypass_rules_and_find_process_mode() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.tun_enabled = True
        cfg.tun_direct_processes = "ToDesk"
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        with mock.patch(
            "deskvane.mihomo.core_manager.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="ToDesk\nToDesk_Service\n",
                stderr="",
            ),
        ):
            data = yaml.safe_load(manager.ensure_runtime_config().read_text(encoding="utf-8"))

        assert data["find-process-mode"] == "always"
        assert data["rules"][0] == "PROCESS-NAME,ToDesk,DIRECT"
        assert data["rules"][1] == "PROCESS-NAME,ToDesk_Service,DIRECT"
        assert data["rules"][2] == "DOMAIN-SUFFIX,todesk.com,DIRECT"


def test_core_manager_removes_legacy_process_wildcard_rules() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.tun_enabled = True
        cfg.tun_direct_processes = "ToDesk"
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "rules": [
                        "PROCESS-NAME,ToDesk,DIRECT",
                        "PROCESS-NAME-WILDCARD,*ToDesk*,DIRECT",
                        "MATCH,PROXY",
                    ]
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        with mock.patch(
            "deskvane.mihomo.core_manager.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="ToDesk\nToDesk_Service\n",
                stderr="",
            ),
        ):
            data = yaml.safe_load(manager.ensure_runtime_config().read_text(encoding="utf-8"))

        assert data["rules"][:2] == [
            "PROCESS-NAME,ToDesk,DIRECT",
            "PROCESS-NAME,ToDesk_Service,DIRECT",
        ]
        assert data["rules"][2] == "DOMAIN-SUFFIX,todesk.com,DIRECT"


def test_core_manager_removes_managed_domain_bypass_rule_when_process_list_is_cleared() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.tun_enabled = False
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "rules": [
                        "PROCESS-NAME,ToDesk,DIRECT",
                        "PROCESS-NAME,ToDesk_Service,DIRECT",
                        "DOMAIN-SUFFIX,todesk.com,DIRECT",
                        "MATCH,PROXY",
                    ]
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        data = yaml.safe_load(manager.ensure_runtime_config().read_text(encoding="utf-8"))

        assert data["rules"] == ["MATCH,PROXY"]


def test_core_manager_bootstraps_rules_when_main_config_missing() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        manager.write_subscription_provider([_sample_proxy()], "https://example.com/sub")

        data = yaml.safe_load((Path(temp_dir) / "config.yaml").read_text(encoding="utf-8"))
        assert data["proxy-providers"]["deskvane-subscription"]["type"] == "file"
        assert any(group["name"] == "DESKVANE-AUTO" for group in data["proxy-groups"])
        assert any(group["name"] == "DESKVANE-PROXY" for group in data["proxy-groups"])
        assert data["rules"][-1] == "MATCH,DESKVANE-PROXY"


def test_core_manager_syncs_same_name_inline_proxies_from_provider() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "proxies": [
                        {
                            "name": "Node-A",
                            "type": "ss",
                            "server": "1.1.1.1",
                            "port": 1000,
                            "cipher": "aes-128-gcm",
                            "password": "old",
                        },
                        {
                            "name": "Custom-Node",
                            "type": "ss",
                            "server": "9.9.9.9",
                            "port": 9000,
                            "cipher": "aes-128-gcm",
                            "password": "keep",
                        },
                    ],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        manager.write_subscription_provider(
            [
                {
                    "name": "Node-A",
                    "type": "ss",
                    "server": "2.2.2.2",
                    "port": 2000,
                    "cipher": "aes-256-gcm",
                    "password": "new",
                }
            ],
            "https://example.com/sub",
        )

        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        inline_map = {item["name"]: item for item in data["proxies"]}
        assert inline_map["Node-A"]["server"] == "2.2.2.2"
        assert inline_map["Node-A"]["password"] == "new"
        assert inline_map["Custom-Node"]["server"] == "9.9.9.9"


def test_core_manager_starts_real_process_and_supports_reload() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.external_controller = f"127.0.0.1:{_free_port()}"
        cfg.core_binary = str(_write_fake_mihomo_binary(Path(temp_dir)))
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "mixed-port": _free_port(),
                    "socks-port": _free_port(),
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        assert manager.start() is True

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            status = manager.get_status()
            if status.api_ready:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("fake mihomo API was not ready in time")

        status = manager.get_status()
        assert status.running is True
        assert status.api_ready is True
        assert manager.reload_config() is True
        manager.stop()
        assert manager.is_running() is False


def test_core_manager_rejects_tun_enable_without_cap_net_admin() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        fake_binary = Path(temp_dir) / "mihomo"
        fake_binary.write_text("", encoding="utf-8")

        real_exists = Path.exists

        def fake_exists(path: Path) -> bool:
            if str(path) == "/dev/net/tun":
                return True
            return real_exists(path)

        def fake_which(name: str) -> str | None:
            if name == "mihomo":
                return str(fake_binary)
            if name == "getcap":
                return "/usr/sbin/getcap"
            return None

        with mock.patch("deskvane.mihomo.core_manager.Path.exists", new=fake_exists), \
             mock.patch("deskvane.mihomo.core_manager.os.geteuid", return_value=1000), \
             mock.patch("deskvane.mihomo.core_manager.shutil.which", side_effect=fake_which), \
             mock.patch("deskvane.mihomo.core_manager.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")), \
             mock.patch.object(MihomoApiClient, "switch_tun", return_value=True) as switch_tun:
            assert manager.switch_tun(True) is False

        switch_tun.assert_not_called()
        assert "CAP_NET_ADMIN" in manager.get_status().last_error


def test_core_manager_reports_runtime_tun_error_even_if_api_accepts_request() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        (Path(temp_dir) / "logs").mkdir(parents=True, exist_ok=True)
        (Path(temp_dir) / "logs" / "core.stdout.log").write_text("", encoding="utf-8")
        runtime = MihomoRuntimeState(
            api_ready=True,
            controller="http://127.0.0.1:19090",
            mode="rule",
            mixed_port=7890,
            port=None,
            socks_port=7891,
            tun_enabled=True,
            groups=[],
        )

        with mock.patch.object(manager, "_tun_preflight_error", return_value=""), \
             mock.patch.object(MihomoApiClient, "switch_tun", return_value=True), \
             mock.patch.object(MihomoApiClient, "get_runtime_state", side_effect=[runtime, runtime]), \
             mock.patch.object(
                 manager,
                 "_read_tun_error_since",
                 side_effect=["", "Start TUN listening error: configure tun interface: operation not permitted"],
             ), \
             mock.patch("deskvane.mihomo.core_manager.time.sleep", return_value=None), \
             mock.patch("deskvane.mihomo.core_manager.time.monotonic", side_effect=[0.0, 0.1, 0.2]):
            assert manager.switch_tun(True) is False

        assert "operation not permitted" in manager.get_status().last_error


def test_core_manager_start_fails_fast_when_proxy_ports_are_occupied() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.core_binary = str(_write_fake_mihomo_binary(Path(temp_dir)))
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump({"mixed-port": 17890, "socks-port": 17891, "external-controller": f"127.0.0.1:{_free_port()}"}),
            encoding="utf-8",
        )

        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("127.0.0.1", 17890))
        occupied.listen(1)
        try:
            notifier = _Notifier()
            manager = MihomoCoreManager(notifier, lambda: cfg)
            assert manager.start() is False
        finally:
            occupied.close()

        status = manager.get_status()
        assert "端口已被占用" in status.last_error
        assert "17890" in status.last_error
        assert notifier.messages[-1][0] == "启动 Mihomo Core 失败"


def test_core_manager_start_fails_fast_when_process_exits_immediately() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.external_controller = f"127.0.0.1:{_free_port()}"
        cfg.core_binary = str(_write_fast_exit_binary(Path(temp_dir)))
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "mixed-port": _free_port(),
                    "socks-port": _free_port(),
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        notifier = _Notifier()
        manager = MihomoCoreManager(notifier, lambda: cfg)

        assert manager.start() is False

        status = manager.get_status()
        assert "exit code 23" in status.last_error
        assert "fatal: bad config" in status.last_error
        assert notifier.messages[-1][0] == "启动 Mihomo Core 失败"


def test_core_manager_status_treats_healthy_api_as_running() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        with mock.patch.object(MihomoApiClient, "is_healthy", return_value=True), \
             mock.patch(
                 "deskvane.mihomo.core_manager.subprocess.run",
                 return_value=SimpleNamespace(
                     returncode=0,
                     stdout=f" 4321 /usr/bin/mihomo -d {temp_dir}\n",
                     stderr="",
                 ),
             ):
            status = manager.get_status()

        assert status.running is True
        assert status.api_ready is True
        assert status.pid == 4321


def test_core_manager_start_skips_spawn_when_existing_core_is_already_running() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        with mock.patch.object(MihomoApiClient, "is_healthy", return_value=True), \
             mock.patch(
                 "deskvane.mihomo.core_manager.subprocess.run",
                 return_value=SimpleNamespace(
                     returncode=0,
                     stdout=f" 4321 /usr/bin/mihomo -d {temp_dir}\n",
                     stderr="",
                 ),
             ), \
             mock.patch("deskvane.mihomo.core_manager.subprocess.Popen") as popen:
            assert manager.start() is True

        popen.assert_not_called()


def test_core_manager_stop_terminates_untracked_external_core() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        with mock.patch(
            "deskvane.mihomo.core_manager.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout=f" 4321 /usr/bin/mihomo -d {temp_dir}\n",
                stderr="",
            ),
        ), \
             mock.patch("deskvane.mihomo.core_manager.os.kill") as kill, \
             mock.patch.object(manager, "_pid_exists", side_effect=[True, False]):
            manager.stop()

        kill.assert_called_once()
        assert kill.call_args.args == (4321, signal.SIGTERM)


def test_core_manager_expands_matching_service_process_for_tun_bypass() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        cfg.tun_enabled = True
        cfg.tun_direct_processes = "ToDesk"
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.dump({"rules": ["MATCH,PROXY"]}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if cmd == ["ps", "-eo", "comm="]:
                return SimpleNamespace(returncode=0, stdout="ToDesk\nToDesk_Service\n", stderr="")
            return real_run(cmd, *args, **kwargs)

        with mock.patch("deskvane.mihomo.core_manager.subprocess.run", side_effect=fake_run):
            path = manager.ensure_runtime_config()

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["rules"][:2] == [
            "PROCESS-NAME,ToDesk,DIRECT",
            "PROCESS-NAME,ToDesk_Service,DIRECT",
        ]


def test_core_manager_refresh_tun_bypass_connections_closes_matching_process_and_domain_entries() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir)
        manager = MihomoCoreManager(_Notifier(), lambda: cfg)

        def fake_run(cmd, *args, **kwargs):
            if cmd == ["ps", "-eo", "comm="]:
                return SimpleNamespace(returncode=0, stdout="ToDesk\nToDesk_Service\n", stderr="")
            raise AssertionError(f"unexpected subprocess.run call: {cmd}")

        connections = [
            {
                "id": "conn-process",
                "metadata": {"process": "ToDesk", "host": "relay.example.com"},
            },
            {
                "id": "conn-domain",
                "metadata": {"process": "", "host": "authds.todesk.com", "uid": 0},
            },
            {
                "id": "conn-other-domain",
                "metadata": {"process": "", "host": "notodesk.com", "uid": 0},
            },
        ]

        with mock.patch("deskvane.mihomo.core_manager.subprocess.run", side_effect=fake_run), \
             mock.patch.object(MihomoApiClient, "get_connections", return_value=connections), \
             mock.patch.object(MihomoApiClient, "close_connection", return_value=True) as close_connection:
            closed = manager.refresh_tun_bypass_connections("ToDesk")

        assert closed == 2
        assert close_connection.call_args_list == [
            mock.call("conn-process"),
            mock.call("conn-domain"),
        ]


def test_mihomo_manager_routes_start_to_core_backend() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cfg = _cfg(temp_dir, backend="core")
        manager = MihomoManager(_Notifier(), lambda: cfg)

        with mock.patch.object(manager.core, "start", return_value=True) as core_start, \
             mock.patch.object(manager.party, "start", return_value=True) as party_start, \
             mock.patch.object(manager.party, "stop") as party_stop:
            assert manager.start() is True

        core_start.assert_called_once()
        party_start.assert_not_called()
        party_stop.assert_called_once()
