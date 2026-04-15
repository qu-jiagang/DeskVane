from __future__ import annotations

import urllib.request
from typing import Any

from .builder import build_clash_config, build_proxy_provider_content
from .decoder import decode_subscription

USER_AGENT = "DeskVane-Subconverter/1.0"


def load_subscription_source(source: str, timeout_s: int = 10) -> str:
    source = source.strip()
    if not source:
        raise ValueError("订阅地址不能为空。")

    if (source.startswith("http://") or source.startswith("https://")) and "\n" not in source:
        req = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            return response.read().decode("utf-8", errors="ignore")
    return source


def load_subscription_proxies(source: str, timeout_s: int = 10) -> list[dict[str, Any]]:
    content = load_subscription_source(source, timeout_s=timeout_s)
    proxies = decode_subscription(content)
    if not proxies:
        raise ValueError("未能在输入内容中解析到任何有效的节点。")
    return proxies


def convert_subscription_source_to_provider_yaml(source: str, timeout_s: int = 10) -> str:
    return build_proxy_provider_content(load_subscription_proxies(source, timeout_s=timeout_s))


def convert_subscription_source_to_yaml(source: str, timeout_s: int = 10) -> str:
    return build_clash_config(load_subscription_proxies(source, timeout_s=timeout_s))
