from __future__ import annotations

from ...app_context import ModuleContext
from ...core.contributions import SettingsGroupSpec, SettingsSectionSpec
from ...feature_module import FeatureModule


class MihomoFeatureModule(FeatureModule):
    name = "mihomo.runtime"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None
        self._started = False

    def register(self, context: ModuleContext) -> None:
        self._context = context

    def start(self) -> None:
        if self._context is None:
            raise RuntimeError("mihomo module has not been registered")
        app = self._context.app
        if not getattr(app.config.mihomo, "autostart", False):
            return
        self._started = bool(app.mihomo_manager.start())
        if self._started:
            app.tray.refresh()
            app.tray.rebuild_menu()
            app.root.after(1200, app.tray.refresh)
            app.root.after(1200, app.tray.rebuild_menu)

    def stop(self) -> None:
        if self._context is None:
            return
        self._context.app.mihomo_manager.stop_all()
        self._started = False

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return (
            SettingsSectionSpec(
                id="mihomo",
                label="Mihomo",
                config_attr="mihomo",
                summary="Core 配置可跨平台使用；Mihomo Party 仅 Linux 支持。",
                order=60,
                groups=(
                    SettingsGroupSpec("后端选择", "非 Linux 平台仅显示 Core，Party 只在 Linux 上可用。", ("backend", "autostart")),
                    SettingsGroupSpec("Core 设置", "仅当后端为 Core 时生效。", ("core_binary", "core_home_dir", "external_controller", "secret", "startup_timeout_s", "tun_enabled", "tun_direct_processes")),
                    SettingsGroupSpec("订阅与 Web UI", "订阅地址与浏览器入口。", ("subscription_url", "external_ui", "external_ui_name", "external_ui_url")),
                ),
            ),
        )
