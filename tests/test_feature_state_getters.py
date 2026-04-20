from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from deskvane.app import DeskVaneApp


def test_feature_state_getters_expose_capture_clipboard_proxy_subconverter() -> None:
    app = DeskVaneApp.__new__(DeskVaneApp)
    app.config = SimpleNamespace(
        screenshot=SimpleNamespace(
            save_dir="~/Pictures/DeskVane",
            copy_to_clipboard=True,
            save_to_disk=False,
            notifications_enabled=False,
        ),
        general=SimpleNamespace(
            clipboard_history_enabled=True,
            notifications_enabled=True,
        ),
        proxy=SimpleNamespace(address="http://127.0.0.1:7890"),
        subconverter=SimpleNamespace(enable_server=True, port=7777),
        mihomo=SimpleNamespace(
            external_ui="",
            external_ui_name="",
            external_ui_url="",
            pac_enabled=False,
            subscription_url="",
            saved_subscriptions=[],
        ),
    )
    app.clipboard_history = SimpleNamespace(history=["a", "b"], _overlay=None)
    app.platform_services = SimpleNamespace(info=SimpleNamespace(supports_terminal_proxy=True, supports_mihomo_party=False))
    app.platform_services.proxy_session = SimpleNamespace(is_enabled=lambda: False)
    app.tray = SimpleNamespace(supports_menu=True)
    app.git_proxy_status_display = "已开启"
    app.terminal_proxy_status_display = "未开启"
    app.subconverter_server = SimpleNamespace(server=object())

    with mock.patch("deskvane.app.GitProxyManager.get_status", return_value=SimpleNamespace(enabled=True)):
        capture_state = DeskVaneApp.get_capture_state(app)
        history_state = DeskVaneApp.get_clipboard_history_state(app)
        shell_state = DeskVaneApp.get_shell_state(app)
        proxy_state = DeskVaneApp.get_proxy_state(app)
        subconverter_state = DeskVaneApp.get_subconverter_state(app)

    assert capture_state.copy_to_clipboard is True
    assert history_state.item_count == 2
    assert shell_state.git_proxy_enabled is True
    assert proxy_state.address == "http://127.0.0.1:7890"
    assert subconverter_state.running is True


def test_get_shell_state_does_not_require_tray_during_tray_bootstrap() -> None:
    app = DeskVaneApp.__new__(DeskVaneApp)
    app.config = SimpleNamespace(
        general=SimpleNamespace(
            clipboard_history_enabled=True,
            notifications_enabled=True,
        ),
    )
    app.platform_services = SimpleNamespace(info=SimpleNamespace(supports_terminal_proxy=False))
    app.platform_services.proxy_session = SimpleNamespace(is_enabled=lambda: False)

    with mock.patch("deskvane.app.GitProxyManager.get_status", return_value=SimpleNamespace(enabled=False)):
        shell_state = DeskVaneApp.get_shell_state(app)

    assert shell_state.tray_supports_menu is True
    assert shell_state.git_proxy_enabled is False
