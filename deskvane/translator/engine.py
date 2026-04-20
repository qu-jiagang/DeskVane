from __future__ import annotations

import time
import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .clipboard import CLIPBOARD, PRIMARY, TkClipboardBackend, choose_clipboard_backend
from ..features.translator.state import TranslatorState
from .ollama import OllamaClient
from .popup import TranslationPopup
from .text_utils import ellipsize, is_translatable, normalize_text
from .worker import TranslationRequest, TranslationResult, TranslationWorker

if TYPE_CHECKING:
    from ..app import DeskVaneApp


class OcrResultDialog:
    def __init__(self, root: tk.Tk, text: str, pointer_x: int, pointer_y: int, on_copy: callable = None):
        self.top = tk.Toplevel(root)
        self.top.title("OCR 提取结果")
        self.top.attributes("-topmost", True)
        self.top.configure(bg="#1e1e1e", pady=10, padx=10)
        
        # Keep window near pointer
        w, h = 400, 250
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        x = min(max(0, pointer_x + 20), sw - w - 20)
        y = min(max(0, pointer_y + 20), sh - h - 20)
        self.top.geometry(f"{w}x{h}+{x}+{y}")
        
        self.text_widget = tk.Text(
            self.top, 
            wrap=tk.WORD, 
            bg="#252526", 
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 11),
            bd=0,
            highlightthickness=1,
            highlightbackground="#3c3c3c"
        )
        self.text_widget.insert("1.0", text)
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        
        btn_frame = tk.Frame(self.top, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        def copy_and_close():
            text_to_copy = self.text_widget.get("1.0", tk.END).strip()
            if on_copy:
                on_copy(text_to_copy)
            else:
                root.clipboard_clear()
                root.clipboard_append(text_to_copy)
            self.top.destroy()
            
        btn = tk.Button(
            btn_frame, 
            text="复制并关闭 ↵", 
            command=copy_and_close,
            bg="#0e639c",
            fg="white",
            activebackground="#1177bb",
            activeforeground="white",
            bd=0,
            cursor="hand2",
            padx=15,
            pady=5
        )
        btn.pack(side=tk.RIGHT)
        
        # Bindings
        self.top.bind("<Escape>", lambda e: self.top.destroy())
        self.text_widget.bind("<Return>", lambda e: [copy_and_close(), "break"][1])
        self.text_widget.focus_set()

@dataclass(slots=True)
class SuppressedValue:
    text: str
    expires_at: float

class TranslatorEngine:
    """Built-in translator — clipboard monitoring + Ollama translation."""

    def __init__(self, app: DeskVaneApp) -> None:
        self.app = app
        self.root = app.root
        cfg = app.config

        self.clipboard_backend = choose_clipboard_backend(self.root)
        self.tk_clipboard = TkClipboardBackend(self.root)
        self.popup = TranslationPopup(self.root, on_copy=self._write_clipboard)

        self.paused = True
        self.running = False
        self.status_key = "ready"
        self.status_text = "就绪"
        self.current_model_label = cfg.translator.model or "自动"
        self.backend_label = self.clipboard_backend.name
        self.last_translation = ""
        self.last_input_text = ""
        self.last_input_source = ""
        self.last_translation_preview = "-"
        self.latest_request_id = 0
        self.last_submitted_text = ""
        self.last_submitted_at = 0.0
        self.last_seen_by_source = {PRIMARY: "", CLIPBOARD: ""}
        self.pending_by_source: dict[str, tuple[str, float]] = {}
        self.suppressed_values: dict[str, SuppressedValue] = {}
        self.last_error_signature = ""
        self.last_error_at = 0.0
        self._platform_clipboard = self.app.platform_services.clipboard

        self.worker = TranslationWorker(
            client=self._build_client(),
            on_result=lambda result: self.app.dispatcher.call_soon(
                self._handle_translation_result, result
            ),
            on_error=lambda request, exc: self.app.dispatcher.call_soon(
                self._handle_translation_error, request, exc
            ),
        )

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.app.config.translator, "enabled", False))

    def _make_worker(self) -> TranslationWorker:
        return TranslationWorker(
            client=self._build_client(),
            on_result=lambda result: self.app.dispatcher.call_soon(
                self._handle_translation_result, result
            ),
            on_error=lambda request, exc: self.app.dispatcher.call_soon(
                self._handle_translation_error, request, exc
            ),
        )

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self) -> None:
        if not self.enabled:
            self.running = False
            self.paused = True
            self.popup.hide()
            self._set_status("disabled", "未启用")
            return
        if self.worker.is_alive():
            return
        if getattr(self.worker, "_stopped", False):
            self.worker = self._make_worker()
        self.running = True
        self.worker.start()
        self._set_status("ready", "就绪")
        self._schedule_poll()

    def stop(self) -> None:
        self.running = False
        if self.worker.is_alive():
            self.worker.stop()
        self.popup.hide()

    # ---------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------

    def _build_client(self) -> OllamaClient:
        cfg = self.app.config
        return OllamaClient(
            host=cfg.translator.ollama_host,
            timeout_s=cfg.translator.request_timeout_s,
            prompt_extra=cfg.translator.prompt_extra,
            disable_thinking=cfg.translator.disable_thinking,
            max_output_tokens=cfg.translator.max_output_tokens,
        )

    def _schedule_poll(self) -> None:
        self.root.after(self.app.config.translator.poll_interval_ms, self._poll_clipboards)

    def _poll_clipboards(self) -> None:
        if not self.running:
            return
        now = time.monotonic()
        self._flush_pending(now)
        if not self.paused:
            cfg = self.app.config
            if cfg.translator.selection_enabled:
                self._poll_source(PRIMARY, now)
            if cfg.translator.clipboard_enabled:
                self._poll_source(CLIPBOARD, now)
        self._schedule_poll()

    def _poll_source(self, source: str, now: float) -> None:
        try:
            raw_text = self._platform_clipboard.read_text(source)
            if raw_text is None:
                raw_text = self.clipboard_backend.read_text(source)
        except Exception:
            return
        if raw_text is None:
            return
        text = normalize_text(raw_text)
        if not text:
            return
        if self._is_suppressed(source, text, now):
            return
        if text == self.last_seen_by_source[source]:
            return
        self.last_seen_by_source[source] = text
        self.pending_by_source[source] = (text, now + (self.app.config.translator.debounce_ms / 1000))

    def _flush_pending(self, now: float) -> None:
        keys_to_del = []
        for source, (text, due_at) in self.pending_by_source.items():
            if now >= due_at:
                keys_to_del.append(source)
                self._maybe_translate(source, text, now)
        for key in keys_to_del:
            if key in self.pending_by_source:
                del self.pending_by_source[key]

    def _maybe_translate(self, source: str, text: str, now: float) -> None:
        cfg = self.app.config
        if not is_translatable(text, cfg.translator.min_chars):
            return
        if len(text) > cfg.translator.max_chars:
            self._notify_once(
                "文本过长",
                f"已跳过 {len(text)} 个字符，超过上限 {cfg.translator.max_chars}。",
            )
            return
        if text == self.last_submitted_text and (now - self.last_submitted_at) < 5:
            return
        self.last_submitted_text = text
        self.last_submitted_at = now
        self.last_input_text = text
        self.last_input_source = source
        self.latest_request_id += 1
        pointer_x, pointer_y = self._pointer_position()
        self._set_status("busy", f"翻译中 ({source})")
        self.worker.submit(
            TranslationRequest(
                request_id=self.latest_request_id,
                source=source,
                text=text,
                pointer_x=pointer_x,
                pointer_y=pointer_y,
                preferred_model=cfg.translator.model,
                source_language=cfg.translator.source_language,
                target_language=cfg.translator.target_language,
                keep_alive=cfg.translator.keep_alive,
            )
        )

    def submit_pure_ocr(self, img_b64: str) -> None:
        """Submit an image purely for OCR without translation."""
        if not self.enabled:
            self._notify_once("翻译功能未启用", "如需 OCR/翻译能力，请先在设置中启用翻译功能并配置 Ollama。")
            self._set_status("disabled", "未启用")
            return
        cfg = self.app.config
        now = time.monotonic()
        self.last_submitted_text = img_b64
        self.last_submitted_at = now
        self.last_input_text = "[图片OCR]"
        self.last_input_source = "截屏"
        self.latest_request_id += 1
        pointer_x, pointer_y = self._pointer_position()
        self._set_status("busy", "OCR提取中")
        self.worker.submit(
            TranslationRequest(
                request_id=self.latest_request_id,
                source="截屏",
                text=img_b64,
                pointer_x=pointer_x,
                pointer_y=pointer_y,
                preferred_model=cfg.translator.model,
                source_language="auto",
                target_language="OCR",
                keep_alive=cfg.translator.keep_alive,
                is_pure_ocr=True,
            )
        )

    def _handle_translation_result(self, result: TranslationResult) -> None:
        if result.request.request_id != self.latest_request_id:
            return
        translated = result.response.text
        
        if getattr(result.request, "is_pure_ocr", False):
            self._set_status("ready", f"OCR完成 {result.response.elapsed_ms} ms")
            px = result.request.pointer_x if result.request.pointer_x is not None else self.root.winfo_pointerx()
            py = result.request.pointer_y if result.request.pointer_y is not None else self.root.winfo_pointery()
            
            def on_ocr_copy(text: str):
                self._write_clipboard(text)
                if self.app.config.general.notifications_enabled:
                    self.app.notifier.show("OCR提取完成", "文本已进入剪贴板")
                    
            OcrResultDialog(self.root, translated, px, py, on_copy=on_ocr_copy)
            return

        self.last_translation = translated
        self.current_model_label = result.response.model
        self.last_translation_preview = ellipsize(translated.replace("\n", " / "), 36) or "-"
        self._set_status("ready", f"已翻译 {result.response.elapsed_ms} ms")
        cfg = self.app.config
        if cfg.translator.auto_copy:
            self._write_clipboard(translated)
        if cfg.translator.popup_enabled:
            self.popup.show(
                text=translated,
                pointer_x=result.request.pointer_x,
                pointer_y=result.request.pointer_y,
                width_px=cfg.translator.popup_width_px,
            )
        elif cfg.general.notifications_enabled:
            body = ellipsize(translated, 240)
            self.app.notifier.show(
                f"{result.request.source} -> {cfg.translator.target_language}",
                f"{body}\n{result.response.model} | {result.response.elapsed_ms} ms",
            )

    def _handle_translation_error(self, request: TranslationRequest, exc: Exception) -> None:
        if request.request_id != self.latest_request_id:
            return
        if getattr(request, "is_pure_ocr", False):
            self._set_status("error", "OCR提取失败")
            self._notify_once("OCR 失败", str(exc))
            return
        self._set_status("error", "翻译失败")
        self._notify_once("翻译失败", str(exc))

    def _notify_once(self, title: str, message: str, cooldown_s: float = 8.0) -> None:
        signature = f"{title}:{message}"
        now = time.monotonic()
        if signature == self.last_error_signature and (now - self.last_error_at) < cooldown_s:
            return
        self.last_error_signature = signature
        self.last_error_at = now
        if self.app.config.general.notifications_enabled:
            self.app.notifier.show(title, ellipsize(message, 240))

    def _set_status(self, key: str, text: str) -> None:
        self.status_key = key
        self.status_text = text
        self.app.tray.refresh()

    def _pointer_position(self) -> tuple[int | None, int | None]:
        try:
            return self.root.winfo_pointerxy()
        except tk.TclError:
            return None, None

    def _is_suppressed(self, source: str, text: str, now: float) -> bool:
        suppressed = self.suppressed_values.get(source)
        if not suppressed:
            return False
        if now > suppressed.expires_at:
            self.suppressed_values.pop(source, None)
            return False
        return suppressed.text == text

    def _write_clipboard(self, text: str) -> None:
        normalized = normalize_text(text)
        self.suppressed_values[CLIPBOARD] = SuppressedValue(
            text=normalized,
            expires_at=time.monotonic() + 2.0,
        )
        if self._platform_clipboard.write_text(text):
            return
        if self.clipboard_backend.write_clipboard(text):
            return
        self.tk_clipboard.write_clipboard(text)

    # ---------------------------------------------------------------
    # Public actions (called from tray/app)
    # ---------------------------------------------------------------

    def copy_last_translation(self) -> None:
        if not self.enabled or not self.last_translation:
            return
        self._write_clipboard(self.last_translation)
        self._notify_once("已复制译文", self.last_translation, cooldown_s=0.5)

    def retry_last_input(self) -> None:
        if not self.enabled or not self.last_input_text:
            return
        self.pending_by_source[self.last_input_source or CLIPBOARD] = (
            self.last_input_text,
            time.monotonic(),
        )

    def toggle_pause(self) -> None:
        if not self.enabled:
            self._notify_once("翻译功能未启用", "如需启用，请打开设置 > 翻译，并开启翻译功能。")
            self._set_status("disabled", "未启用")
            return
        self.paused = not self.paused
        if self.paused:
            self.popup.hide()
            self._set_status("paused", "已暂停")
            return
        self._set_status("ready", "已恢复")

    def reload(self) -> None:
        """Reload translator settings from current config."""
        self.clipboard_backend = choose_clipboard_backend(self.root)
        self.backend_label = self.clipboard_backend.name
        if self.worker.is_alive():
            self.worker.replace_client(self._build_client())
        else:
            self.worker = self._make_worker()
        self.current_model_label = self.app.config.translator.model or "自动"
        if not self.enabled:
            self.stop()
            self.running = False
            self.paused = True
            self.pending_by_source.clear()
            self.popup.hide()
            self._set_status("disabled", "未启用")
            return
        if not self.running:
            self.start()

    def snapshot_state(self) -> TranslatorState:
        return TranslatorState(
            enabled=self.enabled,
            paused=self.paused,
            running=self.running,
            status_key=self.status_key,
            status_text=self.status_text,
            model_label=self.current_model_label,
            backend_label=self.backend_label,
            last_translation_available=bool(self.last_translation),
            last_translation_preview=self.last_translation_preview,
        )
