import base64
import json
import urllib.parse
from typing import Any


def decode_base64(s: str) -> bytes:
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    try:
        return base64.b64decode(s)
    except Exception:
        return b""


def parse_vmess(uri: str) -> dict[str, Any] | None:
    if not uri.startswith("vmess://"):
        return None
    b64_str = uri[8:]
    try:
        data = decode_base64(b64_str).decode("utf-8", errors="ignore")
        v_dict = json.loads(data)
    except Exception:
        return None

    proxy: dict[str, Any] = {
        "name": v_dict.get("ps", "vmess_node"),
        "type": "vmess",
        "server": str(v_dict.get("add", "")),
        "port": int(v_dict.get("port", 443)),
        "uuid": str(v_dict.get("id", "")),
        "alterId": int(v_dict.get("aid", 0)),
        "cipher": v_dict.get("scy", "auto"),
        "udp": True,
    }

    net = str(v_dict.get("net", "tcp"))
    if net == "ws":
        proxy["network"] = "ws"
        proxy["ws-opts"] = {
            "path": str(v_dict.get("path", "/")),
            "headers": {"Host": str(v_dict.get("host", ""))} if v_dict.get("host") else {},
        }
    elif net == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {"grpc-service-name": str(v_dict.get("path", ""))}
    elif net == "h2":
        proxy["network"] = "h2"
        proxy["h2-opts"] = {"host": [str(v_dict.get("host", ""))], "path": str(v_dict.get("path", "/"))}

    tls = str(v_dict.get("tls", ""))
    if tls == "tls":
        proxy["tls"] = True
        sni = str(v_dict.get("sni", "") or v_dict.get("host", ""))
        if sni:
            proxy["sni"] = sni
            proxy["servername"] = sni

    return proxy


def parse_vless_or_trojan(uri: str, ptype: str) -> dict[str, Any] | None:
    try:
        parsed = urllib.parse.urlparse(uri)
    except Exception:
        return None

    password_or_uuid = parsed.username or ""
    server = parsed.hostname or ""
    try:
        port = parsed.port or 443
    except ValueError:
        port = 443
    name = urllib.parse.unquote(parsed.fragment) or f"{ptype}_node"

    query = dict(urllib.parse.parse_qsl(parsed.query))

    proxy: dict[str, Any] = {
        "name": name,
        "type": ptype,
        "server": server,
        "port": port,
        "udp": True,
    }

    if ptype == "vless":
        proxy["uuid"] = password_or_uuid
    else:
        proxy["password"] = password_or_uuid

    if query.get("security") == "tls" or ptype == "trojan":
        proxy["tls"] = True
        sni = query.get("sni", query.get("host", ""))
        if sni:
            proxy["sni"] = sni
            proxy["servername"] = sni

    if query.get("fp"):
        proxy["client-fingerprint"] = query.get("fp")

    if ptype == "vless" and query.get("flow"):
        proxy["flow"] = query.get("flow")

    net = query.get("type", "tcp")
    if net == "ws":
        proxy["network"] = "ws"
        proxy["ws-opts"] = {
            "path": query.get("path", "/"),
            "headers": {"Host": query.get("host", "")} if query.get("host") else {},
        }
    elif net == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {"grpc-service-name": query.get("serviceName", "")}

    return proxy


def parse_ss(uri: str) -> dict[str, Any] | None:
    if not uri.startswith("ss://"):
        return None

    # Strip scheme
    raw = uri[5:]
    
    # Extract name (fragment)
    name = "ss_node"
    if "#" in raw:
        raw, fragment = raw.split("#", 1)
        name = urllib.parse.unquote(fragment)
        
    # Remove plugin query if present
    # Some URLs have /?plugin=...
    if "/?" in raw:
        raw = raw.split("/?", 1)[0]
    elif "?" in raw:
        raw = raw.split("?", 1)[0]
        
    # Now raw is basically the base64 or base64@host:port or cipher:pwd@host:port
    try:
        # Case 1: entire string is base64
        if "@" not in raw:
            decoded = decode_base64(raw).decode("utf-8")
            if "@" in decoded:
                user_pass, host_port = decoded.split("@", 1)
                cipher, password = user_pass.split(":", 1)
                server, port_str = host_port.split(":", 1)
                return {
                    "name": name,
                    "type": "ss",
                    "server": server.strip(),
                    "port": int(port_str.strip()),
                    "cipher": cipher.strip(),
                    "password": password.strip(),
                    "udp": True,
                }
                
        # Case 2: base64_user_pass@host:port
        else:
            user_pass, host_port = raw.split("@", 1)
            # Try to decode the user_pass part
            try:
                decoded_user = decode_base64(user_pass).decode("utf-8")
                cipher, password = decoded_user.split(":", 1)
            except Exception:
                # If decoding fails, maybe it's plain text cipher:pwd
                if ":" in user_pass:
                    cipher, password = user_pass.split(":", 1)
                else:
                    return None
                    
            server, port_str = host_port.split(":", 1)
            if "/" in port_str: # In case of trailing slash
                port_str = port_str.split("/", 1)[0]
                
            return {
                "name": name,
                "type": "ss",
                "server": server.strip(),
                "port": int(port_str.strip()),
                "cipher": cipher.strip(),
                "password": password.strip(),
                "udp": True,
            }
            
    except Exception:
        pass

    return None


def decode_subscription(content: str) -> list[dict[str, Any]]:
    if "://" not in content[:100]:
        try:
            decoded = decode_base64(content).decode("utf-8", errors="ignore")
            if "://" in decoded:
                content = decoded
        except Exception:
            pass

    proxies = []
    lines = [L.strip() for L in content.splitlines() if L.strip()]

    names_seen: set[str] = set()

    for line in lines:
        proxy = None
        if line.startswith("vmess://"):
            proxy = parse_vmess(line)
        elif line.startswith("vless://"):
            proxy = parse_vless_or_trojan(line, "vless")
        elif line.startswith("trojan://") or line.startswith("trojans://"):
            proxy = parse_vless_or_trojan(line, "trojan")
        elif line.startswith("ss://"):
            proxy = parse_ss(line)

        if proxy and proxy.get("name"):
            base_name = str(proxy["name"])
            final_name = base_name
            counter = 1
            while final_name in names_seen:
                final_name = f"{base_name} {counter}"
                counter += 1
            proxy["name"] = final_name
            names_seen.add(final_name)
            proxies.append(proxy)

    return proxies
