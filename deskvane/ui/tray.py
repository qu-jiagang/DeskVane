from __future__ import annotations

from io import BytesIO
import threading
import time
from typing import TYPE_CHECKING

from ..log import get_logger
from .tray_actions import (
    TrayAction,
    TrayMenuState,
    build_tray_menu_model,
)
from .tray_model import TrayMenuSeparator

if TYPE_CHECKING:
    from ..app import DeskVaneApp

_logger = get_logger("tray")


class TrayController:
    """System tray icon and menu for DeskVane."""

    _SEGMENT_MAP = {
        "0": ("a", "b", "c", "d", "e", "f"),
        "1": ("b", "c"),
        "2": ("a", "b", "d", "e", "g"),
        "3": ("a", "b", "c", "d", "g"),
        "4": ("b", "c", "f", "g"),
        "5": ("a", "c", "d", "f", "g"),
        "6": ("a", "c", "d", "e", "f", "g"),
        "7": ("a", "b", "c"),
        "8": ("a", "b", "c", "d", "e", "f", "g"),
        "9": ("a", "b", "c", "d", "f", "g"),
        "-": ("g",),
        " ": (),
    }

    def __init__(self, app: DeskVaneApp) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise RuntimeError(
                "缺少 pystray 或 Pillow。请重新安装 DeskVane（推荐 .deb 包或 pipx）。"
            ) from exc
        self.app = app
        self._platform = app.platform_services.tray_adapter
        self.pystray = pystray
        self.Image = Image
        self.ImageDraw = ImageDraw
        self._status_refresh_interval_seconds = 2.0
        self._refresh_lock = threading.Lock()
        self._menu_open = False
        self._last_icon_payload: bytes | None = None
        self._last_label_payload: tuple[str, str] | None = None
        self._pending_label_payload: tuple[str, str] | None = None
        self._appindicator_label_setter = self._platform.build_label_setter()
        cpu, gpu = self._get_status_snapshot()
        initial_icon = self._build_icon(cpu=cpu, gpu=gpu)
        self._last_icon_payload = self._icon_to_png_bytes(initial_icon)
        self.icon = pystray.Icon(
            "deskvane",
            initial_icon,
            "DeskVane",
            self._build_menu(cpu=cpu, gpu=gpu),
        )
        self._last_label_payload = self._build_label(cpu=cpu, gpu=gpu)
        self.supports_menu = bool(getattr(self.icon, "HAS_MENU", True))
        self._thread: threading.Thread | None = None
        self._refresh_thread: threading.Thread | None = None

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()
        # Auto-refresh only tray visuals. Menus are never rebuilt in background.
        self._refresh_timer_running = True
        self._refresh_thread = threading.Thread(target=self._auto_refresh, daemon=True)
        self._refresh_thread.start()

    def stop(self) -> None:
        self._refresh_timer_running = False
        self.icon.stop()

    def refresh(self) -> None:
        self._refresh_display(force_icon=True)

    def rebuild_menu(self) -> None:
        self._refresh_display(force_menu=True)

    def _auto_refresh(self) -> None:
        """Periodically refresh tray visuals without rebuilding menus."""
        while getattr(self, "_refresh_timer_running", False):
            time.sleep(self._status_refresh_interval_seconds)
            try:
                self._refresh_display()
            except Exception as exc:
                _logger.debug("tray auto refresh failed: %s", exc)

    @staticmethod
    def _noop(icon=None, item=None) -> None:
        return

    def _get_status_snapshot(self):
        from ..sysmon import get_cpu_status, get_gpu_status

        return get_cpu_status(), get_gpu_status()

    def _refresh_display(self, force_menu: bool = False, force_icon: bool = False) -> None:
        cpu, gpu = self._get_status_snapshot()
        with self._refresh_lock:
            self._bind_menu_observers()
            self._maybe_refresh_menu(cpu=cpu, gpu=gpu, force=force_menu)
            self._maybe_refresh_icon(cpu=cpu, gpu=gpu, force=force_icon)
            self._maybe_refresh_label(cpu=cpu, gpu=gpu)

    def _maybe_refresh_menu(self, cpu=None, gpu=None, force: bool = False) -> None:
        if not force:
            return
        if self._menu_open:
            return

        try:
            self.icon.menu = self._build_menu(cpu=cpu, gpu=gpu)
            self.icon.update_menu()
            self._bind_menu_observers()
        except Exception as exc:
            _logger.debug("tray menu refresh failed: %s", exc)

    def _maybe_refresh_icon(self, cpu=None, gpu=None, force: bool = False) -> None:
        mode = getattr(self.app.config.general, "tray_display", "default")
        if not force and getattr(self.icon, "_appindicator", None) is not None and mode != "default":
            return

        image = self._build_icon(cpu=cpu, gpu=gpu)
        payload = self._icon_to_png_bytes(image)
        if not force and payload == self._last_icon_payload:
            return
        if not force and self._menu_open:
            return

        try:
            self.icon.icon = image
            self._last_icon_payload = payload
        except Exception as exc:
            _logger.debug("tray icon refresh failed: %s", exc)

    def _maybe_refresh_label(self, cpu=None, gpu=None) -> None:
        indicator = getattr(self.icon, "_appindicator", None)
        if indicator is None or self._appindicator_label_setter is None:
            return

        label, guide = self._build_label(cpu=cpu, gpu=gpu)
        if (label, guide) == self._last_label_payload:
            return
        if self._menu_open:
            self._pending_label_payload = (label, guide)
            return
        self._appindicator_label_setter(indicator, label, guide)
        self._last_label_payload = (label, guide)
        self._pending_label_payload = None

    @staticmethod
    def _build_system_status_payload(cpu=None, gpu=None) -> tuple:
        cpu_payload = None
        gpu_payload = None
        if cpu:
            cpu_payload = (round(cpu.usage_pct), round(cpu.temp_c) if cpu.temp_c is not None else None)
        if gpu:
            gpu_payload = (
                round(gpu.usage_pct),
                round(gpu.temp_c),
                gpu.mem_used_mb,
                gpu.mem_total_mb,
            )
        return cpu_payload, gpu_payload

    @staticmethod
    def _icon_to_png_bytes(image) -> bytes:
        buf = BytesIO()
        image.save(buf, "PNG")
        return buf.getvalue()

    def _bind_menu_observers(self) -> None:
        self._platform.bind_menu_observers(self.icon, self._on_menu_open, self._on_menu_close)

    def _on_menu_open(self) -> None:
        self._menu_open = True

    def _on_menu_close(self) -> None:
        self._menu_open = False
        self._flush_pending_label()

    def _flush_pending_label(self) -> None:
        indicator = getattr(self.icon, "_appindicator", None)
        if indicator is None or self._appindicator_label_setter is None:
            return
        if not self._pending_label_payload:
            return
        label, guide = self._pending_label_payload
        if (label, guide) == self._last_label_payload:
            self._pending_label_payload = None
            return
        self._appindicator_label_setter(indicator, label, guide)
        self._last_label_payload = (label, guide)
        self._pending_label_payload = None

    def _build_label(self, cpu=None, gpu=None) -> tuple[str, str]:
        mode = getattr(self.app.config.general, "tray_display", "default")
        if mode == "default":
            return "", ""

        if mode == "cpu_usage" and cpu:
            return f"{round(cpu.usage_pct)}%", "100%"
        if mode == "cpu_temp" and cpu and cpu.temp_c is not None:
            return f"{round(cpu.temp_c)}°", "100°"
        if mode == "gpu_usage" and gpu:
            return f"{round(gpu.usage_pct)}%", "100%"
        if mode == "gpu_temp" and gpu:
            return f"{round(gpu.temp_c)}°", "100°"
        if mode == "gpu_mem" and gpu and gpu.mem_total_mb > 0:
            mem_pct = round(gpu.mem_used_mb / gpu.mem_total_mb * 100)
            return f"{mem_pct}%", "100%"

        return "--", "100%"

    def _translator_status_line(self) -> str:
        if not self.app.translator.enabled:
            return "状态: 未启用"
        return f"状态: {'已暂停' if self.app.translator.paused else '运行中'}"

    def _clipboard_history_enabled(self) -> bool:
        return bool(getattr(self.app.config.general, "clipboard_history_enabled", True))

    # ---------------------------------------------------------------
    # Menu
    # ---------------------------------------------------------------

    def _dispatch(self, fn_name: str):
        def callback(icon, item) -> None:
            self.app.dispatcher.call_soon(getattr(self.app, fn_name))
        return callback

    def _dispatch_call(self, fn, *args):
        def callback(icon, item) -> None:
            self.app.dispatcher.call_soon(fn, *args)
        return callback

    def _build_tray_menu_state(self) -> TrayMenuState:
        if hasattr(self.app, "get_translator_state"):
            translator_state = self.app.get_translator_state()
        else:
            translator = self.app.translator
            translator_state = type(
                "_TranslatorState",
                (),
                {
                    "enabled": getattr(translator, "enabled", False),
                    "paused": getattr(translator, "paused", False),
                    "last_translation_available": bool(getattr(translator, "last_translation", "")),
                },
            )()
        if hasattr(self.app, "get_shell_state"):
            shell_state = self.app.get_shell_state()
        else:
            shell_state = type(
                "_ShellState",
                (),
                {
                    "clipboard_history_enabled": self._clipboard_history_enabled(),
                    "git_proxy_enabled": getattr(self.app, "is_git_proxy_enabled", False),
                    "terminal_proxy_enabled": getattr(self.app, "is_terminal_proxy_enabled", False),
                    "terminal_proxy_supported": bool(self.app.platform_services.info.supports_terminal_proxy),
                },
            )()
        return TrayMenuState(
            translator_enabled=translator_state.enabled,
            translator_paused=translator_state.paused,
            last_translation_available=translator_state.last_translation_available,
            clipboard_history_enabled=shell_state.clipboard_history_enabled,
            is_git_proxy_enabled=shell_state.git_proxy_enabled,
            is_terminal_proxy_enabled=shell_state.terminal_proxy_enabled,
            terminal_proxy_supported=shell_state.terminal_proxy_supported,
        )

    def _render_tray_menu_model(self, model):
        return self.pystray.Menu(*(self._render_tray_menu_entry(entry) for entry in model.items))

    @staticmethod
    def _checked_callback(checked):
        if checked is not True:
            return None
        return (lambda _: bool(checked))

    def _render_tray_menu_entry(self, entry):
        if isinstance(entry, TrayMenuSeparator):
            return self.pystray.Menu.SEPARATOR
        if entry.submenu:
            submenu = self.pystray.Menu(*(self._render_tray_menu_entry(item) for item in entry.submenu))
            return self.pystray.MenuItem(
                entry.label,
                submenu,
                enabled=entry.enabled,
                checked=None,
                radio=entry.radio,
                default=entry.default,
            )
        callback = self._resolve_menu_action(entry.action, entry.action_args)
        return self.pystray.MenuItem(
            entry.label,
            callback,
            enabled=entry.enabled,
            checked=self._checked_callback(entry.checked),
            radio=entry.radio,
            default=entry.default,
        )

    def _resolve_menu_action(self, action: str | None, action_args: tuple[object, ...]):
        if action is None:
            return self._noop
        if action_args:
            return self._dispatch_call(getattr(self.app, action), *action_args)
        return self._dispatch(action)

    def _build_menu(self, cpu=None, gpu=None):
        context = getattr(self.app, "context", None)
        registry = getattr(context, "tray_registry", None) if context is not None else None
        if registry is None:
            raise RuntimeError("DeskVane tray controller requires tray registry context")
        model = build_tray_menu_model(self._build_tray_menu_state(), registry=registry)
        return self._render_tray_menu_model(model)

    # ---------------------------------------------------------------
    # Icon
    # ---------------------------------------------------------------

    def _build_icon(self, cpu=None, gpu=None):
        mode = getattr(self.app.config.general, "tray_display", "default")
        image = self.Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = self.ImageDraw.Draw(image)

        if mode == "default":
            # Brand icon: rounded square with a forward vane mark.
            draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#5b61f6")
            draw.rounded_rectangle((5, 5, 59, 59), radius=13, outline="#93c5fd", width=1)
            mark = [
                (19, 15),
                (26, 15),
                (45, 32),
                (26, 49),
                (19, 49),
                (19, 40),
                (33, 32),
                (19, 24),
            ]
            draw.polygon(mark, fill="white")
            return image

        display_value: int | None = None
        meter_pct = 0
        family_color = "#6366f1"
        value_color = "#e0e0e0"
        accent = "#6366f1"

        if mode.startswith("cpu"):
            family_color = "#a6e3a1"
            accent = "#a6e3a1"
            if cpu:
                if mode == "cpu_usage":
                    display_value = round(cpu.usage_pct)
                    meter_pct = int(max(0, min(100, cpu.usage_pct)))
                    value_color = "#a6e3a1" if cpu.usage_pct < 80 else "#f38ba8"
                elif mode == "cpu_temp":
                    accent = "#fab387"
                    family_color = "#fab387"
                    if cpu.temp_c is not None:
                        display_value = round(cpu.temp_c)
                        meter_pct = int(max(0, min(100, cpu.temp_c)))
                    value_color = "#fab387" if cpu.temp_c and cpu.temp_c > 75 else "#e0e0e0"
        elif mode.startswith("gpu"):
            family_color = "#89b4fa"
            accent = "#89b4fa"
            if gpu:
                if mode == "gpu_usage":
                    display_value = round(gpu.usage_pct)
                    meter_pct = int(max(0, min(100, gpu.usage_pct)))
                    value_color = "#89b4fa" if gpu.usage_pct < 80 else "#cba6f7"
                elif mode == "gpu_temp":
                    accent = "#fab387"
                    family_color = "#fab387"
                    display_value = round(gpu.temp_c)
                    meter_pct = int(max(0, min(100, gpu.temp_c)))
                    value_color = "#fab387" if gpu.temp_c and gpu.temp_c > 80 else "#e0e0e0"
                elif mode == "gpu_mem":
                    if gpu.mem_total_mb > 0:
                        mem_pct = gpu.mem_used_mb / gpu.mem_total_mb * 100
                        display_value = round(mem_pct)
                        meter_pct = int(max(0, min(100, mem_pct)))
                        value_color = "#89b4fa" if mem_pct < 80 else "#f38ba8"
                    else:
                        display_value = None
                        meter_pct = 0
                    family_color = "#cba6f7"
                    accent = "#cba6f7"

        # Visible dark background (not pure black, stands out on all tray themes)
        draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#2d2d3f", outline="#4a4a5e", width=1)
        # Metric family chip in the top-left corner.
        draw.rounded_rectangle((8, 8, 20, 14), radius=3, fill=family_color)
        # Colored accent bar at bottom.
        draw.rounded_rectangle((4, 50, 60, 60), radius=6, fill=accent)
        draw.rectangle((4, 50, 60, 54), fill=accent)
        # Right-hand meter makes small changes visible even when digits are tiny.
        self._draw_meter(draw, 47, 12, 55, 46, meter_pct, fill=value_color)
        # Two-digit seven-segment display is more reliable than font rendering
        # under small tray icon scaling on GNOME.
        self._draw_value_display(draw, 10, 13, display_value, fill=value_color)

        return image

    @staticmethod
    def _draw_centered(draw, cx: int, cy: int, text: str, fill: str, font) -> None:
        """Draw text centered at (cx, cy), compatible with all font types."""
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((cx - tw // 2, cy - th // 2), text, fill=fill, font=font)
        except Exception:
            # Ultimate fallback
            draw.text((cx - 10, cy - 5), text, fill=fill, font=font)

    def _draw_value_display(self, draw, x: int, y: int, value: int | None, fill: str) -> None:
        if value is None:
            text = "--"
        else:
            text = f"{max(0, min(99, value)):02d}"

        off_fill = "#53586f"
        self._draw_digit(draw, x, y, text[0], fill=fill, off_fill=off_fill)
        self._draw_digit(draw, x + 18, y, text[1], fill=fill, off_fill=off_fill)

    def _draw_digit(self, draw, x: int, y: int, digit: str, fill: str, off_fill: str) -> None:
        width = 14
        height = 24
        thickness = 3
        mid = y + height // 2
        segments = {
            "a": (x + thickness, y, x + width - thickness, y + thickness),
            "d": (x + thickness, y + height - thickness, x + width - thickness, y + height),
            "g": (x + thickness, mid - 1, x + width - thickness, mid + 2),
            "f": (x, y + thickness, x + thickness, mid - 1),
            "e": (x, mid + 1, x + thickness, y + height - thickness),
            "b": (x + width - thickness, y + thickness, x + width, mid - 1),
            "c": (x + width - thickness, mid + 1, x + width, y + height - thickness),
        }
        active = set(self._SEGMENT_MAP.get(digit, self._SEGMENT_MAP["-"]))
        for name, box in segments.items():
            draw.rounded_rectangle(box, radius=1, fill=fill if name in active else off_fill)

    @staticmethod
    def _draw_meter(draw, x1: int, y1: int, x2: int, y2: int, pct: int, fill: str) -> None:
        pct = max(0, min(100, pct))
        draw.rounded_rectangle((x1, y1, x2, y2), radius=3, fill="#1f2333", outline="#4a4a5e", width=1)
        inner_top = y1 + 2
        inner_bottom = y2 - 2
        inner_left = x1 + 2
        inner_right = x2 - 2
        inner_height = max(inner_bottom - inner_top, 1)
        fill_height = max(1, round(inner_height * pct / 100)) if pct > 0 else 0
        if fill_height:
            draw.rounded_rectangle(
                (inner_left, inner_bottom - fill_height, inner_right, inner_bottom),
                radius=2,
                fill=fill,
            )
