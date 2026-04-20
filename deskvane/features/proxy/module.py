from __future__ import annotations

from ...app_context import ModuleContext
from ...core.contributions import SettingsGroupSpec, SettingsSectionSpec, TraySectionContribution
from ...feature_module import FeatureModule
from ...ui.tray_actions import TrayAction, TrayMenuItem


class ProxyFeatureModule(FeatureModule):
    name = "proxy.runtime"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None

    def register(self, context: ModuleContext) -> None:
        self._context = context

    def start(self) -> None:
        if self._context is None:
            raise RuntimeError("proxy module has not been registered")
        app = self._context.app
        app.platform_services.proxy_session.setup()
        app.terminal_proxy_status_display = "未知"
        app._refresh_proxy_display()

    def stop(self) -> None:
        return

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return (
            SettingsSectionSpec(
                id="proxy",
                label="代理",
                config_attr="proxy",
                summary="Git 和终端共用这一组代理设置。",
                order=40,
                groups=(SettingsGroupSpec("代理地址", "Git 和终端都复用这里。", ("address",)),),
            ),
        )

    def contribute_tray(self) -> tuple[TraySectionContribution, ...]:
        return (
            TraySectionContribution(
                section="proxy",
                order=10,
                build_entries=lambda state: (
                    (TrayMenuItem("终端代理", TrayAction.TOGGLE_TERMINAL_PROXY, checked=state.is_terminal_proxy_enabled),)
                    if state.terminal_proxy_supported
                    else ()
                ),
            ),
            TraySectionContribution(
                section="proxy",
                order=20,
                build_entries=lambda state: (
                    TrayMenuItem("Git 代理", TrayAction.TOGGLE_GIT_PROXY, checked=state.is_git_proxy_enabled),
                ),
            ),
        )
