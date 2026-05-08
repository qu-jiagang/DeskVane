from io import BytesIO
from types import SimpleNamespace

from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw

from deskvane.ui.tray import TrayController


class _FakeTray:
    Image = PILImage
    ImageDraw = PILImageDraw
    _SEGMENT_MAP = TrayController._SEGMENT_MAP
    _draw_centered = staticmethod(TrayController._draw_centered)
    _draw_digit = TrayController._draw_digit
    _draw_meter = staticmethod(TrayController._draw_meter)
    _draw_value_display = TrayController._draw_value_display

    def __init__(self, mode: str) -> None:
        self.app = SimpleNamespace(
            config=SimpleNamespace(
                general=SimpleNamespace(tray_display=mode),
            )
        )


class _Gpu:
    def __init__(self, usage_pct: float, temp_c: float = 67.0, mem_used_mb: int = 13163, mem_total_mb: int = 32607) -> None:
        self.usage_pct = usage_pct
        self.temp_c = temp_c
        self.mem_used_mb = mem_used_mb
        self.mem_total_mb = mem_total_mb


def test_build_tray_menu_state_reads_git_proxy_flag_from_app() -> None:
    tray = TrayController.__new__(TrayController)
    tray.app = SimpleNamespace(
        get_translator_state=lambda: SimpleNamespace(enabled=False, paused=False, last_translation_available=False),
        get_shell_state=lambda: SimpleNamespace(
            clipboard_history_enabled=True,
            git_proxy_enabled=True,
            terminal_proxy_enabled=False,
            terminal_proxy_supported=False,
        ),
        platform_services=SimpleNamespace(
            info=SimpleNamespace(
                supports_terminal_proxy=False,
            )
        ),
    )
    tray._clipboard_history_enabled = lambda: True

    state = TrayController._build_tray_menu_state(tray)

    assert state.is_git_proxy_enabled is True


def test_render_tray_menu_entry_wraps_checked_true_flag_as_callable() -> None:
    captured = {}

    class _FakePystray:
        class _Menu:
            SEPARATOR = object()

            def __call__(self, *items):
                return tuple(items)

        Menu = _Menu()
        MenuItem = staticmethod(lambda label, action, **kwargs: captured.update({"label": label, "action": action, **kwargs}) or captured)

    tray = TrayController.__new__(TrayController)
    tray.pystray = _FakePystray
    tray._resolve_menu_action = lambda action, args: ("resolved", action, args)

    entry = SimpleNamespace(
        label="Git 代理",
        action="toggle_git_proxy",
        action_args=(),
        enabled=True,
        checked=True,
        radio=False,
        default=False,
        submenu=(),
    )

    rendered = TrayController._render_tray_menu_entry(tray, entry)

    assert rendered["label"] == "Git 代理"
    assert callable(rendered["checked"])
    assert rendered["checked"](None) is True


def test_render_tray_menu_entry_omits_checked_for_unchecked_item() -> None:
    captured = {}

    class _FakePystray:
        class _Menu:
            SEPARATOR = object()

            def __call__(self, *items):
                return tuple(items)

        Menu = _Menu()
        MenuItem = staticmethod(lambda label, action, **kwargs: captured.update({"label": label, "action": action, **kwargs}) or captured)

    tray = TrayController.__new__(TrayController)
    tray.pystray = _FakePystray
    tray._resolve_menu_action = lambda action, args: ("resolved", action, args)

    entry = SimpleNamespace(
        label="帮助",
        action="show_help",
        action_args=(),
        enabled=True,
        checked=False,
        radio=False,
        default=False,
        submenu=(),
    )

    rendered = TrayController._render_tray_menu_entry(tray, entry)

    assert rendered["label"] == "帮助"
    assert rendered["checked"] is None


def test_render_tray_menu_entry_omits_checked_for_submenu_parent() -> None:
    captured = {}

    class _FakePystray:
        class _Menu:
            SEPARATOR = object()

            def __call__(self, *items):
                return tuple(items)

        Menu = _Menu()
        MenuItem = staticmethod(lambda label, action, **kwargs: captured.update({"label": label, "action": action, **kwargs}) or captured)

    tray = TrayController.__new__(TrayController)
    tray.pystray = _FakePystray
    tray._resolve_menu_action = lambda action, args: ("resolved", action, args)

    entry = SimpleNamespace(
        label="代理",
        action=None,
        action_args=(),
        enabled=True,
        checked=True,
        radio=False,
        default=False,
        submenu=(
            SimpleNamespace(
                label="Git 代理",
                action="toggle_git_proxy",
                action_args=(),
                enabled=True,
                checked=True,
                radio=False,
                default=False,
                submenu=(),
            ),
        ),
    )

    rendered = TrayController._render_tray_menu_entry(tray, entry)

    assert rendered["label"] == "代理"
    assert rendered["checked"] is None


def _png_bytes(image) -> bytes:
    buf = BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def test_gpu_usage_icon_changes_when_value_changes() -> None:
    tray = _FakeTray("gpu_usage")

    icon_48 = TrayController._build_icon(tray, cpu=None, gpu=_Gpu(48.0))
    icon_53 = TrayController._build_icon(tray, cpu=None, gpu=_Gpu(53.0))

    assert _png_bytes(icon_48) != _png_bytes(icon_53)


def test_default_and_dynamic_icons_differ() -> None:
    default_tray = _FakeTray("default")
    gpu_tray = _FakeTray("gpu_usage")

    default_icon = TrayController._build_icon(default_tray, cpu=None, gpu=None)
    dynamic_icon = TrayController._build_icon(gpu_tray, cpu=None, gpu=_Gpu(54.0))

    assert _png_bytes(default_icon) != _png_bytes(dynamic_icon)


def test_build_label_for_gpu_usage() -> None:
    tray = _FakeTray("gpu_usage")

    label, guide = TrayController._build_label(tray, cpu=None, gpu=_Gpu(54.0))

    assert label == "54%"
    assert guide == "100%"


def test_build_label_for_default_mode_is_blank() -> None:
    tray = _FakeTray("default")

    label, guide = TrayController._build_label(tray, cpu=None, gpu=_Gpu(54.0))

    assert label == ""
    assert guide == ""
