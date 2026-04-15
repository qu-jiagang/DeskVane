"""PAC (Proxy Auto-Configuration) script generation and rule conversion."""

from __future__ import annotations

import logging
import re
import time
import urllib.request
from pathlib import Path

_log = logging.getLogger(__name__)


def parse_domain_list(raw: str) -> list[str]:
    """Parse a comma/space/newline separated domain list into a deduplicated list.

    Each entry is a domain suffix like ``google.com`` or ``.github.io``.
    Leading dots are normalized away so ``".google.com"`` becomes ``"google.com"``.
    """
    if not raw or not raw.strip():
        return []
    tokens = re.split(r"[,，;；\s]+", raw.strip())
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        domain = token.strip().strip(".").lower()
        if not domain or domain in seen:
            continue
        seen.add(domain)
        result.append(domain)
    return result


def generate_pac_script(
    proxy_port: int,
    proxy_domains: list[str],
    direct_domains: list[str],
    default_action: str = "PROXY",
    proxy_host: str = "127.0.0.1",
) -> str:
    """Generate a standard PAC (Proxy Auto-Configuration) JavaScript string.

    Parameters
    ----------
    proxy_port:
        The Mihomo mixed-port to use as the PROXY target.
    proxy_domains:
        Domain suffixes that should always go through the proxy.
    direct_domains:
        Domain suffixes that should always bypass the proxy.
    default_action:
        ``"PROXY"`` or ``"DIRECT"`` — behaviour for domains not in either list.
    proxy_host:
        The address of the proxy server (usually ``127.0.0.1``).
    """
    proxy_statement = f'PROXY {proxy_host}:{proxy_port}'
    default_return = (
        f'return "{proxy_statement}";'
        if default_action.upper() == "PROXY"
        else 'return "DIRECT";'
    )

    # Build domain-match blocks
    direct_checks: list[str] = []
    for domain in direct_domains:
        direct_checks.append(
            f'    if (dnsDomainIs(host, ".{domain}") || host === "{domain}") return "DIRECT";'
        )

    proxy_checks: list[str] = []
    for domain in proxy_domains:
        proxy_checks.append(
            f'    if (dnsDomainIs(host, ".{domain}") || host === "{domain}") return "{proxy_statement}";'
        )

    sections: list[str] = []
    if direct_checks:
        sections.append("    // 用户配置的直连域名")
        sections.extend(direct_checks)
    if proxy_checks:
        sections.append("    // 用户配置的代理域名")
        sections.extend(proxy_checks)

    body = "\n".join(sections)
    if body:
        body = "\n" + body + "\n"

    script = f"""\
function FindProxyForURL(url, host) {{
    // 本地 / LAN 直连
    if (isPlainHostName(host) ||
        host === "localhost" ||
        shExpMatch(host, "*.local") ||
        isInNet(host, "10.0.0.0", "255.0.0.0") ||
        isInNet(host, "172.16.0.0", "255.240.0.0") ||
        isInNet(host, "192.168.0.0", "255.255.0.0") ||
        isInNet(host, "127.0.0.0", "255.0.0.0")) {{
        return "DIRECT";
    }}
{body}
    // 默认行为
    {default_return}
}}
"""
    return script


# ---------------------------------------------------------------------------
# PAC domains → Mihomo YAML rules
# ---------------------------------------------------------------------------

_PAC_PROXY_RULE_MARKER = "# pac-proxy"
_PAC_DIRECT_RULE_MARKER = "# pac-direct"


def pac_domains_to_mihomo_rules(
    proxy_domains: list[str],
    direct_domains: list[str],
    proxy_group: str,
    default_action: str = "PROXY",
) -> list[str]:
    """Convert PAC domain lists into Mihomo rule strings.

    These rules are meant to be inserted into the Mihomo ``rules`` list so
    that TUN-mode traffic honours the same PAC-like routing logic.

    Rules carry an inline comment marker (``# pac-proxy`` / ``# pac-direct``)
    so that the sync logic can identify and replace them on subsequent updates.
    """
    rules: list[str] = []
    for domain in direct_domains:
        rules.append(f"DOMAIN-SUFFIX,{domain},DIRECT {_PAC_DIRECT_RULE_MARKER}")
    for domain in proxy_domains:
        rules.append(f"DOMAIN-SUFFIX,{domain},{proxy_group} {_PAC_PROXY_RULE_MARKER}")
    return rules


