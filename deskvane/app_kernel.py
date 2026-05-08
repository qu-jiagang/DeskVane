from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace

from .app import DeskVaneApp
from .app_context import ModuleContext
from .core import ConfigManager, RuntimeApi, RuntimeEventStore, RuntimeHttpServer, TaskManager
from .feature_module import FeatureModule
from .features.capture.module import CaptureFeatureModule
from .features.clipboard_history.module import ClipboardHistoryFeatureModule
from .features.proxy.module import ProxyFeatureModule
from .features.shell.module import HotkeyFeatureModule, TrayFeatureModule
from .features.shell.registries import HotkeyRegistry, SettingsRegistry, TrayRegistry
from .features.subconverter.module import SubconverterFeatureModule
from .features.translator.module import TranslatorFeatureModule
from .platform.base import PlatformServices
from .platform.factory import get_platform_services


class AppKernel:
    """Application composition root for DeskVane."""

    def __init__(
        self,
        *,
        platform_services: PlatformServices | None = None,
        config_manager: ConfigManager | None = None,
        task_manager: TaskManager | None = None,
        modules: Iterable[FeatureModule] | None = None,
    ) -> None:
        self.platform_services = platform_services or get_platform_services()
        self.config_manager = config_manager or ConfigManager()
        self.task_manager = task_manager or TaskManager()
        self.hotkey_registry = HotkeyRegistry()
        self.settings_registry = SettingsRegistry()
        self.tray_registry = TrayRegistry()
        provisional_context = SimpleNamespace(
            hotkey_registry=self.hotkey_registry,
            settings_registry=self.settings_registry,
            tray_registry=self.tray_registry,
        )
        self.app = DeskVaneApp(
            platform_services=self.platform_services,
            config_manager=self.config_manager,
            context=provisional_context,
        )
        self.context = ModuleContext(
            platform=self.platform_services,
            config=self.config_manager,
            tasks=self.task_manager,
            app=self.app,
            ui_dispatcher=self.app.dispatcher,
            hotkey_registry=self.hotkey_registry,
            settings_registry=self.settings_registry,
            tray_registry=self.tray_registry,
        )
        self.app.context = self.context
        self.runtime_events = RuntimeEventStore()
        self.runtime_api = RuntimeApi(self.app, events=self.runtime_events)
        self.runtime_server = RuntimeHttpServer(self.runtime_api)
        self.task_manager.register("runtime-api", self.runtime_server.start, self.runtime_server.stop)
        self.modules = list(
            modules
            or [
                CaptureFeatureModule(),
                ClipboardHistoryFeatureModule(),
                TrayFeatureModule(),
                HotkeyFeatureModule(),
                TranslatorFeatureModule(),
                SubconverterFeatureModule(),
                ProxyFeatureModule(),
            ]
        )
        for module in self.modules:
            module.register(self.context)
            self.hotkey_registry.extend(getattr(module, "contribute_hotkeys", lambda: ())())
            self.settings_registry.extend(getattr(module, "contribute_settings", lambda: ())())
            self.tray_registry.extend(getattr(module, "contribute_tray", lambda: ())())
        self.app.tray.rebuild_menu()
        self.hotkey_registry.bind(self.app)

    def run(self) -> None:
        try:
            for module in self.modules:
                module.start()
            self.task_manager.start_all()
            self.app.enter_mainloop()
        finally:
            self.task_manager.stop_all()
            for module in reversed(self.modules):
                module.stop()
