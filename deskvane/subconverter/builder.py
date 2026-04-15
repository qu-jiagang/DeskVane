from typing import Any

import yaml


class IndentDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=IndentDumper, allow_unicode=True, sort_keys=False)


def build_proxy_provider_content(proxies: list[dict[str, Any]]) -> str:
    return _dump_yaml({"proxies": proxies})


def build_clash_config(proxies: list[dict[str, Any]]) -> str:
    proxy_names = [str(p["name"]) for p in proxies]

    config: dict[str, Any] = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "127.0.0.1:9090",
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "PROXY",
                "type": "select",
                "proxies": ["Auto", "Direct"] + proxy_names,
            },
            {
                "name": "Auto",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": proxy_names if proxy_names else ["DIRECT"],
            },
            {"name": "Direct", "type": "select", "proxies": ["DIRECT"]},
        ],
        "rules": [
            "DOMAIN-SUFFIX,local,Direct",
            "IP-CIDR,127.0.0.0/8,Direct,no-resolve",
            "IP-CIDR,192.168.0.0/16,Direct,no-resolve",
            "IP-CIDR,10.0.0.0/8,Direct,no-resolve",
            "IP-CIDR,172.16.0.0/12,Direct,no-resolve",
            "MATCH,PROXY",
        ],
    }
    return _dump_yaml(config)
