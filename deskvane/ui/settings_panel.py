"""GUI settings panel for DeskVane."""
from __future__ import annotations

import dataclasses
import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox as messagebox
from typing import TYPE_CHECKING, Any

from ..config import AppConfig, _save_config
from .ui_theme import (
    ACCENT,
    ACCENT_FG,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    MUTED,
    SIDEBAR,
    SUBTEXT,
    TEXT,
    button as themed_button,
    card as themed_card,
    make_font,
)

if TYPE_CHECKING:
    from ..app import DeskVaneApp


def _deep_copy_config(cfg: AppConfig) -> AppConfig:
    """Create a deep copy of the config so the panel can work on a draft."""
    kwargs = {}
    for f in dataclasses.fields(cfg):
        sub = getattr(cfg, f.name)
        if dataclasses.is_dataclass(sub):
            kwargs[f.name] = type(sub)(**dataclasses.asdict(sub))
        else:
            kwargs[f.name] = sub
    return AppConfig(**kwargs)

# ── Singleton guard ───────────────────────────────────────────────────
_active_window: _SettingsWindow | None = None


# ── Human‑readable field labels ──────────────────────────────────────
_FIELD_LABELS: dict[str, str] = {
    # General
    "general.notifications_enabled": "启用通知",
    "notifications_enabled":     "启用通知",
    "clipboard_history_enabled": "启用剪贴板历史",
    "hotkey_clipboard_history":  "剪贴板历史快捷键",
    "tray_display":              "托盘图标显示模式",
    # Screenshot
    "save_dir":             "截图保存目录",
    "hotkey":               "截图快捷键",
    "hotkey_pin":           "截图钉图快捷键",
    "hotkey_pure_ocr":      "纯 OCR 快捷键",
    "hotkey_interactive":   "交互式截图快捷键",
    "hotkey_pin_clipboard": "钉贴剪贴板快捷键",
    "copy_to_clipboard":    "截图自动复制到剪贴板",
    "save_to_disk":         "截图保存到磁盘",
    "screenshot.notifications_enabled": "截图通知",
    # Translator
    "enabled":              "启用翻译功能",
    "ollama_host":          "Ollama 地址",
    "model":                "模型 (空=自动)",
    "source_language":      "源语言",
    "target_language":      "目标语言",
    "poll_interval_ms":     "轮询间隔 (ms)",
    "selection_enabled":    "启用选区监听",
    "clipboard_enabled":    "启用剪贴板监听",
    "popup_enabled":        "启用弹窗显示",
    "debounce_ms":          "防抖间隔 (ms)",
    "max_chars":            "最大字符数",
    "min_chars":            "最小字符数",
    "keep_alive":           "模型 Keep‑Alive",
    "request_timeout_s":    "请求超时 (秒)",
    "auto_copy":            "自动复制译文",
    "disable_thinking":     "禁用思考过程",
    "max_output_tokens":    "最大输出 Token",
    "popup_width_px":       "弹窗宽度 (px)",
    "prompt_extra":         "追加 Prompt",
    "hotkey_toggle_pause":  "暂停/恢复监控快捷键",
    # Proxy
    "address":              "代理地址",
    # Subconverter
    "port":                 "订阅转换端口",
    "enable_server":        "启用订阅转换服务",
}

_FIELD_HINTS: dict[str, str] = {
    "translator.enabled": "关闭时不会启动 Ollama 翻译监听，也不会触发 OCR 请求。",
    "proxy.address": "示例: http://127.0.0.1:7890",
    "translator.model": "留空时按当前 Ollama 环境自动选择。",
    "translator.prompt_extra": "仅在需要扩展翻译提示词时填写。",
}

# Fields that should render as dropdown (OptionMenu)
# Maps "section.field" → list of (internal_value, display_label)
_FIELD_OPTIONS: dict[str, list[tuple[str, str]]] = {
    "general.tray_display": [
        ("default",   "默认图标"),
        ("cpu_usage", "CPU 使用率"),
        ("cpu_temp",  "CPU 温度"),
        ("gpu_usage", "GPU 使用率"),
        ("gpu_temp",  "GPU 温度"),
        ("gpu_mem",   "GPU 显存占用"),
    ],
}

