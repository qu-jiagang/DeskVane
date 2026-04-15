"""Tests for subconverter subscription decoder."""

from __future__ import annotations

import base64
import json

import pytest

from deskvane.subconverter.decoder import (
    decode_base64,
    decode_subscription,
    parse_ss,
    parse_vless_or_trojan,
    parse_vmess,
)


# ---------------------------------------------------------------------------
# decode_base64
# ---------------------------------------------------------------------------


class TestDecodeBase64:
    def test_standard_base64(self):
        raw = base64.b64encode(b"hello world").decode()
        assert decode_base64(raw) == b"hello world"

    def test_url_safe_base64(self):
        raw = base64.urlsafe_b64encode(b"hello world").decode()
        assert decode_base64(raw) == b"hello world"

    def test_missing_padding(self):
        raw = base64.b64encode(b"test data").decode().rstrip("=")
        assert decode_base64(raw) == b"test data"

    def test_empty_string(self):
        assert decode_base64("") == b""

    def test_invalid_base64(self):
        # Should NOT raise — the decoder is lenient by design for subscription parsing
        result = decode_base64("!@#$%^&*()_+-")
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# parse_vmess
# ---------------------------------------------------------------------------


class TestParseVmess:
    def _make_vmess_uri(self, config: dict) -> str:
        payload = json.dumps(config).encode()
        b64 = base64.b64encode(payload).decode()
        return f"vmess://{b64}"

    def test_basic_vmess(self):
        config = {
            "ps": "Test Node",
            "add": "1.2.3.4",
            "port": 443,
            "id": "aaaa-bbbb-cccc",
            "aid": 0,
            "net": "tcp",
            "tls": "",
        }
        result = parse_vmess(self._make_vmess_uri(config))
        assert result is not None
        assert result["name"] == "Test Node"
        assert result["type"] == "vmess"
        assert result["server"] == "1.2.3.4"
        assert result["port"] == 443
        assert result["uuid"] == "aaaa-bbbb-cccc"
        assert result["alterId"] == 0

    def test_vmess_with_ws(self):
        config = {
            "ps": "WS Node",
            "add": "ws.example.com",
            "port": 8080,
            "id": "uuid-1",
            "aid": 0,
            "net": "ws",
            "path": "/ws-path",
            "host": "ws.example.com",
            "tls": "tls",
            "sni": "ws.example.com",
        }
        result = parse_vmess(self._make_vmess_uri(config))
        assert result is not None
        assert result["network"] == "ws"
        assert result["ws-opts"]["path"] == "/ws-path"
        assert result["tls"] is True
        assert result["sni"] == "ws.example.com"

    def test_vmess_with_grpc(self):
        config = {
            "ps": "gRPC",
            "add": "1.1.1.1",
            "port": 443,
            "id": "uuid-2",
            "aid": 0,
            "net": "grpc",
            "path": "my-service",
        }
        result = parse_vmess(self._make_vmess_uri(config))
        assert result is not None
        assert result["network"] == "grpc"
        assert result["grpc-opts"]["grpc-service-name"] == "my-service"

    def test_vmess_invalid_base64(self):
        assert parse_vmess("vmess://!!!invalid!!!") is None

    def test_non_vmess_uri(self):
        assert parse_vmess("vless://user@host:443") is None

    def test_vmess_missing_fields(self):
        config = {"add": "1.1.1.1", "port": "80", "id": "u"}
        result = parse_vmess(self._make_vmess_uri(config))
        assert result is not None
        assert result["name"] == "vmess_node"  # default name


# ---------------------------------------------------------------------------
# parse_vless_or_trojan
# ---------------------------------------------------------------------------


