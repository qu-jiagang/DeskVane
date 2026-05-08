from __future__ import annotations

from ...app_context import ModuleContext
from ...core.contributions import SettingsGroupSpec, SettingsSectionSpec, TraySectionContribution
from ...feature_module import FeatureModule
from ...ui.tray_actions import TrayAction, TrayMenuItem


class SubconverterFeatureModule(FeatureModule):
    name = "subconverter.runtime"

    def __init__(self) -> None:
        self._context: ModuleContext | None = None

    def register(self, context: ModuleContext) -> None:
        self._context = context
        context.tasks.register(
            "subconverter",
            lambda: context.app.subconverter_server.start() if context.app.subconverter_server else None,
            lambda: context.app.subconverter_server.stop() if context.app.subconverter_server else None,
        )

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def contribute_settings(self) -> tuple[SettingsSectionSpec, ...]:
        return (
            SettingsSectionSpec(
                id="subconverter",
                label="订阅转换",
                config_attr="subconverter",
                summary="只需配置服务开关和端口。",
                order=50,
                groups=(SettingsGroupSpec("本地订阅服务", "提供本地订阅转 Clash/Mihomo YAML 的转换服务。", ("enable_server", "port")),),
            ),
        )

    def contribute_tray(self) -> tuple[TraySectionContribution, ...]:
        return (
            TraySectionContribution(
                section="tools",
                order=30,
                build_entries=lambda _state: (TrayMenuItem("订阅转换…", TrayAction.SHOW_SUBCONVERTER),),
            ),
        )
