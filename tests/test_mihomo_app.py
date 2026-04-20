from types import SimpleNamespace
from unittest import mock

from deskvane.app import DeskVaneApp
from deskvane.config import CONFIG_PATH


def _app_stub(*, notifications: bool = True) -> DeskVaneApp:
    app = DeskVaneApp.__new__(DeskVaneApp)
    app.config = SimpleNamespace(
        general=SimpleNamespace(notifications_enabled=notifications),
        mihomo=SimpleNamespace(
            tun_enabled=False,
            tun_direct_processes="",
            subscription_url="",
            saved_subscriptions=[],
        ),
    )
    app.notifier = SimpleNamespace(show=mock.Mock())
    app.tray = SimpleNamespace(refresh=mock.Mock(), rebuild_menu=mock.Mock())
    app.platform_services = SimpleNamespace(
        opener=SimpleNamespace(
            open_path=mock.Mock(return_value=True),
            open_uri=mock.Mock(return_value=True),
        )
    )
    app.mihomo_manager = SimpleNamespace(refresh_tun_bypass_connections=mock.Mock(return_value=0))
    return app


def test_mihomo_toggle_tun_reloads_live_core_config() -> None:
    app = _app_stub(notifications=False)
    app.mihomo_manager.get_runtime_state = mock.Mock(return_value=SimpleNamespace(tun_enabled=False))
    app.mihomo_manager.switch_tun = mock.Mock(return_value=True)
    app.mihomo_manager.reload_core_config = mock.Mock(return_value=True)
    app.mihomo_manager.get_core_status = mock.Mock(return_value=SimpleNamespace(last_error=""))

    with mock.patch("deskvane.app._save_config") as save_config:
        assert DeskVaneApp.mihomo_toggle_tun(app) is True

    save_config.assert_called_once()
    app.mihomo_manager.reload_core_config.assert_called_once()
    assert app.config.mihomo.tun_enabled is True
    app.tray.refresh.assert_called_once()
    app.tray.rebuild_menu.assert_called_once()


def test_mihomo_set_tun_bypass_is_pending_when_core_not_running() -> None:
    app = _app_stub(notifications=False)
    app.mihomo_manager.is_running = mock.Mock(return_value=False)
    app.mihomo_manager.reload_core_config = mock.Mock(return_value=False)
    app.mihomo_manager.reload_config = mock.Mock()

    with mock.patch("deskvane.app._save_config") as save_config:
        assert DeskVaneApp.mihomo_set_tun_bypass(app, "firefox,steam") is True

    save_config.assert_called_once()
    app.mihomo_manager.reload_config.assert_called_once()
    app.mihomo_manager.reload_core_config.assert_not_called()
    app.mihomo_manager.refresh_tun_bypass_connections.assert_not_called()
    assert app.config.mihomo.tun_direct_processes == "firefox, steam"
    app.tray.refresh.assert_called_once()
    app.tray.rebuild_menu.assert_called_once()


def test_mihomo_set_tun_bypass_reloads_live_core_and_closes_existing_connections() -> None:
    app = _app_stub(notifications=False)
    app.mihomo_manager.is_running = mock.Mock(return_value=True)
    app.mihomo_manager.reload_core_config = mock.Mock(return_value=True)
    app.mihomo_manager.reload_config = mock.Mock()
    app.mihomo_manager.refresh_tun_bypass_connections = mock.Mock(return_value=2)

    with mock.patch("deskvane.app._save_config") as save_config:
        assert DeskVaneApp.mihomo_set_tun_bypass(app, "ToDesk") is True

    save_config.assert_called_once()
    app.mihomo_manager.reload_core_config.assert_called_once()
    app.mihomo_manager.reload_config.assert_not_called()
    app.mihomo_manager.refresh_tun_bypass_connections.assert_called_once_with("ToDesk")
    assert app.config.mihomo.tun_direct_processes == "ToDesk"


def test_mihomo_update_subscription_fails_when_live_reload_fails() -> None:
    app = _app_stub(notifications=True)
    app.mihomo_manager.is_running = mock.Mock(return_value=True)
    app.mihomo_manager.save_subscription_provider = mock.Mock(return_value="/tmp/provider.yaml")
    app.mihomo_manager.reload_core_config = mock.Mock(return_value=False)
    app.mihomo_manager.get_core_status = mock.Mock(return_value=SimpleNamespace(last_error="reload failed"))

    with mock.patch("deskvane.app._save_config"), \
         mock.patch("deskvane.app.load_subscription_proxies", return_value=[{"name": "Node-A"}]):
        assert DeskVaneApp.mihomo_update_subscription(app, "https://example.com/sub") is False

    app.mihomo_manager.save_subscription_provider.assert_called_once()
    app.mihomo_manager.reload_core_config.assert_called_once()
    app.notifier.show.assert_called_once()
    title, body = app.notifier.show.call_args.args[:2]
    assert title == "Mihomo 订阅更新失败"
    assert "reload failed" in body
    app.tray.refresh.assert_called_once()
    app.tray.rebuild_menu.assert_called_once()


def test_mihomo_save_subscription_url_updates_saved_subscription_list() -> None:
    app = _app_stub(notifications=False)
    app.config.mihomo.saved_subscriptions = ["https://old.example/sub"]

    with mock.patch("deskvane.app._save_config") as save_config:
        assert DeskVaneApp.mihomo_save_subscription_url(app, "https://new.example/sub") is True

    save_config.assert_called_once()
    assert app.config.mihomo.subscription_url == "https://new.example/sub"
    assert app.config.mihomo.saved_subscriptions == [
        "https://new.example/sub",
        "https://old.example/sub",
    ]


def test_open_config_uses_platform_opener() -> None:
    app = _app_stub(notifications=False)

    assert DeskVaneApp.open_config(app) is None

    app.platform_services.opener.open_path.assert_called_once_with(CONFIG_PATH)


def test_open_config_shows_error_when_opener_fails() -> None:
    app = _app_stub(notifications=False)
    app.platform_services.opener.open_path.return_value = False

    DeskVaneApp.open_config(app)

    app.notifier.show.assert_called_once_with("无法打开配置", str(CONFIG_PATH))


def test_open_mihomo_core_config_uses_platform_opener() -> None:
    app = _app_stub(notifications=False)
    app.mihomo_manager.get_core_status = mock.Mock(
        return_value=SimpleNamespace(config_exists=True, config_path="/tmp/config.yaml", home_dir="/tmp/home")
    )

    DeskVaneApp.open_mihomo_core_config(app)

    app.platform_services.opener.open_path.assert_called_once_with("/tmp/config.yaml")


def test_open_mihomo_logs_uses_platform_opener() -> None:
    app = _app_stub(notifications=False)
    app.mihomo_manager.get_core_status = mock.Mock(
        return_value=SimpleNamespace(config_exists=False, config_path="/tmp/config.yaml", logs_dir="/tmp/logs", home_dir="/tmp/home")
    )

    with mock.patch("deskvane.app.os.path.isdir", return_value=True):
        DeskVaneApp.open_mihomo_logs(app)

    app.platform_services.opener.open_path.assert_called_once_with("/tmp/logs")


def test_mihomo_switch_subscription_reuses_update_flow() -> None:
    app = _app_stub(notifications=False)

    with mock.patch.object(DeskVaneApp, "mihomo_update_subscription", return_value=True) as update:
        assert DeskVaneApp.mihomo_switch_subscription(app, "https://example.com/sub") is True

    update.assert_called_once_with("https://example.com/sub")
