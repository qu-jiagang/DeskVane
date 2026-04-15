from unittest import mock

from deskvane.mihomo.api import MihomoApiClient


def test_runtime_state_extracts_mode_and_groups() -> None:
    client = MihomoApiClient(controller="127.0.0.1:9090")
    with mock.patch.object(
        MihomoApiClient,
        "get_config",
        return_value={"mode": "rule", "mixed-port": 7890, "socks-port": 7891},
    ), mock.patch.object(
        MihomoApiClient,
        "get_proxies",
        return_value={
            "GLOBAL": {
                "type": "Selector",
                "now": "Node-A",
                "all": ["Node-A", "Node-B", "DIRECT"],
            },
            "Node-A": {"type": "Vmess"},
        },
    ):
        runtime = client.get_runtime_state()

    assert runtime.api_ready is True
    assert runtime.mode == "rule"
    assert runtime.mixed_port == 7890
    assert len(runtime.groups) == 1
    assert runtime.groups[0].name == "GLOBAL"
    assert runtime.groups[0].current == "Node-A"
    assert runtime.groups[0].candidates == ["Node-A", "Node-B", "DIRECT"]


def test_runtime_state_extracts_recent_delay_and_test_url() -> None:
    client = MihomoApiClient(controller="127.0.0.1:9090")
    with mock.patch.object(
        MihomoApiClient,
        "get_config",
        return_value={"mode": "rule", "mixed-port": 7890, "socks-port": 7891},
    ), mock.patch.object(
        MihomoApiClient,
        "get_proxies",
        return_value={
            "PROXY": {
                "type": "Selector",
                "now": "Node-A",
                "all": ["Node-A", "Node-B", "DIRECT"],
                "testUrl": "https://cp.cloudflare.com/generate_204",
                "history": [{"time": "2026-04-08T10:00:00Z", "delay": 286}],
            },
            "Node-A": {
                "type": "Vmess",
                "history": [{"time": "2026-04-08T10:00:00Z", "delay": 188}],
            },
            "Node-B": {
                "type": "Vmess",
                "history": [{"time": "2026-04-08T10:01:00Z", "delay": 245}],
            },
        },
    ):
        runtime = client.get_runtime_state()

    assert runtime.groups[0].test_url == "https://cp.cloudflare.com/generate_204"
    assert runtime.groups[0].last_delay_ms == 286
    assert runtime.groups[0].candidate_delays == {"Node-A": 188, "Node-B": 245}


def test_runtime_state_handles_empty_api() -> None:
    client = MihomoApiClient(controller="127.0.0.1:9090")
    with mock.patch.object(MihomoApiClient, "get_config", return_value={}), \
         mock.patch.object(MihomoApiClient, "get_proxies", return_value={}):
        runtime = client.get_runtime_state()

    assert runtime.api_ready is False
    assert runtime.groups == []


def test_proxy_delay_uses_delay_endpoint_and_parses_response() -> None:
    client = MihomoApiClient(controller="127.0.0.1:9090")
    with mock.patch.object(MihomoApiClient, "_request", return_value={"delay": 233}) as request:
        delay = client.test_proxy_delay(
            "Node A@127.0.0.1:8443",
            test_url="https://www.gstatic.com/generate_204",
            timeout_ms=4200,
        )

    assert delay == 233
    request.assert_called_once()
    method, path = request.call_args.args
    assert method == "GET"
    assert "/proxies/Node%20A%40127.0.0.1%3A8443/delay" in path
    assert "timeout=4200" in path
    assert "url=https%3A%2F%2Fwww.gstatic.com%2Fgenerate_204" in path


def test_proxy_delay_returns_none_on_invalid_response() -> None:
    client = MihomoApiClient(controller="127.0.0.1:9090")
    with mock.patch.object(MihomoApiClient, "_request", return_value={"message": "failed"}):
        delay = client.test_proxy_delay("Node-A")

    assert delay is None
