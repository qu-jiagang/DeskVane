from __future__ import annotations

import json
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import DeskVaneApp

from .config import CONFIG_DIR

class HistoryOverlay:
    def __init__(self, root: tk.Tk, history: list[str], on_select: callable):
        self.top = tk.Toplevel(root)
        try:
            self.top.attributes("-type", "splash")
        except Exception:
            self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="#2d2d2d", highlightbackground="#6366f1", highlightthickness=2)
        
        w, h = 500, 360
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        
        # Center the overlay around the current mouse pointer to fix dual-monitor splits
        px = root.winfo_pointerx()
        py = root.winfo_pointery()
        x = px - (w // 2)
        y = py - (h // 2)
        
        # Bounds checking to ensure it doesn't spawn off-screen
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        
        self.top.geometry(f"{w}x{h}+{x}+{y}")
        
        # Title bar
        lbl = tk.Label(
            self.top, 
            text="📋 剪贴板历史记录", 
            bg="#2d2d2d", 
            fg="#6366f1", 
            font=("sans-serif", 10, "bold"), 
            anchor="w"
        )
        lbl.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Instruction
        instr = tk.Label(
            self.top,
            text="使用 ↑ ↓ 浏览，回车选择 / 快捷键 1-9 秒选 / Esc 退出",
            bg="#2d2d2d",
            fg="#888888",
            font=("sans-serif", 8),
            anchor="w"
        )
        instr.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.listbox = tk.Listbox(
            self.top, 
            bg="#2d2d2d", 
            fg="white", 
            selectbackground="#6366f1", 
            selectforeground="white",
            font=("sans-serif", 11), 
            borderwidth=0, 
            highlightthickness=0, 
            activestyle="none"
        )
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        for i, text in enumerate(history):
            disp = text.replace('\n', ' ↵ ')
            if len(disp) > 55:
                disp = disp[:52] + "..."
            prefix = f"{i+1}." if i < 9 else "  "
            self.listbox.insert(tk.END, f"{prefix} {disp}")
            
        self.listbox.bind("<Escape>", lambda e: self.close())
        self.top.bind("<Escape>", lambda e: self.close())
        
        # Right click to close
        self.listbox.bind("<Button-3>", lambda e: self.close())
        self.top.bind("<Button-3>", lambda e: self.close())
        
        self.listbox.bind("<Return>", lambda e: self._do_select(on_select))
        self.listbox.bind("<Double-Button-1>", lambda e: self._do_select(on_select))
        
        # When user clicks away, auto close
        self.top.bind("<FocusOut>", lambda e: self.close())
        
        for i in range(1, 10):
            self.listbox.bind(str(i), lambda e, idx=i-1: self._do_quick_select(idx, on_select))
            
        if history:
            self.listbox.selection_set(0)
            
        self.top.focus_force()
        self.listbox.focus_set()
        
    def _do_select(self, on_select: callable):
        sel = self.listbox.curselection()
        if sel:
            on_select(sel[0])
            self.close()
            
    def _do_quick_select(self, idx: int, on_select: callable):
        if idx < self.listbox.size():
            on_select(idx)
            self.close()
            
    def close(self):
        self.top.destroy()


class ClipboardHistoryManager:
    _HISTORY_PATH = CONFIG_DIR / "clipboard_history.json"
    _MAX_ENTRIES = 50

    def __init__(self, app: DeskVaneApp):
        self.app = app
        self.history: list[str] = self._load_from_disk()
        self._last_clip = ""
        self._overlay: HistoryOverlay | None = None
        self._save_pending = False

        if self.app.config.general.clipboard_history_enabled:
            # Short delay before first poll to avoid locking during app init
            self.app.root.after(2000, self._poll_clipboard)
            
    def _poll_clipboard(self):
        try:
            content = self.app.root.clipboard_get()
            if content and isinstance(content, str) and content != self._last_clip:
                self._last_clip = content
                if content in self.history:
                    self.history.remove(content)
                self.history.insert(0, content)
                self.history = self.history[:self._MAX_ENTRIES]
                self._schedule_save()
        except tk.TclError:
            pass
            
        self.app.root.after(1000, self._poll_clipboard)

    def _schedule_save(self) -> None:
        """Debounce saves — write at most once every 5 seconds."""
        if not self._save_pending:
            self._save_pending = True
            self.app.root.after(5000, self._flush_to_disk)

    def _flush_to_disk(self) -> None:
        self._save_pending = False
        try:
            self._HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._HISTORY_PATH.write_text(
                json.dumps(self.history[:self._MAX_ENTRIES], ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @classmethod
    def _load_from_disk(cls) -> list[str]:
        try:
            if cls._HISTORY_PATH.exists():
                data = json.loads(cls._HISTORY_PATH.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [str(x) for x in data[:cls._MAX_ENTRIES]]
        except Exception:
            pass
        return []
        
    def show_overlay(self):
        # If already showing, close it (toggle behavior)
        if hasattr(self, "_overlay") and self._overlay and self._overlay.top.winfo_exists():
            self._overlay.close()
            return
            
        if not self.history:
            if self.app.config.general.notifications_enabled:
                self.app.notifier.show("剪贴板历史", "暂无历史记录")
            return
            
        self._overlay = HistoryOverlay(self.app.root, self.history, self._on_select)
        
    def _on_select(self, index: int):
        if 0 <= index < len(self.history):
            content = self.history[index]
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(content)
            self._last_clip = content
            
            # Move to top
            self.history.pop(index)
            self.history.insert(0, content)
            
            if self.app.config.general.notifications_enabled:
                self.app.notifier.show("已提取", "内容已复制到剪贴板最上层，可按 Ctrl+V 粘贴")
