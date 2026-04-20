from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Mapping
from urllib.parse import parse_qs, urlparse

from ..mihomo.api import MihomoRuntimeState
from .tray_model import TrayMenuEntry, TrayMenuItem, TrayMenuModel, TrayMenuSeparator


class TrayAction:
    DO_SCREENSHOT_AND_PIN = "do_screenshot_and_pin"
    DO_PURE_OCR = "do_pure_ocr"
    SHOW_CLIPBOARD_HISTORY = "show_clipboard_history"
    SHOW_SUBCONVERTER = "show_subconverter"
    TOGGLE_MIHOMO = "toggle_mihomo"
    MIHOMO_RELOAD_CORE_CONFIG = "mihomo_reload_core_config"
    OPEN_MIHOMO_CONTROLLER = "open_mihomo_controller"
    OPEN_MIHOMO_CORE_CONFIG = "open_mihomo_core_config"
    OPEN_MIHOMO_LOGS = "open_mihomo_logs"
    MIHOMO_SWITCH_SUBSCRIPTION = "mihomo_switch_subscription"
    MIHOMO_SET_MODE = "mihomo_set_mode"
    MIHOMO_SWITCH_PROXY = "mihomo_switch_proxy"
    MIHOMO_START_NODE_DELAY_TEST = "mihomo_start_node_delay_test"
    MIHOMO_TOGGLE_TUN = "mihomo_toggle_tun"
    MIHOMO_TOGGLE_PAC = "mihomo_toggle_pac"
    MIHOMO_COPY_PAC_URL = "mihomo_copy_pac_url"
    SHOW_MIHOMO_WINDOW = "show_mihomo_window"
    TOGGLE_TERMINAL_PROXY = "toggle_terminal_proxy"
    TOGGLE_GIT_PROXY = "toggle_git_proxy"
    TRANSLATOR_COPY_LAST = "translator_copy_last"
    TRANSLATOR_TOGGLE_PAUSE = "translator_toggle_pause"
    SHOW_SETTINGS = "show_settings"
    SHOW_HELP = "show_help"
    QUIT = "quit"


@dataclass(frozen=True, slots=True)
class MihomoProxyGroupState:
    name: str
    group_type: str
    current: str
    candidates: tuple[str, ...]
    candidate_delays: Mapping[str, int] = field(default_factory=dict)
    test_url: str = ""


@dataclass(frozen=True, slots=True)
class MihomoMenuState:
    installed: bool
    running: bool
    backend: str
    title: str
    api_ready: bool
    party_supported: bool
    mode: str
    tun_enabled: bool
    mixed_port: int | None
    port: int | None
    has_external_ui: bool
    last_error: str = ""
    config_error: str = ""
    pac_enabled: bool = False
    subscription_url: str = ""
    saved_subscriptions: tuple[str, ...] = ()
    groups: tuple[MihomoProxyGroupState, ...] = ()
    delay_test_running: bool = False
    manual_delay_results: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TrayMenuState:
    translator_enabled: bool
    translator_paused: bool
    last_translation_available: bool
    clipboard_history_enabled: bool
    is_git_proxy_enabled: bool
    is_terminal_proxy_enabled: bool
    terminal_proxy_supported: bool
    mihomo: MihomoMenuState


def truncate_text(text: str, limit: int = 72) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}…"


def format_mihomo_mode(mode: str) -> str:
    mapping = {
        "rule": "Rule",
        "global": "Global",
        "direct": "Direct",
    }
    return mapping.get(mode, mode or "-")