def is_managed_pac_rule(rule: str) -> bool:
    """Return True if *rule* is a DeskVane-managed PAC rule."""
    if not isinstance(rule, str):
        return False
    return rule.rstrip().endswith(_PAC_PROXY_RULE_MARKER) or rule.rstrip().endswith(
        _PAC_DIRECT_RULE_MARKER
    )


def sync_pac_rules(
    data: dict,
    proxy_domains: list[str],
    direct_domains: list[str],
    proxy_group: str,
    default_action: str = "PROXY",
    enabled: bool = True,
) -> bool:
    """Ensure the Mihomo ``rules`` list contains the correct PAC rules.

    Managed PAC rules are inserted *after* any process-bypass rules and
    *before* the final ``MATCH`` catch-all.  Existing managed PAC rules
    are removed first, then the new set is injected.

    Returns True if the rules list was modified.
    """
    rules = data.get("rules")
    if not isinstance(rules, list):
        if not enabled or (not proxy_domains and not direct_domains):
            return False
        rules = []
        data["rules"] = rules

    # 1. Remove existing managed PAC rules.
    old_count = len(rules)
    cleaned = [rule for rule in rules if not is_managed_pac_rule(rule)]
    removed = old_count - len(cleaned)

    if not enabled or (not proxy_domains and not direct_domains):
        if removed > 0:
            data["rules"] = cleaned
            return True
        return False

    # 2. Build new managed rules.
    new_rules = pac_domains_to_mihomo_rules(
        proxy_domains, direct_domains, proxy_group, default_action
    )

    # 3. Find insertion point: after process-bypass rules, before MATCH.
    insert_index = len(cleaned)
    for i, rule in enumerate(cleaned):
        stripped = str(rule).strip()
        if stripped.startswith("MATCH,") or stripped.startswith("MATCH "):
            insert_index = i
            break

    for i, new_rule in enumerate(new_rules):
        cleaned.insert(insert_index + i, new_rule)

    data["rules"] = cleaned
    return True


# ---------------------------------------------------------------------------
# Remote PAC support
# ---------------------------------------------------------------------------

# Proxy declaration patterns found in common PAC files.
# Matches e.g.:  var proxy = 'SOCKS5 127.0.0.1:1080; SOCKS 127.0.0.1:1080; DIRECT;';
#                var proxy = "PROXY 127.0.0.1:8080";
_PROXY_VAR_RE = re.compile(
    r"""(var\s+proxy\s*=\s*)(['"])(.+?)\2""",
    re.IGNORECASE,
)

# Standalone proxy strings inside return statements or assignments.
# Matches e.g.:  SOCKS5 127.0.0.1:1080  /  PROXY 192.168.1.1:3128
_PROXY_TOKEN_RE = re.compile(
    r"(PROXY|SOCKS5?|HTTPS?)\s+[\d.]+:\d+",
    re.IGNORECASE,
)


def rewrite_pac_proxy(
    pac_js: str,
    proxy_port: int,
    proxy_host: str = "127.0.0.1",
) -> str:
    """Rewrite proxy addresses in *pac_js* to point at the local Mihomo port.

    Two strategies are applied:

    1. If a ``var proxy = '...'`` declaration exists (gfwlist2pac style),
       the entire value is replaced with ``PROXY <host>:<port>; DIRECT;``.
    2. All remaining ``PROXY/SOCKS/SOCKS5 <ip>:<port>`` tokens are replaced.
    """
    new_proxy_val = f"PROXY {proxy_host}:{proxy_port}; DIRECT;"

    def _replace_var(m: re.Match) -> str:
        quote = m.group(2)
        return f"{m.group(1)}{quote}{new_proxy_val}{quote}"

    result = _PROXY_VAR_RE.sub(_replace_var, pac_js)

    def _replace_token(m: re.Match) -> str:
        return f"PROXY {proxy_host}:{proxy_port}"

    result = _PROXY_TOKEN_RE.sub(_replace_token, result)
    return result


# Simple disk cache for remote PAC files.
_remote_pac_cache: dict[str, tuple[float, str]] = {}
_CACHE_TTL_S = 3600  # 1 hour


