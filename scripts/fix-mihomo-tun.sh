#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mihomo-party"
WORK_CONFIG="${CONFIG_DIR}/work/config.yaml"
SOCK="/tmp/mihomo-party.sock"
TUN_DNS="198.18.0.1:1053"
MODE="tun"
IFACE=""

log() {
    printf '[fix-mihomo-tun] %s\n' "$*"
}

warn() {
    printf '[fix-mihomo-tun] WARN: %s\n' "$*" >&2
}

die() {
    printf '[fix-mihomo-tun] ERROR: %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

usage() {
    cat <<'EOF'
Usage:
  fix-mihomo-tun.sh [tun|tun-only|sync|status] [iface]

Modes:
  tun     Force-enable mihomo TUN and point current link DNS to mihomo DNS.
  tun-only
          Force-enable mihomo TUN, disable system proxy, and point current
          link DNS to mihomo DNS.
  sync    Keep current mihomo UI/live TUN state, but sync host DNS with it.
          If TUN is on, use 198.18.0.1:1053; if TUN is off, revert link DNS.
  status  Print current mihomo TUN state, system proxy mode, link DNS, and routes.

Examples:
  fix-mihomo-tun.sh
  fix-mihomo-tun.sh tun-only
  fix-mihomo-tun.sh sync
  fix-mihomo-tun.sh status wlp131s0
EOF
}

no_proxy_env() {
    env \
        -u HTTP_PROXY -u HTTPS_PROXY \
        -u http_proxy -u https_proxy \
        -u ALL_PROXY -u all_proxy \
        -u NO_PROXY -u no_proxy \
        "$@"
}

read_live_config() {
    curl --silent --show-error --fail --unix-socket "$SOCK" http://localhost/configs
}

live_tun_enabled() {
    read_live_config | tr -d '\n' | grep -q '"tun":{"enable":true'
}

default_iface() {
    ip route show default 2>/dev/null | awk '/default/ {print $5; exit}'
}

show_status() {
    log "Interface: ${IFACE}"
    if live_tun_enabled; then
        log "Live mihomo TUN: enabled"
    else
        log "Live mihomo TUN: disabled"
    fi
    log "System proxy mode: $(gsettings get org.gnome.system.proxy mode 2>/dev/null || echo unknown)"
    resolvectl status "$IFACE" | sed -n '1,12p'
    ip -brief addr show | sed -n '1,20p'
    ip rule show | sed -n '1,20p'
}

point_dns_to_tun() {
    log "Pointing ${IFACE} DNS to ${TUN_DNS}"
    resolvectl dns "$IFACE" "$TUN_DNS"
    resolvectl domain "$IFACE" '~.'
    resolvectl flush-caches >/dev/null 2>&1 || true
    sleep 1
}

disable_system_proxy() {
    log "Disabling system proxy"
    gsettings set org.gnome.system.proxy mode 'none'
}

revert_dns_to_network() {
    local dns_servers=()
    mapfile -t dns_servers < <(
        nmcli dev show "$IFACE" | awk -F: '
            /IP4.DNS/ {
                gsub(/^[ \t]+/, "", $2)
                if ($2 != "") print $2
            }
        '
    )

    if [[ ${#dns_servers[@]} -gt 0 ]]; then
        log "Restoring ${IFACE} DNS to NetworkManager defaults: ${dns_servers[*]}"
        resolvectl dns "$IFACE" "${dns_servers[@]}"
    else
        log "Reverting ${IFACE} DNS to network defaults"
        resolvectl revert "$IFACE"
    fi
    resolvectl flush-caches >/dev/null 2>&1 || true
    sleep 1
}

quick_check() {
    local host="$1"
    local url="https://${host}"
    local http_code

    if http_code="$(
        no_proxy_env timeout 12 curl \
            --silent \
            --show-error \
            --output /dev/null \
            --write-out '%{http_code}' \
            -I "$url" 2>/dev/null
    )" && [[ -n "$http_code" && "$http_code" != "000" ]]; then
        log "${host}: connectivity OK (HTTP ${http_code})"
    else
        warn "${host}: connectivity check failed"
    fi
}

need_cmd curl
need_cmd ip
need_cmd nmcli
need_cmd resolvectl
need_cmd getent
need_cmd timeout

[[ -S "$SOCK" ]] || die "mihomo control socket not found: ${SOCK}"
[[ -f "$WORK_CONFIG" ]] || die "mihomo work config not found: ${WORK_CONFIG}"

case "${1:-}" in
    "" ) ;;
    tun|tun-only|sync|status)
        MODE="$1"
        IFACE="${2:-}"
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        IFACE="$1"
        ;;
esac

IFACE="${IFACE:-$(default_iface)}"
[[ -n "$IFACE" ]] || die "Could not detect default network interface"

if [[ "$MODE" == "status" ]]; then
    show_status
    exit 0
fi

if [[ "$MODE" == "tun" || "$MODE" == "tun-only" ]]; then
    log "Reloading mihomo from ${WORK_CONFIG}"
    curl --silent --show-error --fail \
        --unix-socket "$SOCK" \
        -X PUT 'http://localhost/configs?force=true' \
        -H 'Content-Type: application/json' \
        -d "{\"path\":\"${WORK_CONFIG}\"}" >/dev/null

    log "Enabling TUN in live config"
    curl --silent --show-error --fail \
        --unix-socket "$SOCK" \
        -X PATCH http://localhost/configs \
        -H 'Content-Type: application/json' \
        -d '{"tun":{"enable":true}}' >/dev/null

    sleep 1

    LIVE_CONFIG="$(read_live_config | tr -d '\n')"
    printf '%s' "$LIVE_CONFIG" | grep -q '"tun":{"enable":true' || die "Live config still shows TUN disabled"

    if ! ip -brief addr show Kard >/dev/null 2>&1; then
        die "TUN interface Kard is missing after reload"
    fi

    if [[ "$MODE" == "tun-only" ]]; then
        disable_system_proxy
    fi

    point_dns_to_tun
elif [[ "$MODE" == "sync" ]]; then
    if live_tun_enabled; then
        point_dns_to_tun
    else
        revert_dns_to_network
    fi
fi

log "Resolver status for ${IFACE}"
resolvectl status "$IFACE" | sed -n '1,12p'

for host in www.google.com www.zhihu.com; do
    resolved_ip="$(getent ahosts "$host" | awk 'NR==1 {print $1}')"
    if [[ -n "${resolved_ip}" ]]; then
        log "${host} -> ${resolved_ip}"
    else
        warn "${host}: no resolver result"
    fi
done

quick_check "www.google.com"
quick_check "www.zhihu.com"

log "Done"
log "If you change TUN in the mihomo-party UI, run: $0 sync"
log "If the mihomo-party UI still looks stale, restart only mihomo-party to refresh its page state."
