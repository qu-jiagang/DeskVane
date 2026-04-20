from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from deskvane.app import DeskVaneApp
from deskvane.features.clipboard_history.manager import ClipboardHistoryManager


def test_mihomo_copy_pac_url_prefers_platform_clipboard() -> None:
    app = SimpleNamespace(
        platform_services=SimpleNamespace(
            clipboard=SimpleNamespace(write_text=mock.Mock(return_value=True)),
        ),
        root=SimpleNamespace(
            clipboard_clear=mock.Mock(),
            clipboard_append=mock.Mock(),
            update=mock.Mock(),
        ),
        config=SimpleNamespace(
            general=SimpleNamespace(notifications_enabled=True),
        ),
        notifier=SimpleNamespace(show=mock.Mock()),
        mihomo_manager=SimpleNamespace(pac_url="http://127.0.0.1:7893/pac"),
    )

    DeskVaneApp.mihomo_copy_pac_url(app)

    app.platform_services.clipboard.write_text.assert_called_once_with("http://127.0.0.1:7893/pac")
    app.root.clipboard_clear.assert_not_called()
    app.root.clipboard_append.assert_not_called()
    app.notifier.show.assert_called_once_with("PAC 地址已复制", "http://127.0.0.1:7893/pac")


def test_mihomo_toggle_pac_rolls_back_when_server_start_fails() -> None:
    app = SimpleNamespace(
        config=SimpleNamespace(
            mihomo=SimpleNamespace(pac_enabled=False),
            general=SimpleNamespace(notifications_enabled=True),
        ),
        notifier=SimpleNamespace(show=mock.Mock()),
        mihomo_manager=SimpleNamespace(
            set_pac_enabled=mock.Mock(return_value=False),
            is_running=mock.Mock(return_value=False),
            pac_url="http://127.0.0.1:7893/pac",
        ),
        tray=SimpleNamespace(refresh=mock.Mock(), rebuild_menu=mock.Mock()),
        _save_current_config=mock.Mock(),
    )

    result = DeskVaneApp.mihomo_toggle_pac(app)

    assert result is False
    assert app.config.mihomo.pac_enabled is False
    assert app._save_current_config.call_count == 2
    app.mihomo_manager.set_pac_enabled.assert_called_once_with(True)
    app.notifier.show.assert_not_called()


def test_mihomo_save_pac_config_rolls_back_when_restart_fails() -> None:
    app = SimpleNamespace(
        config=SimpleNamespace(
            mihomo=SimpleNamespace(
                pac_enabled=True,
                pac_port=7893,
                pac_remote_url="https://old.example/pac.js",
                pac_proxy_domains="google.com",
                pac_direct_domains="baidu.com",
                pac_default_action="PROXY",
            ),
            general=SimpleNamespace(notifications_enabled=True),
        ),
        notifier=SimpleNamespace(show=mock.Mock()),
        mihomo_manager=SimpleNamespace(
            restart_pac=mock.Mock(side_effect=[False, True]),
            is_running=mock.Mock(return_value=True),
            reload_core_config=mock.Mock(),
        ),
        tray=SimpleNamespace(refresh=mock.Mock(), rebuild_menu=mock.Mock()),
        _save_current_config=mock.Mock(),
    )

    with mock.patch("deskvane.mihomo.pac.invalidate_remote_pac_cache") as invalidate_cache:
        result = DeskVaneApp.mihomo_save_pac_config(
            app,
            "github.com",
            "example.com",
            "DIRECT",
            7895,
            remote_url="https://new.example/pac.js",
        )

    assert result is False
    assert app.config.mihomo.pac_port == 7893
    assert app.config.mihomo.pac_remote_url == "https://old.example/pac.js"
    assert app.config.mihomo.pac_proxy_domains == "google.com"
    assert app.config.mihomo.pac_direct_domains == "baidu.com"
    assert app.config.mihomo.pac_default_action == "PROXY"
    assert app._save_current_config.call_count == 2
    assert app.mihomo_manager.restart_pac.call_count == 2
    app.mihomo_manager.reload_core_config.assert_not_called()
    app.notifier.show.assert_not_called()
    invalidate_cache.assert_any_call("https://new.example/pac.js")
    invalidate_cache.assert_any_call("https://old.example/pac.js")


def test_clipboard_history_uses_platform_text_clipboard(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "clipboard_history.json"
    monkeypatch.setattr(ClipboardHistoryManager, "_HISTORY_PATH", history_path)

    app = SimpleNamespace(
        platform_services=SimpleNamespace(
            clipboard=SimpleNamespace(
                read_text=mock.Mock(return_value="platform text"),
                write_text=mock.Mock(return_value=True),
            )
        ),
        root=SimpleNamespace(
            after=mock.Mock(),
            clipboard_get=mock.Mock(return_value="fallback text"),
            clipboard_clear=mock.Mock(),
            clipboard_append=mock.Mock(),
        ),
        config=SimpleNamespace(
            general=SimpleNamespace(
                clipboard_history_enabled=False,
                notifications_enabled=False,
            )
        ),
        notifier=SimpleNamespace(show=mock.Mock()),
    )

    manager = ClipboardHistoryManager(app)
    manager._poll_clipboard()

    assert manager.history == ["platform text"]
    app.platform_services.clipboard.read_text.assert_called_once_with("clipboard")

    manager._on_select(0)

    app.platform_services.clipboard.write_text.assert_called_once_with("platform text")
    app.root.clipboard_clear.assert_not_called()
    app.root.clipboard_append.assert_not_called()
