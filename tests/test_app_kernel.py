from __future__ import annotations

from types import SimpleNamespace

from deskvane.app_kernel import AppKernel
from deskvane.features.capture.module import CaptureFeatureModule
from deskvane.features.clipboard_history.module import ClipboardHistoryFeatureModule
from deskvane.features.proxy.module import ProxyFeatureModule
from deskvane.features.shell.module import HotkeyFeatureModule, TrayFeatureModule
from deskvane.features.subconverter.module import SubconverterFeatureModule
from deskvane.features.translator.module import TranslatorFeatureModule


class _FakeApp:
    def __init__(self, **_kwargs) -> None:
        self.dispatcher = object()
        self.started = 0
        self.stopped = 0
        self.mainloop_entered = 0
        self.tray_rebuilds = 0
        self.tray = SimpleNamespace(
            start=lambda: None,
            stop=lambda: None,
            supports_menu=True,
            rebuild_menu=lambda: setattr(self, "tray_rebuilds", self.tray_rebuilds + 1),
        )
        self.hotkeys = SimpleNamespace(start=lambda: None, stop=lambda: None)
        self.translator = SimpleNamespace(start=lambda: None, stop=lambda: None, pause=lambda: None, resume=lambda: None)
        self.subconverter_server = None
        self.platform_services = SimpleNamespace(proxy_session=SimpleNamespace(setup=lambda: None))
        self.config = SimpleNamespace()
        self.root = SimpleNamespace(after=lambda delay, cb: None)
        self.notifier = SimpleNamespace(show=lambda title, body: None)
        self._refresh_proxy_display = lambda: None
        self.terminal_proxy_status_display = ""

    def start_runtime(self) -> None:
        self.started += 1

    def stop_runtime(self) -> None:
        self.stopped += 1

    def enter_mainloop(self) -> None:
        self.mainloop_entered += 1


class _RecordingModule:
    name = "recording"

    def __init__(self) -> None:
        self.context = None
        self.started = 0
        self.stopped = 0

    def register(self, context) -> None:
        self.context = context

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def test_app_kernel_registers_context_and_runs_modules(monkeypatch) -> None:
    module = _RecordingModule()
    fake_platform = SimpleNamespace(name="linux")

    monkeypatch.setattr("deskvane.app_kernel.DeskVaneApp", _FakeApp)

    kernel = AppKernel(platform_services=fake_platform, modules=[module])
    assert module.context is kernel.context
    assert kernel.context.platform is fake_platform
    assert kernel.context.app is kernel.app
    assert kernel.app.tray_rebuilds == 1

    kernel.run()

    assert module.started == 1
    assert module.stopped == 1
    assert kernel.app.mainloop_entered == 1


def test_runtime_modules_register_long_lived_tasks_and_start_hooks() -> None:
    events: list[str] = []
    task_manager = SimpleNamespace(register=lambda name, start, stop, pause=None, resume=None: events.append(f"task:{name}"))
    app = SimpleNamespace(
        tray=SimpleNamespace(start=lambda: None, stop=lambda: None, supports_menu=True, refresh=lambda: events.append("tray.refresh"), rebuild_menu=lambda: events.append("tray.rebuild")),
        hotkeys=SimpleNamespace(start=lambda: None, stop=lambda: None),
        translator=SimpleNamespace(start=lambda: None, stop=lambda: None, pause=lambda: None, resume=lambda: None),
        subconverter_server=SimpleNamespace(start=lambda: None, stop=lambda: None),
        platform_services=SimpleNamespace(proxy_session=SimpleNamespace(setup=lambda: events.append("proxy.setup"))),
        config=SimpleNamespace(),
        root=SimpleNamespace(after=lambda delay, cb: events.append(f"after:{delay}")),
        notifier=SimpleNamespace(show=lambda title, body: events.append(f"notify:{title}")),
        _refresh_proxy_display=lambda: events.append("proxy.refresh"),
        terminal_proxy_status_display="",
    )
    context = SimpleNamespace(app=app, tasks=task_manager)

    modules = [
        TrayFeatureModule(),
        HotkeyFeatureModule(),
        TranslatorFeatureModule(),
        SubconverterFeatureModule(),
        ProxyFeatureModule(),
    ]

    for module in modules:
        module.register(context)

    assert events[:4] == ["task:tray", "task:hotkeys", "task:translator", "task:subconverter"]

    for module in modules:
        module.start()

    assert "proxy.setup" in events
    assert "proxy.refresh" in events


def test_app_kernel_uses_feature_modules_by_default(monkeypatch) -> None:
    monkeypatch.setattr("deskvane.app_kernel.DeskVaneApp", _FakeApp)
    kernel = AppKernel(platform_services=SimpleNamespace(name="linux"))

    assert [type(module) for module in kernel.modules] == [
        CaptureFeatureModule,
        ClipboardHistoryFeatureModule,
        TrayFeatureModule,
        HotkeyFeatureModule,
        TranslatorFeatureModule,
        SubconverterFeatureModule,
        ProxyFeatureModule,
    ]
