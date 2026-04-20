from __future__ import annotations

from deskvane.ui.tray_actions import (
    MihomoMenuState,
    MihomoProxyGroupState,
    TrayAction,
    TrayMenuItem,
    TrayMenuSeparator,
    TrayMenuState,
    build_translator_status_line,
    build_tray_menu_model,
)


class _Registry:
    def build_entries(self, section, state):
        if section == "tools":
            return (
                TrayMenuItem("截图并钉住", TrayAction.DO_SCREENSHOT_AND_PIN, default=True),
                TrayMenuItem("纯 OCR", TrayAction.DO_PURE_OCR),
                TrayMenuItem("剪贴板历史", TrayAction.SHOW_CLIPBOARD_HISTORY, enabled=state.clipboard_history_enabled),
                TrayMenuItem("订阅转换…", TrayAction.SHOW_SUBCONVERTER),
            )
        if section == "proxy":
            items = []
            if state.terminal_proxy_supported:
                items.append(
                    TrayMenuItem("终端代理", TrayAction.TOGGLE_TERMINAL_PROXY, checked=state.is_terminal_proxy_enabled)
                )
            items.append(TrayMenuItem("Git 代理", TrayAction.TOGGLE_GIT_PROXY, checked=state.is_git_proxy_enabled))
            return tuple(items)
        if section == "translator":
            return (
                TrayMenuItem(build_translator_status_line(state), enabled=False),
                TrayMenuItem(
                    "复制最近译文",
                    TrayAction.TRANSLATOR_COPY_LAST,
                    default=True,
                    enabled=state.translator_enabled and state.last_translation_available,
                ),
                TrayMenuItem(
                    "恢复监控" if state.translator_paused else "暂停监控",
                    TrayAction.TRANSLATOR_TOGGLE_PAUSE,
                    enabled=state.translator_enabled,
                ),
            )
        return ()


def _labels(items):
    labels = []
    for entry in items:
        if isinstance(entry, TrayMenuSeparator):
            labels.append("---")
        else:
            labels.append(entry.label)
    return labels


def test_build_tray_menu_model_uses_pure_data_tree() -> None:
    model = build_tray_menu_model(
        TrayMenuState(
            translator_enabled=False,
            translator_paused=False,
            last_translation_available=False,
            clipboard_history_enabled=True,
            is_git_proxy_enabled=False,
            is_terminal_proxy_enabled=True,
            terminal_proxy_supported=False,
            mihomo=MihomoMenuState(
                installed=False,
                running=False,
                backend="core",
                title="Mihomo Core",
                api_ready=False,
                party_supported=False,
                mode="rule",
                tun_enabled=False,
                mixed_port=None,
                port=None,
                has_external_ui=False,
            ),
        ),
        registry=_Registry(),
    )

    assert _labels(model.items) == [
        "工具",
        "Mihomo Core · 未安装",
        "代理",
        "翻译",
        "---",
        "设置…",
        "帮助",
        "---",
        "退出",
    ]

    tools = model.items[0]
    assert isinstance(tools, TrayMenuItem)
    assert [item.action for item in tools.submenu] == [
        TrayAction.DO_SCREENSHOT_AND_PIN,
        TrayAction.DO_PURE_OCR,
        TrayAction.SHOW_CLIPBOARD_HISTORY,
        TrayAction.SHOW_SUBCONVERTER,
    ]
    assert tools.submenu[0].default is True
    assert tools.submenu[2].enabled is True

    proxy = model.items[2]
    assert isinstance(proxy, TrayMenuItem)
    assert [entry.label for entry in proxy.submenu] == ["Git 代理"]


def test_build_tray_menu_model_includes_core_mihomo_actions() -> None:
    model = build_tray_menu_model(
        TrayMenuState(
            translator_enabled=True,
            translator_paused=True,
            last_translation_available=True,
            clipboard_history_enabled=True,
            is_git_proxy_enabled=True,
            is_terminal_proxy_enabled=False,
            terminal_proxy_supported=True,
            mihomo=MihomoMenuState(
                installed=True,
                running=True,
                backend="core",
                title="Mihomo Core",
                api_ready=True,
                party_supported=True,
                mode="rule",
                tun_enabled=True,
                mixed_port=7890,
                port=None,
                has_external_ui=True,
                pac_enabled=True,
                subscription_url="https://example.com/sub",
                saved_subscriptions=("https://example.com/sub", "https://example.com/other"),
                groups=(
                    MihomoProxyGroupState(
                        name="PROXY",
                        group_type="Selector",
                        current="Node-A",
                        candidates=("Auto", "Node-A", "Node-B"),
                        candidate_delays={"Node-A": 123},
                    ),
                ),
                manual_delay_results={"Node-A": 234},
            ),
        ),
        registry=_Registry(),
    )

    mihomo = model.items[1]
    assert isinstance(mihomo, TrayMenuItem)
    assert mihomo.label == "Mihomo Core · Rule · TUN · PAC"

    mihomo_labels = _labels(mihomo.submenu)
    assert mihomo_labels[:4] == ["停止", "端口: 7890 | 1 个代理组", "模式", "TUN 模式"]

    mode_item = next(item for item in mihomo.submenu if isinstance(item, TrayMenuItem) and item.label == "模式")
    assert _labels(mode_item.submenu) == ["Rule", "Global", "Direct"]
    assert [item.action_args for item in mode_item.submenu] == [("rule",), ("global",), ("direct",)]

    node_item = next(item for item in mihomo.submenu if isinstance(item, TrayMenuItem) and item.label == "节点快切")
    assert _labels(node_item.submenu)[0] == "当前组: PROXY"
    assert "测试节点延迟" in _labels(node_item.submenu)
    assert any(
        isinstance(entry, TrayMenuItem)
        and entry.action == TrayAction.MIHOMO_SWITCH_PROXY
        and entry.action_args == ("PROXY", "Node-A")
        and entry.checked is True
        for entry in node_item.submenu
    )


def test_build_tray_menu_model_hides_terminal_proxy_when_unsupported() -> None:
    model = build_tray_menu_model(
        TrayMenuState(
            translator_enabled=False,
            translator_paused=False,
            last_translation_available=False,
            clipboard_history_enabled=True,
            is_git_proxy_enabled=True,
            is_terminal_proxy_enabled=True,
            terminal_proxy_supported=False,
            mihomo=MihomoMenuState(
                installed=True,
                running=False,
                backend="core",
                title="Mihomo Core",
                api_ready=False,
                party_supported=False,
                mode="rule",
                tun_enabled=False,
                mixed_port=None,
                port=None,
                has_external_ui=False,
            ),
        ),
        registry=_Registry(),
    )

    proxy = model.items[2]
    assert isinstance(proxy, TrayMenuItem)
    assert [entry.label for entry in proxy.submenu] == ["Git 代理"]