_SOURCE_BUILD_STAMP = "源码戳: menu-fix-20260507-1538"


def _settings_layout(app: DeskVaneApp):
    context = getattr(app, "context", None)
    registry = getattr(context, "settings_registry", None) if context is not None else None
    if registry is None:
        raise RuntimeError("DeskVane settings panel requires settings registry context")

    tabs: list[tuple[str, str, str]] = []
    summaries: dict[str, str] = {}
    groups: dict[str, list[tuple[str, str, list[str]]]] = {}
    for section in registry.ordered_sections():
        tabs.append((section.label, "", section.config_attr))
        if section.summary:
            summaries[section.config_attr] = section.summary
        groups[section.config_attr] = [
            (group.title, group.description, list(group.fields))
            for group in section.groups
        ]
    return tabs, summaries, groups


def open_settings(app: DeskVaneApp) -> None:
    """Open the settings panel (singleton – refocuses if already open)."""
    global _active_window
    if _active_window is not None:
        try:
            _active_window.lift()
            _active_window.focus_force()
            return
        except tk.TclError:
            _active_window = None

    _active_window = _SettingsWindow(app)


class _SettingsWindow:
    """Main settings Toplevel."""

    def __init__(self, app: DeskVaneApp) -> None:
        self.app = app
        self._tabs, self._tab_summaries, self._tab_groups = _settings_layout(app)
        # Work on a deep copy so we can cancel without side‑effects
        self.draft = _deep_copy_config(app.config)
        # Persistent var storage across all tabs — keyed by "section.field"
        self._field_vars: dict[str, tk.Variable] = {}
        self._platform_info = app.platform_services.info

        self.win = tk.Toplevel(app.root)
        self.win.title("DeskVane 设置")
        self.win.configure(bg=BG)
        self.win.minsize(820, 560)
        self.win.geometry("980x680")
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Fonts
        self._font_tab = make_font(12, weight="bold")
        self._font_label = make_font(11)
        self._font_entry = make_font(11, mono=True)
        self._font_heading = make_font(15, weight="bold")
        self._font_summary = make_font(10)
        self._font_btn = make_font(11, weight="bold")

        # ── Build layout (order matters for pack!) ──
        self._build_sidebar()
        self._build_footer()    # Footer BEFORE body so it gets space
        self._build_body()

        # Pre-create all tk vars for every tab so switching tabs is lossless
        self._init_all_vars()

        # Select first tab
        self._selected_tab = 0
        self._select_tab(0)

    # ── Pre-create all tk Variables ──────────────────────────────────

    def _init_all_vars(self) -> None:
        """Create tk Variables for every field across all tabs upfront."""
        for _, _, attr_name in self._tabs:
            sub_config = getattr(self.draft, attr_name)
            for field in dataclasses.fields(sub_config):
                full_key = f"{attr_name}.{field.name}"
                value = getattr(sub_config, field.name)
                if isinstance(value, bool):
                    self._field_vars[full_key] = tk.BooleanVar(value=value)
                elif isinstance(value, int):
                    self._field_vars[full_key] = tk.IntVar(value=value)
                else:
                    self._field_vars[full_key] = tk.StringVar(value=str(value))

    # ── Sidebar (left tabs) ──────────────────────────────────────────

    def _build_sidebar(self) -> None:
        self.sidebar = tk.Frame(self.win, bg=SIDEBAR, width=196)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        title = tk.Frame(self.sidebar, bg=SIDEBAR)
        title.pack(fill="x", padx=18, pady=(18, 14))
        tk.Label(
            title,
            text="设置",
            bg=SIDEBAR,
            fg=TEXT,
            font=make_font(14, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title,
            text="按功能分组整理，减少来回找配置的成本。",
            bg=SIDEBAR,
            fg=SUBTEXT,
            font=self._font_summary,
            anchor="w",
            justify="left",
            wraplength=150,
        ).pack(fill="x", pady=(6, 0))

        self._tab_buttons: list[tk.Label] = []
        for idx, (label, icon, _) in enumerate(self._tabs):
            prefix = f"{icon}  " if icon else ""
            btn = tk.Label(
                self.sidebar,
                text=f"  {prefix}{label}",
                bg=SIDEBAR,
                fg=SUBTEXT,
                font=self._font_tab,
                anchor="w",
                padx=16,
                pady=10,
                cursor="hand2",
            )
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda e, i=idx: self._select_tab(i))
            btn.bind("<Enter>", lambda e, b=btn: self._tab_hover(b, True))
            btn.bind("<Leave>", lambda e, b=btn: self._tab_hover(b, False))
            self._tab_buttons.append(btn)

    def _tab_hover(self, btn: tk.Label, enter: bool) -> None:
        idx = self._tab_buttons.index(btn)
        if idx == self._selected_tab:
            return
        btn.configure(bg=CARD_ALT if enter else SIDEBAR)

    def _select_tab(self, idx: int) -> None:
        self._selected_tab = idx
        for i, btn in enumerate(self._tab_buttons):
            if i == idx:
                btn.configure(bg=CARD_ALT, fg=ACCENT)
            else:
                btn.configure(bg=SIDEBAR, fg=SUBTEXT)
        self._render_tab(idx)

    # ── Footer ───────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        footer = tk.Frame(self.win, bg=SIDEBAR, height=64, highlightbackground=BORDER, highlightthickness=1)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        # Cancel button
        cancel_btn = themed_button(
            footer, text="取消", command=self._on_cancel,
            variant="secondary", font=self._font_btn,
        )
        cancel_btn.pack(side="right", padx=(0, 16), pady=12)

        # Save button
        save_btn = themed_button(
            footer, text="保存并应用", command=self._on_save,
            variant="primary", font=self._font_btn,
        )
        save_btn.pack(side="right", padx=(0, 8), pady=12)

        yaml_btn = themed_button(
            footer, text="打开配置", command=self._open_yaml,
            variant="ghost", compact=True, font=self._font_label,
        )
        yaml_btn.pack(side="left", padx=16, pady=12)
        tk.Label(
            footer,
            text=_SOURCE_BUILD_STAMP,
            bg=SIDEBAR,
            fg=MUTED,
            font=self._font_summary,
            anchor="w",
        ).pack(side="left", padx=(0, 16), pady=12)

    # ── Body (scrollable content) ────────────────────────────────────

    def _build_body(self) -> None:
        self.body_outer = tk.Frame(self.win, bg=BG)
        self.body_outer.pack(side="left", fill="both", expand=True)

        self._body_canvas = tk.Canvas(
            self.body_outer, bg=BG, highlightthickness=0, bd=0,
        )
        self._body_scrollbar = tk.Scrollbar(
            self.body_outer, orient="vertical", command=self._body_canvas.yview,
            bg=CARD_ALT, troughcolor=BG, activebackground=BORDER,
        )
        self._body_canvas.configure(yscrollcommand=self._body_scrollbar.set)

        self._body_scrollbar.pack(side="right", fill="y")
        self._body_canvas.pack(side="left", fill="both", expand=True)

        self._body_inner = tk.Frame(self._body_canvas, bg=BG)
        self._body_canvas_id = self._body_canvas.create_window(
            (0, 0), window=self._body_inner, anchor="nw",
        )

        self._body_inner.bind("<Configure>", self._on_body_configure)
        self._body_canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse‑wheel scrolling (Linux)
        def _on_mousewheel(event):
            try:
                self._body_canvas.yview_scroll(-3 if event.num == 4 else 3, "units")
            except tk.TclError:
                pass
        self.win.bind("<Button-4>", _on_mousewheel, add="+")
        self.win.bind("<Button-5>", _on_mousewheel, add="+")

    def _on_body_configure(self, _e: tk.Event) -> None:
        self._body_canvas.configure(scrollregion=self._body_canvas.bbox("all"))

    def _on_canvas_configure(self, e: tk.Event) -> None:
        self._body_canvas.itemconfigure(self._body_canvas_id, width=e.width)

    # ── Tab rendering ────────────────────────────────────────────────

    def _render_tab(self, idx: int) -> None:
        # Destroy old widgets
        for w in self._body_inner.winfo_children():
            w.destroy()

        label, icon, attr_name = self._tabs[idx]
        sub_config = getattr(self.draft, attr_name)

        # Header
        hdr = tk.Label(
            self._body_inner,
            text=label,
            bg=BG, fg=TEXT, font=self._font_heading,
            anchor="w",
        )
        hdr.pack(fill="x", padx=28, pady=(22, 4))

        summary = self._tab_summaries.get(attr_name)
        if summary:
            tk.Label(
                self._body_inner,
                text=summary,
                bg=BG,
                fg=SUBTEXT,
                font=self._font_summary,
                anchor="w",
                justify="left",
                wraplength=700,
            ).pack(fill="x", padx=28, pady=(0, 16))

        rendered_fields: set[str] = set()
        for title, desc, field_names in self._tab_groups.get(attr_name, []):
            available_names = [name for name in field_names if hasattr(sub_config, name)]
            if not available_names:
                continue
            rendered_fields.update(available_names)
            self._render_group_card(
                parent=self._body_inner,
                section_attr=attr_name,
                sub_config=sub_config,
                title=title,
                description=desc,
                field_names=available_names,
            )

        leftovers = [
            field.name for field in dataclasses.fields(sub_config)
            if field.name not in rendered_fields
        ]
        if leftovers:
            self._render_group_card(
                parent=self._body_inner,
                section_attr=attr_name,
                sub_config=sub_config,
                title="其他",
                description="其他较少调整的项目。",
                field_names=leftovers,
            )

        # Bottom spacer
        tk.Frame(self._body_inner, bg=BG, height=24).pack()

        # Force layout update so canvas sees the new content
        self._body_inner.update_idletasks()
        self._body_canvas.configure(scrollregion=self._body_canvas.bbox("all"))
        # Ensure inner frame fills canvas width
        try:
            canvas_w = self._body_canvas.winfo_width()
            if canvas_w > 1:
                self._body_canvas.itemconfigure(self._body_canvas_id, width=canvas_w)
        except tk.TclError:
            pass
        self._body_canvas.yview_moveto(0)

    def _render_group_card(
        self,
        parent: tk.Frame,
        section_attr: str,
        sub_config: object,
        title: str,
        description: str,
        field_names: list[str],
    ) -> None:
        group = themed_card(parent, fill="x", padx=28, pady=(0, 14))
        group_body = tk.Frame(group, bg=CARD)
        group_body.pack(fill="x", padx=18, pady=16)

        tk.Label(
            group_body,
            text=title,
            bg=CARD,
            fg=TEXT,
            font=make_font(12, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            group_body,
            text=description,
            bg=CARD,
            fg=SUBTEXT,
            font=self._font_summary,
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(4, 10))

        for field_name in field_names:
            self._render_field(
                parent=group_body,
                section_attr=section_attr,
                field_name=field_name,
                value=getattr(sub_config, field_name),
            )

    @staticmethod
    def _field_label(section_attr: str, field_name: str) -> str:
        return _FIELD_LABELS.get(f"{section_attr}.{field_name}", _FIELD_LABELS.get(field_name, field_name))

    def _render_field(
        self,
        parent: tk.Frame,
        section_attr: str,
        field_name: str,
        value: Any,
    ) -> None:
        label_text = self._field_label(section_attr, field_name)
        full_key = f"{section_attr}.{field_name}"
        var = self._field_vars.get(full_key)
        if var is None:
            return  # Safety — should not happen

        row_bg = str(parent.cget("bg"))
        row = tk.Frame(parent, bg=row_bg)
        row.pack(fill="x", pady=6)
        row.columnconfigure(1, weight=1)

        lbl = tk.Label(
            row, text=label_text, bg=row_bg, fg=TEXT,
            font=self._font_label, anchor="nw", width=18,
        )
        lbl.grid(row=0, column=0, sticky="nw", padx=(0, 18), pady=(4, 0))

        control_host = tk.Frame(row, bg=row_bg)
        control_host.grid(row=0, column=1, sticky="ew")
        hint = _FIELD_HINTS.get(full_key, "")

        if isinstance(value, bool):
            def _checkbox_label() -> str:
                return "启用" if bool(var.get()) else "关闭"

            cb = tk.Checkbutton(
                control_host, variable=var,
                bg=row_bg, fg=TEXT, selectcolor=CARD_ALT,
                activebackground=row_bg, activeforeground=TEXT,
                bd=0, highlightthickness=0,
                onvalue=True, offvalue=False,
                font=self._font_label,
                text=_checkbox_label(),
                command=lambda cb_ref=None: cb.configure(text=_checkbox_label()),
                cursor="hand2",
            )
            cb.pack(side="left")
        elif isinstance(value, int):
            sp = tk.Spinbox(
                control_host, from_=0, to=99999, textvariable=var,
                bg=CARD_ALT, fg=TEXT, insertbackground=TEXT,
                font=self._font_entry, bd=0,
                highlightthickness=1, highlightbackground=BORDER,
                highlightcolor=ACCENT, width=12,
                buttonbackground=BORDER,
            )
            sp.pack(side="left", fill="x")
        else:
            # Check if this field has predefined options → dropdown
            options = self._field_options(full_key)
            if options:
                # Build value↔label mapping
                val_to_label = {v: l for v, l in options}
                label_to_val = {l: v for v, l in options}
                display_labels = [l for _, l in options]

                # Display var shows human label, synced with the real var
                display_var = tk.StringVar(value=val_to_label.get(str(var.get()), str(var.get())))

                def _sync_to_real(display_v=display_var, real_v=var, mapping=label_to_val):
                    real_v.set(mapping.get(display_v.get(), display_v.get()))
                display_var.trace_add("write", lambda *_a, f=_sync_to_real: f())

                om = tk.OptionMenu(control_host, display_var, *display_labels)
                om.configure(
                    bg=CARD_ALT, fg=TEXT, activebackground=BORDER,
                    activeforeground=TEXT, font=self._font_entry,
                    bd=0, highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT, cursor="hand2",
                )
                om["menu"].configure(
                    bg=CARD_ALT, fg=TEXT, activebackground=ACCENT,
                    activeforeground=ACCENT_FG, font=self._font_entry,
                )
                om.pack(side="left", fill="x")
            else:
                entry = tk.Entry(
                    control_host, textvariable=var,
                    bg=CARD_ALT, fg=TEXT, insertbackground=TEXT,
                    font=self._font_entry, bd=0,
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=ACCENT,
                )
                entry.pack(side="left", fill="x", expand=True)

        if hint:
            tk.Label(
                row,
                text=hint,
                bg=row_bg,
                fg=MUTED,
                font=self._font_summary,
                anchor="w",
                justify="left",
                wraplength=520,
                ).grid(row=1, column=1, sticky="w", pady=(6, 0))

    def _field_options(self, full_key: str) -> list[tuple[str, str]] | None:
        return _FIELD_OPTIONS.get(full_key)

    # ── Actions ──────────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Apply ALL field variable values back to draft config, save and reload."""
        pending_updates: list[tuple[object, str, object]] = []
        invalid_fields: list[str] = []
        for full_key, var in self._field_vars.items():
            section_attr, field_name = full_key.split(".", 1)
            sub = getattr(self.draft, section_attr)
            old_val = getattr(sub, field_name)
            label_text = _FIELD_LABELS.get(field_name, field_name)
            try:
                if isinstance(old_val, bool):
                    new_val = bool(var.get())
                elif isinstance(old_val, int):
                    new_val = int(var.get())
                else:
                    new_val = str(var.get())
                pending_updates.append((sub, field_name, new_val))
            except (ValueError, tk.TclError):
                invalid_fields.append(label_text)

        if invalid_fields:
            messagebox.showerror(
                "保存失败",
                "以下数值项不是合法输入，请修正后再保存：\n" + "\n".join(f"- {name}" for name in invalid_fields),
                parent=self.win,
            )
            return

        for target, field_name, value in pending_updates:
            setattr(target, field_name, value)

        # Persist all sections from draft → live config
        for _, _, attr_name in self._tabs:
            setattr(self.app.config, attr_name, getattr(self.draft, attr_name))

        try:
            _save_config(self.app.config)
            self.app.reload_config()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.win)
            return
        self._close()

    def _on_cancel(self) -> None:
        self._close()

    def _open_yaml(self) -> None:
        self.app.open_config()

    def _close(self) -> None:
        global _active_window
        _active_window = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # Expose lift/focus_force for singleton guard
    def lift(self) -> None:
        self.win.lift()

    def focus_force(self) -> None:
        self.win.focus_force()
