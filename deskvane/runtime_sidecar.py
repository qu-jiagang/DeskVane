from __future__ import annotations

import signal
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import NoReturn
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import AppConfig
from .core import ConfigManager, RuntimeApi, RuntimeEventStore, RuntimeHttpServer
from .features.capture.state import CaptureState
from .features.clipboard_history.state import ClipboardHistoryState
from .features.proxy.git_proxy import GitProxyManager
from .features.proxy.state import ProxyState
from .features.proxy.terminal_proxy import TerminalProxyManager
from .features.shell.state import ShellState
from .features.subconverter.state import SubconverterState
from .features.translator.state import TranslatorState
from .platform.factory import get_platform_services
from .translator.ollama import OllamaClient
from .translator.text_utils import ellipsize, is_translatable, normalize_text


class _TranslationPopupBridge:
    """Small Tk-only popup bridge for sidecar clipboard translations."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, str, int]] = queue.Queue()
        self._started = False
        self._lock = threading.Lock()

    def show(self, text: str, width_px: int) -> None:
        if not text.strip():
            return
        self._ensure_started()
        self._queue.put(("show", text, width_px))

    def show_loading(self, text: str, width_px: int) -> None:
        self._ensure_started()
        preview = ellipsize(text.replace("\n", " / "), 160) or "剪贴板文本"
        self._queue.put(("loading", preview, width_px))

    def show_error(self, message: str, width_px: int) -> None:
        self._ensure_started()
        self._queue.put(("error", message, width_px))

    def stop(self) -> None:
        if self._started:
            self._queue.put(("stop", "", 0))

    def _ensure_started(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            threading.Thread(target=self._run, name="deskvane-translation-popup", daemon=True).start()

    @staticmethod
    def _format_display_text(text: str) -> str:
        stripped = normalize_text(text)
        if len(stripped) < 120 or "\n\n" in stripped:
            return stripped
        if "\n" in stripped:
            return "\n\n".join(line.strip() for line in stripped.splitlines() if line.strip())

        import re

        normalized = re.sub(r"\s+", " ", stripped)
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？；.!?;])\s+", normalized)
            if sentence.strip()
        ]
        if len(sentences) <= 1:
            return normalized

        paragraphs: list[str] = []
        current: list[str] = []
        current_len = 0
        for sentence in sentences:
            starts_new_topic = bool(
                current
                and (
                    sentence.startswith(("然而", "但是", "同时", "此外", "为了", "之前", "最后"))
                    or sentence.startswith(("DeepSeek", "OpenAI", "我们开源", "蒸馏"))
                )
            )
            if starts_new_topic or (current and current_len + len(sentence) > 120):
                paragraphs.append(" ".join(current))
                current = []
                current_len = 0
            current.append(sentence)
            current_len += len(sentence)
        if current:
            paragraphs.append(" ".join(current))
        return "\n\n".join(paragraphs)

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            return

        try:
            root = tk.Tk()
        except Exception:
            return

        root.withdraw()
        window: tk.Toplevel | None = None
        status_label: tk.Label | None = None
        text_widget: tk.Text | None = None
        scrollbar: tk.Scrollbar | None = None
        loading = False
        spinner_index = 0
        spinner_frames = ("|", "/", "-", "\\")

        def choose_font(size: int = 11) -> tuple[str, int]:
            try:
                import tkinter.font as tkfont

                families = set(tkfont.families(root))
                for family in (
                    "Noto Sans CJK SC",
                    "Microsoft YaHei UI",
                    "WenQuanYi Micro Hei",
                    "PingFang SC",
                    "Source Han Sans SC",
                    "Arial",
                ):
                    if family in families:
                        return (family, size)
            except Exception:
                pass
            return ("sans-serif", size)

        def copy_text() -> None:
            if text_widget is None:
                return
            text = text_widget.get("1.0", "end").strip()
            root.clipboard_clear()
            root.clipboard_append(text)

        def hide() -> None:
            if window is not None:
                window.withdraw()

        def set_body(text: str, *, state: str = "normal") -> None:
            assert text_widget is not None
            display_text = text if state == "loading" else self._format_display_text(text)
            text_widget.configure(state=tk.NORMAL)
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", display_text)
            text_widget.configure(state=tk.DISABLED)
            text_widget.yview_moveto(0.0)
            if status_label is not None:
                status_label.configure(
                    text={"loading": "翻译中", "error": "翻译失败"}.get(state, "翻译完成"),
                    fg={"loading": "#185abc", "error": "#9f1239"}.get(state, "#17633a"),
                )

        def desired_popup_height(text: str, width: int, screen_h: int) -> int:
            del width
            max_h = max(260, int(screen_h * 0.72))
            min_h = 180
            if text_widget is None:
                return min_h
            try:
                text_widget.update_idletasks()
                count = text_widget.count("1.0", "end", "displaylines")
                display_lines = int(count[0]) if count else max(1, text.count("\n") + 1)
                line_height = max(16, int(text_widget.tk.call("font", "metrics", text_widget.cget("font"), "-linespace")))
                content_h = display_lines * line_height + 94
            except Exception:
                content_h = 120 + min(len(text), 4000) // 4
            return max(min_h, min(max_h, content_h))

        def desired_popup_width(text: str, requested_width: int, screen_w: int) -> int:
            max_w = max(420, int(screen_w * 0.58))
            longest_line = max((len(line) for line in text.splitlines()), default=len(text))
            if len(text) > 180 or longest_line > 34:
                requested_width = max(requested_width, 520)
            if len(text) > 420 or longest_line > 58:
                requested_width = max(requested_width, 620)
            return max(360, min(max_w, requested_width))

        def pulse() -> None:
            nonlocal spinner_index
            if loading and status_label is not None and window is not None and window.winfo_viewable():
                status_label.configure(text=f"翻译中 {spinner_frames[spinner_index % len(spinner_frames)]}")
                spinner_index += 1
            root.after(140, pulse)

        def poll() -> None:
            nonlocal window, status_label, text_widget, scrollbar, loading
            while True:
                try:
                    command, text, width_px = self._queue.get_nowait()
                except queue.Empty:
                    break
                if command == "stop":
                    root.destroy()
                    return
                if command not in {"show", "loading", "error"}:
                    continue
                if window is None or not window.winfo_exists():
                    window = tk.Toplevel(root)
                    window.title("DeskVane 翻译")
                    window.configure(bg="#f8fafc")
                    window.attributes("-topmost", True)
                    window.protocol("WM_DELETE_WINDOW", hide)
                    frame = tk.Frame(window, bg="#f8fafc", padx=16, pady=12)
                    frame.pack(fill=tk.BOTH, expand=True)
                    status_label = tk.Label(
                        frame,
                        anchor="w",
                        bg="#f8fafc",
                        fg="#185abc",
                        font=(*choose_font(10), "bold"),
                    )
                    status_label.pack(fill=tk.X, pady=(0, 10))
                    text_frame = tk.Frame(
                        frame,
                        bg="#ffffff",
                        highlightthickness=1,
                        highlightbackground="#d7dee8",
                    )
                    text_frame.pack(fill=tk.BOTH, expand=True)
                    text_widget = tk.Text(
                        text_frame,
                        wrap=tk.CHAR,
                        bg="#ffffff",
                        fg="#18202c",
                        font=choose_font(11),
                        relief=tk.FLAT,
                        borderwidth=0,
                        highlightthickness=0,
                        padx=14,
                        pady=12,
                        spacing1=2,
                        spacing2=1,
                        spacing3=7,
                    )
                    scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
                    text_widget.configure(yscrollcommand=scrollbar.set)
                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    buttons = tk.Frame(frame, bg="#f8fafc")
                    buttons.pack(fill=tk.X, pady=(8, 0))
                    tk.Button(buttons, text="复制", command=copy_text).pack(side=tk.RIGHT, padx=(8, 0))
                    tk.Button(buttons, text="关闭", command=hide).pack(side=tk.RIGHT)
                    window.bind("<Escape>", lambda _event: hide())
                loading = command == "loading"
                if command == "loading":
                    set_body(f"正在翻译剪贴板内容...\n\n{text}", state="loading")
                elif command == "error":
                    set_body(str(text), state="error")
                else:
                    set_body(text, state="done")
                try:
                    pointer_x, pointer_y = root.winfo_pointerxy()
                except Exception:
                    pointer_x, pointer_y = 80, 80
                screen_w = root.winfo_screenwidth()
                screen_h = root.winfo_screenheight()
                width = desired_popup_width(text, int(width_px or 360), screen_w)
                height = desired_popup_height(text, width, screen_h)
                x = min(max(0, pointer_x + 18), max(0, screen_w - width - 20))
                y = min(max(0, pointer_y + 18), max(0, screen_h - height - 40))
                window.geometry(f"{width}x{height}+{x}+{y}")
                if scrollbar is not None and text_widget is not None:
                    text_widget.update_idletasks()
                    first, last = text_widget.yview()
                    if first <= 0.0 and last >= 1.0:
                        scrollbar.pack_forget()
                    elif not scrollbar.winfo_ismapped():
                        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                window.deiconify()
                window.lift()
            root.after(80, poll)

        root.after(80, poll)
        root.after(140, pulse)
        root.mainloop()


class HeadlessRuntimeApp:
    """Tk-free app facade used by the Tauri sidecar runtime API."""

    _LEGACY_ACTIONS = frozenset(
        {
            "capture.screenshot",
            "capture.screenshot_and_pin",
            "capture.interactive_screenshot",
            "capture.pure_ocr",
            "capture.pin_clipboard",
            "clipboard.show_history",
            "settings.show",
            "help.show",
            "subconverter.show",
            "translator.copy_last",
        }
    )

    supported_runtime_actions = frozenset(
        {
            "capture.screenshot",
            "capture.screenshot_and_pin",
            "capture.interactive_screenshot",
            "capture.pure_ocr",
            "capture.pin_clipboard",
            "clipboard.show_history",
            "settings.show",
            "help.show",
            "subconverter.show",
            "translator.copy_last",
            "proxy.toggle_git",
            "proxy.toggle_terminal",
            "translator.retry_last",
            "translator.toggle_pause",
            "app.quit",
        }
    )

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        events: RuntimeEventStore | None = None,
    ) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.events = events or RuntimeEventStore()
        self.platform_services = get_platform_services()
        self.config = self.config_manager.load()
        self._quit_requested = False
        self.subconverter_server = None
        self.clipboard_history = self._load_clipboard_history()
        self._clipboard_last_text = ""
        self._clipboard_poll_stop = threading.Event()
        self._clipboard_poll_thread: threading.Thread | None = None
        self.translator_paused = True
        self.translator_running = False
        self.translator_status_key = "disabled"
        self.translator_status_text = "未启用"
        self.translator_model_label = self.config.translator.model or "自动"
        self.last_translation = ""
        self.last_translation_preview = "-"
        self.last_input_text = ""
        self._auto_translate_lock = threading.Lock()
        self._auto_translate_pending: set[str] = set()
        self._last_auto_translated_text = ""
        self._translation_popup = _TranslationPopupBridge()
        self.legacy_process: subprocess.Popen | None = None
        self._refresh_proxy_display()
        self._sync_clipboard_history_polling()
        self._sync_subconverter_server()
        self._sync_translator_state()

    def reload_config(self) -> None:
        old_server = self.subconverter_server
        self.config = self.config_manager.load()
        self._refresh_proxy_display()
        self._sync_clipboard_history_polling()
        if (
            old_server is not None
            and int(getattr(old_server, "port", 0)) != int(self.config.subconverter.port)
        ):
            old_server.stop()
            self.subconverter_server = None
        self._sync_subconverter_server()
        self._sync_translator_state()

    def quit(self) -> None:
        self._quit_requested = True
        self._translation_popup.stop()
        if self.subconverter_server is not None:
            self.subconverter_server.stop()
        self._clipboard_poll_stop.set()
        if self.legacy_process is not None and self.legacy_process.poll() is None:
            self.legacy_process.terminate()
        self.events.add("app.quit", "Headless runtime quit requested")

    def get_capture_state(self) -> CaptureState:
        cfg = self.config.screenshot
        return CaptureState(
            save_dir=str(cfg.save_dir),
            copy_to_clipboard=bool(cfg.copy_to_clipboard),
            save_to_disk=bool(cfg.save_to_disk),
            notifications_enabled=bool(cfg.notifications_enabled),
        )

    def get_clipboard_history_state(self) -> ClipboardHistoryState:
        return ClipboardHistoryState(
            enabled=bool(self.config.general.clipboard_history_enabled),
            item_count=len(self.clipboard_history),
            overlay_visible=False,
        )

    def get_clipboard_history_items(self) -> list[dict[str, object]]:
        return [
            {
                "index": index,
                "text": text,
                "preview": text.replace("\n", " ↵ ")[:120],
            }
            for index, text in enumerate(self.clipboard_history)
        ]

    def select_clipboard_history_item(self, index: int) -> dict[str, object]:
        if index < 0 or index >= len(self.clipboard_history):
            raise ValueError("clipboard history index out of range")
        text = self.clipboard_history[index]
        if not self.platform_services.clipboard.write_text(text):
            raise RuntimeError("failed to write clipboard text")
        self._clipboard_last_text = text
        self.clipboard_history.pop(index)
        self.clipboard_history.insert(0, text)
        self._save_clipboard_history()
        return {"index": 0, "text": text, "preview": text.replace("\n", " ↵ ")[:120]}

    def get_translator_state(self) -> TranslatorState:
        return TranslatorState(
            enabled=bool(self.config.translator.enabled),
            paused=self.translator_paused,
            running=self.translator_running,
            status_key=self.translator_status_key,
            status_text=self.translator_status_text,
            model_label=self.translator_model_label,
            backend_label="python-sidecar",
            last_translation_available=bool(self.last_translation),
            last_translation_preview=self.last_translation_preview,
        )

    def get_shell_state(self) -> ShellState:
        return ShellState(
            tray_supports_menu=True,
            notifications_enabled=bool(self.config.general.notifications_enabled),
            clipboard_history_enabled=bool(self.config.general.clipboard_history_enabled),
            autostart_enabled=bool(self.config.general.autostart_enabled),
            git_proxy_enabled=self.is_git_proxy_enabled,
            terminal_proxy_enabled=self.is_terminal_proxy_enabled,
            terminal_proxy_supported=True,
        )

    def get_proxy_state(self) -> ProxyState:
        return ProxyState(
            address=str(self.config.proxy.address),
            git_proxy_enabled=self.is_git_proxy_enabled,
            terminal_proxy_enabled=self.is_terminal_proxy_enabled,
            terminal_proxy_supported=True,
            git_proxy_status_display=self.git_proxy_status_display,
            terminal_proxy_status_display=self.terminal_proxy_status_display,
        )

    def get_subconverter_state(self) -> SubconverterState:
        server = self.subconverter_server
        return SubconverterState(
            enabled=bool(self.config.subconverter.enable_server),
            port=int(self.config.subconverter.port),
            running=bool(server and getattr(server, "server", None)),
        )

    def get_system_state(self) -> dict[str, object]:
        from .sysmon import get_cpu_status, get_gpu_status

        cpu = get_cpu_status()
        gpu = get_gpu_status()
        return {
            "cpu": None
            if cpu is None
            else {
                "usage_pct": cpu.usage_pct,
                "temp_c": cpu.temp_c,
                "core_count": cpu.core_count,
            },
            "gpu": None
            if gpu is None
            else {
                "name": gpu.name,
                "usage_pct": gpu.usage_pct,
                "temp_c": gpu.temp_c,
                "mem_used_mb": gpu.mem_used_mb,
                "mem_total_mb": gpu.mem_total_mb,
            },
        }

    def _sync_subconverter_server(self) -> None:
        enabled = bool(self.config.subconverter.enable_server)
        if not enabled:
            if self.subconverter_server is not None:
                self.subconverter_server.stop()
                self.subconverter_server = None
            return

        if self.subconverter_server is None:
            from .subconverter.server import SubconverterServer

            self.subconverter_server = SubconverterServer(int(self.config.subconverter.port))
            self.subconverter_server.start()

    def _sync_clipboard_history_polling(self) -> None:
        if not self.config.general.clipboard_history_enabled:
            self._clipboard_poll_stop.set()
            return
        if self._clipboard_poll_thread is not None and self._clipboard_poll_thread.is_alive():
            return
        self._clipboard_poll_stop.clear()
        self._clipboard_poll_thread = threading.Thread(target=self._poll_clipboard_history, daemon=True)
        self._clipboard_poll_thread.start()

    def _poll_clipboard_history(self) -> None:
        while not self._clipboard_poll_stop.wait(1.0):
            if not self.config.general.clipboard_history_enabled:
                continue
            try:
                text = self.platform_services.clipboard.read_text("clipboard")
            except Exception:
                text = None
            text = normalize_text(text or "")
            if not text or text == self._clipboard_last_text:
                continue
            self._clipboard_last_text = text
            if text in self.clipboard_history:
                self.clipboard_history.remove(text)
            self.clipboard_history.insert(0, text)
            self.clipboard_history = self.clipboard_history[:50]
            self._save_clipboard_history()
            self._maybe_auto_translate(text)

    @staticmethod
    def _clipboard_history_path() -> Path:
        from .config import CONFIG_DIR

        return CONFIG_DIR / "clipboard_history.json"

    def _load_clipboard_history(self) -> list[str]:
        try:
            path = self._clipboard_history_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [str(item) for item in data[:50]]
        except Exception:
            pass
        return []

    def _save_clipboard_history(self) -> None:
        try:
            path = self._clipboard_history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.clipboard_history[:50], ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _maybe_auto_translate(self, text: str) -> None:
        cfg = self.config.translator
        if not cfg.enabled or not cfg.clipboard_enabled or self.translator_paused:
            return
        if text == self._last_auto_translated_text:
            return
        if not is_translatable(text, cfg.min_chars) or len(text) > cfg.max_chars:
            return
        with self._auto_translate_lock:
            if text in self._auto_translate_pending:
                return
            self._auto_translate_pending.add(text)
        threading.Thread(target=self._auto_translate_text, args=(text,), daemon=True).start()

    def _auto_translate_text(self, text: str) -> None:
        popup_enabled = bool(self.config.translator.popup_enabled)
        popup_width = int(self.config.translator.popup_width_px)
        try:
            if popup_enabled:
                self._translation_popup.show_loading(text, popup_width)
            if int(self.config.translator.debounce_ms) > 0:
                time.sleep(int(self.config.translator.debounce_ms) / 1000)
            result = self.translate_text(text)
            self._last_auto_translated_text = text
            if self.config.translator.auto_copy:
                self.platform_services.clipboard.write_text(str(result.get("text", "")))
            if popup_enabled:
                self._translation_popup.show(str(result.get("text", "")), popup_width)
            self.events.add(
                "translator.auto_translated",
                f"Clipboard text translated: {self.last_translation_preview}",
                data={
                    "preview": self.last_translation_preview,
                    "model": result.get("model", ""),
                    "elapsed_ms": result.get("elapsed_ms", 0),
                    "popup_enabled": bool(self.config.translator.popup_enabled),
                },
            )
        except Exception as exc:
            self.events.add(
                "translator.error",
                f"Clipboard translation failed: {exc}",
                data={"error": str(exc)},
            )
            if popup_enabled:
                self._translation_popup.show_error(str(exc), popup_width)
        finally:
            with self._auto_translate_lock:
                self._auto_translate_pending.discard(text)

    @property
    def is_git_proxy_enabled(self) -> bool:
        try:
            return GitProxyManager.get_status().enabled
        except Exception:
            return False

    @property
    def is_terminal_proxy_enabled(self) -> bool:
        try:
            return TerminalProxyManager.get_status().enabled
        except Exception:
            return False

    def toggle_git_proxy(self) -> None:
        if self.is_git_proxy_enabled:
            GitProxyManager.disable()
        else:
            GitProxyManager.enable(self.config.proxy.address)
        self._refresh_proxy_display()

    def toggle_terminal_proxy(self) -> None:
        if self.is_terminal_proxy_enabled:
            TerminalProxyManager.disable(self.config.proxy.address)
        else:
            TerminalProxyManager.enable(self.config.proxy.address)
        self._refresh_proxy_display()

    def _refresh_proxy_display(self) -> None:
        try:
            self.git_proxy_status_display = GitProxyManager.get_status().display
        except Exception:
            self.git_proxy_status_display = "未知"

        try:
            enabled = TerminalProxyManager.get_status().enabled
            self.terminal_proxy_status_display = "已开启 (新终端有效)" if enabled else "未开启"
        except Exception:
            self.terminal_proxy_status_display = "未知"

    def _sync_translator_state(self) -> None:
        self.translator_model_label = self.config.translator.model or "自动"
        if not self.config.translator.enabled:
            self.translator_paused = True
            self.translator_running = False
            self.translator_status_key = "disabled"
            self.translator_status_text = "未启用"
            return
        self.translator_running = True
        if self.translator_status_key == "disabled":
            self.translator_status_key = "paused"
            self.translator_status_text = "已暂停"

    def _build_translator_client(self) -> OllamaClient:
        cfg = self.config.translator
        return OllamaClient(
            host=cfg.ollama_host,
            timeout_s=cfg.request_timeout_s,
            prompt_extra=cfg.prompt_extra,
            disable_thinking=cfg.disable_thinking,
            max_output_tokens=cfg.max_output_tokens,
        )

    def translate_text(self, text: str) -> dict[str, object]:
        if not self.config.translator.enabled:
            raise RuntimeError("translator is disabled")
        if self.translator_paused:
            raise RuntimeError("translator is paused")

        normalized = normalize_text(text)
        cfg = self.config.translator
        if not is_translatable(normalized, cfg.min_chars):
            raise ValueError("text is too short or not translatable")
        if len(normalized) > cfg.max_chars:
            raise ValueError(f"text exceeds max_chars: {len(normalized)} > {cfg.max_chars}")

        self.last_input_text = normalized
        self.translator_status_key = "busy"
        self.translator_status_text = "翻译中"
        try:
            result = self._build_translator_client().translate(
                text=normalized,
                preferred_model=cfg.model,
                source_language=cfg.source_language,
                target_language=cfg.target_language,
                keep_alive=cfg.keep_alive,
            )
        except Exception:
            self.translator_status_key = "error"
            self.translator_status_text = "翻译失败"
            raise

        self.last_translation = result.text
        self.translator_model_label = result.model
        self.last_translation_preview = ellipsize(result.text.replace("\n", " / "), 36) or "-"
        self.translator_status_key = "ready"
        self.translator_status_text = f"已翻译 {result.elapsed_ms} ms"
        return {
            "text": result.text,
            "model": result.model,
            "elapsed_ms": result.elapsed_ms,
        }

    def do_screenshot(self) -> None:
        self._dispatch_legacy_action("capture.screenshot")

    def do_screenshot_and_pin(self) -> None:
        self._dispatch_legacy_action("capture.screenshot_and_pin")

    def do_screenshot_interactive(self) -> None:
        self._dispatch_legacy_action("capture.interactive_screenshot")

    def do_pure_ocr(self) -> None:
        self._dispatch_legacy_action("capture.pure_ocr")

    def do_pin_clipboard(self) -> None:
        self._dispatch_legacy_action("capture.pin_clipboard")

    def show_clipboard_history(self) -> None:
        self._dispatch_legacy_action("clipboard.show_history")

    def show_settings(self) -> None:
        self._dispatch_legacy_action("settings.show")

    def show_help(self) -> None:
        self._dispatch_legacy_action("help.show")

    def show_subconverter(self) -> None:
        self._dispatch_legacy_action("subconverter.show")

    def translator_copy_last(self) -> None:
        self._dispatch_legacy_action("translator.copy_last")

    def translator_retry_last(self) -> None:
        if not self.last_input_text:
            raise RuntimeError("no previous translator input")
        self.translate_text(self.last_input_text)

    def translator_toggle_pause(self) -> None:
        if not self.config.translator.enabled:
            self.translator_running = False
            self.translator_paused = True
            self.translator_status_key = "disabled"
            self.translator_status_text = "未启用"
            return
        self.translator_running = True
        self.translator_paused = not self.translator_paused
        self.translator_status_key = "paused" if self.translator_paused else "ready"
        self.translator_status_text = "已暂停" if self.translator_paused else "已恢复"

    def _unsupported(self, action: str) -> NoReturn:
        self.events.add(
            "action.unsupported",
            f"Action requires the legacy Tk runtime: {action}",
            data={"action": action},
        )
        raise RuntimeError(f"action requires the legacy Tk runtime: {action}")

    def _dispatch_legacy_action(self, action: str) -> None:
        if action not in self._LEGACY_ACTIONS:
            self._unsupported(action)
        self._ensure_legacy_runtime()
        self._post_legacy_action(action)
        self.events.add("legacy.action", f"Legacy runtime action dispatched: {action}", data={"action": action})

    def _ensure_legacy_runtime(self) -> None:
        if self._legacy_health_ok():
            return
        if self.legacy_process is not None and self.legacy_process.poll() is None:
            self._wait_for_legacy_runtime()
            return

        root_dir = Path(__file__).resolve().parents[1]
        script = root_dir / "scripts" / "run-legacy-runtime.sh"
        log_path = Path("/tmp/deskvane-legacy-runtime.log")
        log = log_path.open("ab")
        self.legacy_process = subprocess.Popen(
            [str(script)],
            cwd=str(root_dir),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self._wait_for_legacy_runtime()

    def _wait_for_legacy_runtime(self) -> None:
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self._legacy_health_ok():
                return
            time.sleep(0.15)
        raise RuntimeError("legacy runtime did not become ready")

    @staticmethod
    def _legacy_health_ok() -> bool:
        try:
            with urlopen("http://127.0.0.1:37656/health", timeout=0.5) as response:
                return response.status == 200
        except Exception:
            return False

    @staticmethod
    def _post_legacy_action(action: str) -> None:
        request = Request(
            f"http://127.0.0.1:37656/actions/{action}",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=3) as response:
                response.read()
        except URLError as exc:
            raise RuntimeError(f"legacy runtime action failed: {action}") from exc


def serve_runtime_sidecar(host: str = "127.0.0.1", port: int = 37655) -> int:
    events = RuntimeEventStore()
    app = HeadlessRuntimeApp(events=events)
    server = RuntimeHttpServer(RuntimeApi(app, events=events), host=host, port=port)
    stopped = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stopped.set()

    previous_sigterm = signal.signal(signal.SIGTERM, _stop)
    previous_sigint = signal.signal(signal.SIGINT, _stop)
    try:
        server.start()
        if not server.is_running:
            return 1
        events.add("runtime.started", "Headless runtime API started", data={"url": server.base_url})
        while not stopped.is_set() and not app._quit_requested:
            stopped.wait(0.25)
    finally:
        server.stop()
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv
    return serve_runtime_sidecar()