def subscription_menu_label(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        return "未命名订阅"
    try:
        parsed = urlparse(normalized)
    except Exception:
        return truncate_text(normalized, 36)
    host = parsed.netloc or "本地订阅"
    query = parse_qs(parsed.query)
    service = (query.get("service") or [""])[0].strip()
    sub_id = (query.get("id") or [""])[0].strip()
    if service:
        return f"{host} · {service}"
    if sub_id:
        return f"{host} · …{sub_id[-6:]}"
    tail = parsed.path.rstrip("/").rsplit("/", 1)[-1].strip()
    if tail and tail not in {"", "getsub.php"}:
        return f"{host} · {truncate_text(tail, 14)}"
    return host


def mihomo_group_map(runtime: MihomoRuntimeState) -> dict[str, object]:
    return {group.name: group for group in runtime.groups}


def mihomo_active_group_name(runtime: MihomoRuntimeState) -> str:
    available = {group.name for group in runtime.groups}
    mode = str(runtime.mode).strip().lower()
    if mode == "global":
        return "GLOBAL" if "GLOBAL" in available else ""
    if mode == "rule":
        if "PROXY" in available:
            return "PROXY"
        if "DESKVANE-PROXY" in available:
            return "DESKVANE-PROXY"
        return ""
    if mode == "direct":
        return "Direct" if "Direct" in available else ""
    return ""


def mihomo_primary_group(runtime: MihomoRuntimeState):
    if not runtime.groups:
        return None
    group_map = mihomo_group_map(runtime)
    preferred: list[str] = []
    active = mihomo_active_group_name(runtime)
    if active:
        preferred.append(active)
    preferred.extend(["PROXY", "DESKVANE-PROXY", "GLOBAL", "Auto", "Direct"])
    for name in preferred:
        group = group_map.get(name)
        if group is not None:
            return group
    return runtime.groups[0]


def mihomo_visible_nodes(group, runtime: MihomoRuntimeState) -> list[str]:
    group_names = {item.name for item in runtime.groups}
    visible: list[str] = []
    for candidate in group.candidates:
        normalized = str(candidate).strip()
        if not normalized:
            continue
        if normalized in group_names:
            continue
        if normalized.upper() in {"DIRECT", "REJECT"}:
            continue
        visible.append(normalized)
    return visible


def mihomo_leaf_node_name(group, runtime: MihomoRuntimeState) -> str:
    group_map = mihomo_group_map(runtime)
    current = str(group.current).strip()
    seen: set[str] = set()
    while current and current in group_map and current not in seen:
        seen.add(current)
        current = str(group_map[current].current).strip()
    return current or str(group.current).strip()


def node_host_token(node: str) -> str:
    if "@" not in node:
        return ""
    host = node.rsplit("@", 1)[-1].strip()
    if not host:
        return ""
    for sep in ("/", ":", "."):
        if sep in host:
            host = host.split(sep, 1)[0]
    return host.strip()


def compact_node_labels(nodes: list[str]) -> dict[str, str]:
    host_labels: dict[str, str] = {}
    for node in nodes:
        host_token = node_host_token(node)
        if not host_token:
            host_labels = {}
            break
        host_labels[node] = host_token
    if host_labels and len(set(host_labels.values())) == len(nodes):
        return host_labels

    if not nodes:
        return {}

    prefix = os.path.commonprefix(nodes)
    reversed_nodes = [node[::-1] for node in nodes]
    suffix = os.path.commonprefix(reversed_nodes)[::-1]
    if len(prefix) + len(suffix) >= min(len(node) for node in nodes):
        suffix = ""

    labels: dict[str, str] = {}
    used: set[str] = set()
    for node in nodes:
        core = node[len(prefix):] if prefix else node
        if suffix and core.endswith(suffix):
            core = core[:-len(suffix)]
        compact = core.strip(" -_@.:/|") or node
        if compact in used:
            compact = truncate_text(node, 40)
        used.add(compact)
        labels[node] = compact
    return labels


def mihomo_delay_ms_for_node(
    node: str,
    runtime: MihomoRuntimeState,
    manual_delay_results: Mapping[str, int],
) -> int | None:
    cached = manual_delay_results.get(node)
    if cached is not None and cached > 0:
        return cached
    for group in runtime.groups:
        delay = group.candidate_delays.get(node)
        if delay is not None and delay > 0:
            return delay
    return None


def build_mihomo_node_menu_label(
    node: str,
    compact_labels: Mapping[str, str],
    runtime: MihomoRuntimeState,
    manual_delay_results: Mapping[str, int],
) -> str:
    label = compact_labels.get(node, node)
    delay = mihomo_delay_ms_for_node(node, runtime, manual_delay_results)
    if delay is None:
        return label
    return f"{label} · {delay}ms"


def build_mihomo_root_label(state: MihomoMenuState) -> str:
    title = state.title
    if not state.installed:
        return f"{title} · 未安装"
    if state.backend == "party":
        return f"{title} · {'运行中' if state.running else '已停止'}"
    if not state.running:
        return f"{title} · 已停止"
    if not state.api_ready:
        return f"{title} · 启动中"
    tun_tag = " · TUN" if state.tun_enabled else ""
    pac_tag = " · PAC" if state.pac_enabled else ""
    return f"{title} · {format_mihomo_mode(state.mode)}{tun_tag}{pac_tag}"


def build_mihomo_status_line(state: MihomoMenuState) -> str:
    title = state.title
    if not state.installed:
        return f"状态: {title} 未安装"
    if state.backend == "party":
        return f"状态: {'运行中' if state.running else '已停止'}"
    if state.api_ready:
        port = state.mixed_port or state.port or "-"
        return f"端口: {port} | {len(state.groups)} 个代理组"
    if state.running:
        return "等待 API 就绪…"
    return "已停止"


def build_mihomo_error_line(state: MihomoMenuState) -> str:
    errors = [msg for msg in (state.last_error, state.config_error) if msg]
    if not errors:
        return ""
    return f"错误: {truncate_text(' | '.join(errors), 32)}"


def build_mihomo_open_label(state: MihomoMenuState) -> str:
    if state.backend != "core":
        return "打开控制台"
    return "打开 Web UI" if state.has_external_ui else "打开 API 地址"


def build_translator_status_line(state: TrayMenuState) -> str:
    if not state.translator_enabled:
        return "状态: 未启用"
    return f"状态: {'已暂停' if state.translator_paused else '运行中'}"


def build_tray_menu_model(state: TrayMenuState, registry) -> TrayMenuModel:
    if registry is None:
        raise RuntimeError("DeskVane tray menu requires tray registry context")

    tools_sub = registry.build_entries("tools", state)
    proxy_sub = registry.build_entries("proxy", state)
    translator_sub = registry.build_entries("translator", state)

    mihomo_sub = build_mihomo_menu_items(state.mihomo)

    return TrayMenuModel(
        items=(
            TrayMenuItem("工具", submenu=tools_sub),
            TrayMenuItem(build_mihomo_root_label(state.mihomo), submenu=mihomo_sub),
            TrayMenuItem("代理", submenu=proxy_sub),
            TrayMenuItem("翻译", submenu=translator_sub),
            TrayMenuSeparator(),
            TrayMenuItem("设置…", TrayAction.SHOW_SETTINGS),
            TrayMenuItem("帮助", TrayAction.SHOW_HELP),
            TrayMenuSeparator(),
            TrayMenuItem("退出", TrayAction.QUIT),
        )
    )


def build_mihomo_menu_items(state: MihomoMenuState) -> tuple[TrayMenuEntry, ...]:
    items: list[TrayMenuEntry] = []
    if not state.installed:
        items.append(TrayMenuItem(f"{state.title} 未安装", enabled=False))
        return tuple(items)

    items.append(
        TrayMenuItem(
            "停止" if state.running else "启动",
            TrayAction.TOGGLE_MIHOMO,
        )
    )
    items.append(TrayMenuItem(build_mihomo_status_line(state), enabled=False))

    error_line = build_mihomo_error_line(state)
    if error_line:
        items.append(TrayMenuItem(error_line, enabled=False))

    if state.backend == "core":
        mode_sub = (
            TrayMenuItem(
                "Rule",
                TrayAction.MIHOMO_SET_MODE,
                action_args=("rule",),
                checked=state.mode == "rule",
                radio=True,
                enabled=state.api_ready,
            ),
            TrayMenuItem(
                "Global",
                TrayAction.MIHOMO_SET_MODE,
                action_args=("global",),
                checked=state.mode == "global",
                radio=True,
                enabled=state.api_ready,
            ),
            TrayMenuItem(
                "Direct",
                TrayAction.MIHOMO_SET_MODE,
                action_args=("direct",),
                checked=state.mode == "direct",
                radio=True,
                enabled=state.api_ready,
            ),
        )
        advanced_sub = (
            TrayMenuItem("重载配置", TrayAction.MIHOMO_RELOAD_CORE_CONFIG),
            TrayMenuItem(
                build_mihomo_open_label(state),
                TrayAction.OPEN_MIHOMO_CONTROLLER,
                enabled=state.api_ready,
            ),
            TrayMenuItem("打开配置", TrayAction.OPEN_MIHOMO_CORE_CONFIG),
            TrayMenuItem("打开日志", TrayAction.OPEN_MIHOMO_LOGS),
        )
        subscription_urls = state.saved_subscriptions
        if subscription_urls:
            subscription_switch_sub = tuple(
                TrayMenuItem(
                    subscription_menu_label(url),
                    TrayAction.MIHOMO_SWITCH_SUBSCRIPTION,
                    action_args=(url,),
                    radio=True,
                    checked=state.subscription_url == url,
                )
                for url in subscription_urls
            )
        else:
            subscription_switch_sub = (
                TrayMenuItem("暂无已保存订阅", enabled=False),
            )

        runtime = state_runtime_from_menu_state(state)
        quick_group = mihomo_primary_group(runtime)
        quick_group_name = quick_group.name if quick_group is not None else ""
        quick_nodes = (
            mihomo_visible_nodes(quick_group, runtime)
            if quick_group is not None
            else []
        )
        current_node = (
            mihomo_leaf_node_name(quick_group, runtime)
            if quick_group is not None
            else ""
        )
        compact_node_labels = compact_node_labels_for_state(quick_nodes)
        if quick_group is not None and quick_nodes:
            node_switch_sub = (
                TrayMenuItem(f"当前组: {quick_group_name}", enabled=False),
                TrayMenuSeparator(),
                TrayMenuItem(
                    "测试节点延迟（进行中）" if state.delay_test_running else "测试节点延迟",
                    TrayAction.MIHOMO_START_NODE_DELAY_TEST,
                    enabled=state.api_ready and not state.delay_test_running,
                ),
                TrayMenuSeparator(),
                *[
                    TrayMenuItem(
                        build_mihomo_node_menu_label(
                            node,
                            compact_node_labels,
                            runtime,
                            state.manual_delay_results,
                        ),
                        TrayAction.MIHOMO_SWITCH_PROXY,
                        action_args=(quick_group_name, node),
                        radio=True,
                        checked=current_node == node,
                        enabled=state.api_ready,
                    )
                    for node in quick_nodes
                ],
            )
        else:
            node_switch_sub = (
                TrayMenuItem("当前模式下没有可切换节点", enabled=False),
            )

        items.extend(
            (
                TrayMenuItem("模式", submenu=mode_sub, enabled=state.api_ready),
                TrayMenuItem(
                    "TUN 模式",
                    TrayAction.MIHOMO_TOGGLE_TUN,
                    checked=state.tun_enabled,
                    enabled=state.api_ready,
                ),
                TrayMenuItem(
                    "PAC 模式",
                    TrayAction.MIHOMO_TOGGLE_PAC,
                    checked=state.pac_enabled,
                    enabled=state.api_ready,
                ),
                TrayMenuItem(
                    "复制 PAC 地址",
                    TrayAction.MIHOMO_COPY_PAC_URL,
                    enabled=state.pac_enabled,
                ),
                TrayMenuSeparator(),
                TrayMenuItem("打开面板…", TrayAction.SHOW_MIHOMO_WINDOW),
                TrayMenuItem("节点快切", submenu=node_switch_sub, enabled=state.api_ready),
                TrayMenuItem(
                    "订阅",
                    submenu=(
                        TrayMenuItem(
                            "更新当前订阅",
                            TrayAction.MIHOMO_SWITCH_SUBSCRIPTION,
                            action_args=(state.subscription_url,),
                            enabled=bool(state.subscription_url),
                        ),
                        TrayMenuItem(
                            "快速切换",
                            submenu=subscription_switch_sub,
                            enabled=bool(state.saved_subscriptions),
                        ),
                    ),
                ),
                TrayMenuItem("高级与诊断", submenu=advanced_sub),
            )
        )
    elif state.running and state.party_supported:
        items.append(TrayMenuItem("打开控制台", TrayAction.SHOW_MIHOMO_WINDOW))

    return tuple(items)


def mihomo_runtime_from_state(state: MihomoMenuState) -> MihomoRuntimeState:
    return MihomoRuntimeState(
        api_ready=state.api_ready,
        controller="",
        mode=state.mode,
        mixed_port=state.mixed_port,
        port=state.port,
        socks_port=None,
        tun_enabled=state.tun_enabled,
        groups=[
            _runtime_group(group)
            for group in state.groups
        ],
    )


def _runtime_group(group: MihomoProxyGroupState):
    from ..mihomo.api import MihomoProxyGroup

    return MihomoProxyGroup(
        name=group.name,
        group_type=group.group_type,
        current=group.current,
        candidates=list(group.candidates),
        candidate_delays=dict(group.candidate_delays),
        test_url=group.test_url,
    )


def state_runtime_from_menu_state(state: MihomoMenuState) -> MihomoRuntimeState:
    return mihomo_runtime_from_state(state)


def mihomo_primary_group_from_state(state: MihomoMenuState):
    return mihomo_primary_group(state_runtime_from_menu_state(state))


def compact_node_labels_for_state(nodes: list[str]) -> dict[str, str]:
    return compact_node_labels(nodes)
