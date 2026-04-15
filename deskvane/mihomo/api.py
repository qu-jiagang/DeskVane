from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CONTROLLER = "127.0.0.1:9090"
API_URL = f"http://{DEFAULT_CONTROLLER}"
DEFAULT_DELAY_TEST_URL = "https://www.gstatic.com/generate_204"


def _normalize_controller(controller: str) -> str:
    normalized = controller.strip() or DEFAULT_CONTROLLER
    if not normalized.startswith(("http://", "https://")):
        normalized = f"http://{normalized}"
    return normalized.rstrip("/")


@dataclass(slots=True)
class MihomoApiClient:
    controller: str = DEFAULT_CONTROLLER
    secret: str = ""
    timeout_s: int = 3

    @property
    def base_url(self) -> str:
        return _normalize_controller(self.controller)

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        req = urllib.request.Request(f"{self.base_url}{path}", method=method)
        req.add_header("Accept", "application/json")
        secret = self.secret.strip()
        if secret:
            req.add_header("Authorization", f"Bearer {secret}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(data).encode("utf-8")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                content = resp.read()
                if content:
                    return json.loads(content)
                return True
        except Exception:
            return None

    def get_version(self) -> dict[str, Any]:
        resp = self._request("GET", "/version")
        return resp if isinstance(resp, dict) else {}

    def is_healthy(self) -> bool:
        return bool(self.get_config())

    def get_proxies(self) -> dict[str, Any]:
        resp = self._request("GET", "/proxies")
        if resp and isinstance(resp, dict):
            return resp.get("proxies", {})
        return {}

    def get_connections(self) -> list[dict[str, Any]]:
        resp = self._request("GET", "/connections")
        if resp and isinstance(resp, dict):
            connections = resp.get("connections")
            if isinstance(connections, list):
                return connections
        return []

    def close_connection(self, connection_id: str) -> bool:
        q_id = urllib.parse.quote(connection_id.strip(), safe="")
        return self._request("DELETE", f"/connections/{q_id}") is not None

    def switch_proxy(self, group_name: str, proxy_name: str) -> bool:
        q_group = urllib.parse.quote(group_name)
        return self._request("PUT", f"/proxies/{q_group}", {"name": proxy_name}) is not None

    def test_proxy_delay(
        self,
        proxy_name: str,
        test_url: str = DEFAULT_DELAY_TEST_URL,
        timeout_ms: int = 5000,
    ) -> int | None:
        q_name = urllib.parse.quote(proxy_name)
        q_url = urllib.parse.quote(test_url.strip() or DEFAULT_DELAY_TEST_URL, safe="")
        resp = self._request(
            "GET",
            f"/proxies/{q_name}/delay?timeout={int(timeout_ms)}&url={q_url}",
        )
        if isinstance(resp, dict):
            return _to_int(resp.get("delay"))
        return None

    def switch_mode(self, mode: str) -> bool:
        return self._request("PATCH", "/configs", {"mode": mode}) is not None

    def switch_tun(self, enabled: bool) -> bool:
        return self._request("PATCH", "/configs", {"tun": {"enable": enabled}}) is not None

    def get_config(self) -> dict[str, Any]:
        resp = self._request("GET", "/configs")
        return resp if isinstance(resp, dict) else {}

    def reload_config(self) -> bool:
        return self._request("PUT", "/configs?force=true", {"path": "", "payload": ""}) is not None

    def get_runtime_state(self) -> "MihomoRuntimeState":
        config = self.get_config()
        proxies = self.get_proxies()

        groups: list[MihomoProxyGroup] = []
        for name, payload in proxies.items():
            if not isinstance(payload, dict):
                continue
            all_candidates = payload.get("all")
            if not isinstance(all_candidates, list) or not all_candidates:
                continue
            candidate_names = [str(item) for item in all_candidates if str(item).strip()]
            candidate_delays = {
                candidate: delay
                for candidate in candidate_names
                if (
                    delay := _extract_history_delay(proxies.get(candidate))
                ) is not None
            }
            groups.append(
                MihomoProxyGroup(
                    name=str(name),
                    group_type=str(payload.get("type", "")),
                    current=str(payload.get("now", "")),
                    candidates=candidate_names,
                    test_url=str(payload.get("testUrl", "") or ""),
                    last_delay_ms=_extract_history_delay(payload),
                    candidate_delays=candidate_delays,
                )
            )

        tun_cfg = config.get("tun")
        tun_enabled = bool(
            isinstance(tun_cfg, dict) and tun_cfg.get("enable")
        )

        return MihomoRuntimeState(
            api_ready=bool(config),
            controller=self.base_url,
            mode=str(config.get("mode", "")),
            mixed_port=_to_int(config.get("mixed-port")),
            port=_to_int(config.get("port")),
            socks_port=_to_int(config.get("socks-port")),
            tun_enabled=tun_enabled,
            groups=groups,
        )


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class MihomoProxyGroup:
    name: str
    group_type: str
    current: str
    candidates: list[str]
    test_url: str = ""
    last_delay_ms: int | None = None
    candidate_delays: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class MihomoRuntimeState:
    api_ready: bool
    controller: str
    mode: str
    mixed_port: int | None
    port: int | None
    socks_port: int | None
    tun_enabled: bool
    groups: list[MihomoProxyGroup]


def _extract_history_delay(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None

    history = payload.get("history")
    if isinstance(history, list):
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            delay = _to_int(item.get("delay"))
            if delay is not None:
                return delay

    return _to_int(payload.get("delay"))


def _default_client() -> MihomoApiClient:
    return MihomoApiClient(controller=DEFAULT_CONTROLLER)


def get_proxies() -> dict[str, Any]:
    return _default_client().get_proxies()


def switch_proxy(group_name: str, proxy_name: str) -> bool:
    return _default_client().switch_proxy(group_name, proxy_name)


def switch_mode(mode: str) -> bool:
    return _default_client().switch_mode(mode)


def switch_tun(enabled: bool) -> bool:
    return _default_client().switch_tun(enabled)


def get_config() -> dict[str, Any]:
    return _default_client().get_config()


def reload_config() -> bool:
    return _default_client().reload_config()