def fetch_remote_pac(
    url: str,
    proxy_port: int,
    proxy_host: str = "127.0.0.1",
    cache_dir: Path | None = None,
    timeout_s: int = 15,
) -> str:
    """Download a remote PAC file, rewrite the proxy address, and return the JS.

    The download is routed through the local Mihomo proxy
    (``http://<proxy_host>:<proxy_port>``) so that blocked hosts like
    ``raw.githubusercontent.com`` are reachable.  Falls back to a direct
    connection, then to the disk cache.

    Results are cached in memory (1 hour TTL) and optionally persisted to
    *cache_dir* so the last-known-good PAC is available even when the remote
    server is unreachable.
    """
    cache_key = url

    # Memory cache hit?
    if cache_key in _remote_pac_cache:
        ts, cached_raw = _remote_pac_cache[cache_key]
        if time.monotonic() - ts < _CACHE_TTL_S:
            return rewrite_pac_proxy(cached_raw, proxy_port, proxy_host)

    # Disk cache path
    disk_cache: Path | None = None
    if cache_dir is not None:
        safe_name = re.sub(r"[^\w]", "_", url)[:120] + ".pac"
        disk_cache = cache_dir / safe_name

    raw_pac: str | None = None
    headers = {"User-Agent": "DeskVane/1.0"}

    # Strategy 1: fetch through local Mihomo proxy
    try:
        proxy_handler = urllib.request.ProxyHandler({
            "http": f"http://{proxy_host}:{proxy_port}",
            "https": f"http://{proxy_host}:{proxy_port}",
        })
        opener = urllib.request.build_opener(proxy_handler)
        req1 = urllib.request.Request(url, headers=headers)
        with opener.open(req1, timeout=timeout_s) as resp:
            raw_pac = resp.read().decode("utf-8", errors="replace")
        _log.info("Fetched remote PAC via proxy from %s (%d bytes)", url, len(raw_pac))
    except Exception as exc:
        _log.debug("Proxy fetch failed for %s: %s, trying direct", url, exc)

    # Strategy 2: fetch directly (in case proxy is not up or URL is local)
    if raw_pac is None:
        try:
            req2 = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req2, timeout=timeout_s) as resp:
                raw_pac = resp.read().decode("utf-8", errors="replace")
            _log.info("Fetched remote PAC directly from %s (%d bytes)", url, len(raw_pac))
        except Exception as exc:
            _log.warning("Direct fetch also failed for %s: %s", url, exc)

    # Strategy 3: fall back to disk cache
    if raw_pac is None and disk_cache is not None and disk_cache.exists():
        raw_pac = disk_cache.read_text(encoding="utf-8")
        _log.info("Using disk-cached PAC for %s", url)

    if raw_pac is None:
        raise RuntimeError(f"无法获取远程 PAC 文件: {url}")

    # Update caches
    _remote_pac_cache[cache_key] = (time.monotonic(), raw_pac)
    if disk_cache is not None:
        try:
            disk_cache.parent.mkdir(parents=True, exist_ok=True)
            disk_cache.write_text(raw_pac, encoding="utf-8")
        except OSError:
            pass

    return rewrite_pac_proxy(raw_pac, proxy_port, proxy_host)


def invalidate_remote_pac_cache(url: str = "") -> None:
    """Clear the memory cache for a specific URL, or all URLs if empty."""
    if url:
        _remote_pac_cache.pop(url, None)
    else:
        _remote_pac_cache.clear()


def extract_domains_from_pac_js(pac_js: str) -> list[str]:
    """Best-effort extraction of domain strings from a PAC JavaScript file.

    This handles the gfwlist2pac format where domains are stored as quoted
    strings inside JavaScript arrays.  For arbitrary PAC files it will
    extract any quoted string that looks like a domain name.
    """
    # Match quoted strings that look like domain names
    candidates = re.findall(r'["\']([a-zA-Z0-9][\w.-]+\.[a-zA-Z]{2,})["\']', pac_js)
    seen: set[str] = set()
    result: list[str] = []
    for domain in candidates:
        d = domain.lower()
        if d in seen:
            continue
        # Filter out things that are clearly not domains
        if d.startswith("127.") or d.startswith("192.168.") or d.startswith("10."):
            continue
        seen.add(d)
        result.append(d)
    return result