class TestParseVlessOrTrojan:
    def test_basic_vless(self):
        uri = "vless://uuid-123@server.com:443?security=tls&sni=server.com&type=ws&path=/v#My%20Node"
        result = parse_vless_or_trojan(uri, "vless")
        assert result is not None
        assert result["name"] == "My Node"
        assert result["type"] == "vless"
        assert result["server"] == "server.com"
        assert result["port"] == 443
        assert result["uuid"] == "uuid-123"
        assert result["tls"] is True
        assert result["network"] == "ws"

    def test_trojan(self):
        uri = "trojan://password123@trojan.host:8443#Trojan%20Node"
        result = parse_vless_or_trojan(uri, "trojan")
        assert result is not None
        assert result["type"] == "trojan"
        assert result["password"] == "password123"
        assert result["tls"] is True  # trojan always sets tls

    def test_vless_with_flow(self):
        uri = "vless://uid@host:443?security=tls&flow=xtls-rprx-vision&fp=chrome#flow_node"
        result = parse_vless_or_trojan(uri, "vless")
        assert result is not None
        assert result["flow"] == "xtls-rprx-vision"
        assert result["client-fingerprint"] == "chrome"

    def test_vless_grpc(self):
        uri = "vless://uid@host:443?type=grpc&serviceName=my-svc#grpc"
        result = parse_vless_or_trojan(uri, "vless")
        assert result is not None
        assert result["network"] == "grpc"
        assert result["grpc-opts"]["grpc-service-name"] == "my-svc"


# ---------------------------------------------------------------------------
# parse_ss
# ---------------------------------------------------------------------------


class TestParseSS:
    def test_ss_with_base64_userpass(self):
        # cipher:password base64-encoded, then @host:port
        userinfo = base64.b64encode(b"aes-256-gcm:my-password").decode()
        uri = f"ss://{userinfo}@10.0.0.1:8388#SS%20Node"
        result = parse_ss(uri)
        assert result is not None
        assert result["name"] == "SS Node"
        assert result["type"] == "ss"
        assert result["server"] == "10.0.0.1"
        assert result["port"] == 8388
        assert result["cipher"] == "aes-256-gcm"
        assert result["password"] == "my-password"

    def test_ss_fully_base64(self):
        inner = "aes-128-gcm:pass@1.2.3.4:1234"
        b64 = base64.b64encode(inner.encode()).decode()
        uri = f"ss://{b64}#Full64"
        result = parse_ss(uri)
        assert result is not None
        assert result["server"] == "1.2.3.4"
        assert result["port"] == 1234
        assert result["cipher"] == "aes-128-gcm"
        assert result["password"] == "pass"

    def test_ss_invalid(self):
        assert parse_ss("ss://totally-broken-garbage") is None

    def test_non_ss_uri(self):
        assert parse_ss("vmess://something") is None


# ---------------------------------------------------------------------------
# decode_subscription
# ---------------------------------------------------------------------------


class TestDecodeSubscription:
    def _make_vmess_uri(self, name: str = "v1") -> str:
        config = {"ps": name, "add": "1.1.1.1", "port": 443, "id": "uid", "aid": 0}
        return "vmess://" + base64.b64encode(json.dumps(config).encode()).decode()

    def test_multi_protocol(self):
        vmess = self._make_vmess_uri("vmess1")
        trojan = "trojan://pwd@host:443#trojan1"
        content = f"{vmess}\n{trojan}\n"
        proxies = decode_subscription(content)
        assert len(proxies) == 2
        assert proxies[0]["name"] == "vmess1"
        assert proxies[1]["name"] == "trojan1"

    def test_base64_wrapped_subscription(self):
        vmess = self._make_vmess_uri("inner")
        raw = base64.b64encode(vmess.encode()).decode()
        proxies = decode_subscription(raw)
        assert len(proxies) == 1
        assert proxies[0]["name"] == "inner"

    def test_name_deduplication(self):
        v1 = self._make_vmess_uri("dup")
        v2 = self._make_vmess_uri("dup")
        proxies = decode_subscription(f"{v1}\n{v2}\n")
        assert len(proxies) == 2
        names = {p["name"] for p in proxies}
        assert "dup" in names
        assert "dup 1" in names

    def test_empty_content(self):
        assert decode_subscription("") == []

    def test_invalid_lines_skipped(self):
        content = "not_a_valid_uri\nhttp://example.com\n"
        assert decode_subscription(content) == []
