from __future__ import annotations

from pathlib import Path
import subprocess
import threading
import tkinter as tk
import urllib.parse
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Callable

import yaml

from .api import DEFAULT_DELAY_TEST_URL, MihomoProxyGroup, MihomoRuntimeState
from ..ui_theme import (
    ACCENT as _ACCENT,
    ACCENT_FG as _ACCENT_FG,
    ACCENT_HOVER as _ACCENT_HOVER,
    BG as _BG,
    BORDER as _BORDER,
    CARD as _PANEL,
    CARD_ALT as _PANEL_ALT,
    DANGER as _DANGER,
    MUTED as _MUTED,
    SUBTEXT as _SUBTEXT,
    SUCCESS as _SUCCESS,
    TEXT as _TEXT,
    WARN as _WARN,
    button as themed_button,
    card as themed_card,
    make_font,
)

if TYPE_CHECKING:
    from ..app import DeskVaneApp


_active_panel: _MihomoPanel | None = None


class _SelectableCardList:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        height: int,
        on_select: Callable[[int], None] | None = None,
        on_activate: Callable[[int], None] | None = None,
    ) -> None:
        self.on_select = on_select
        self.on_activate = on_activate
        self.selected_index: int | None = None
        self._enabled = True
        self._items: list[dict[str, str]] = []
        self._rows: list[dict[str, Any]] = []

        self.container = tk.Frame(parent, bg=_PANEL)
        shell = tk.Frame(
            self.container,
            bg=_PANEL_ALT,
            highlightbackground="#e6e9f0",
            highlightthickness=1,
            bd=0,
            padx=6,
            pady=6,
        )
        shell.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            shell,
            bg=_PANEL_ALT,
            highlightthickness=0,
            bd=0,
            height=height,
        )
        self.scrollbar = tk.Scrollbar(
            shell,
            orient="vertical",
            command=self.canvas.yview,
            bg=_PANEL_ALT,
            troughcolor=_PANEL_ALT,
            activebackground=_BORDER,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.body = tk.Frame(self.canvas, bg=_PANEL_ALT)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for widget in (self.canvas, self.body):
            self._bind_mousewheel(widget)

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        for index in range(len(self._rows)):
            self._apply_row_style(index)

    def set_items(self, items: list[dict[str, str]], *, selected_index: int | None = 0) -> None:
        normalized_items = [
            {
                "title": str(item.get("title", "")),
                "badge": str(item.get("badge", "")),
                "subtitle": str(item.get("subtitle", "")),
                "detail": str(item.get("detail", "")),
            }
            for item in items
        ]
        target_index = None
        if normalized_items and selected_index is not None:
            target_index = min(max(selected_index, 0), len(normalized_items) - 1)
        if normalized_items == self._items:
            if target_index is None and self.selected_index is not None:
                previous = self.selected_index
                self.selected_index = None
                self._apply_row_style(previous)
            elif target_index is not None and self.selected_index != target_index:
                self.select(target_index, notify=False)
            self._update_row_wraps()
            return

        top_fraction = 0.0
        try:
            if self._rows:
                top_fraction = self.canvas.yview()[0]
        except tk.TclError:
            top_fraction = 0.0

        self._items = [item.copy() for item in normalized_items]
        self.selected_index = None
        if len(normalized_items) == len(self._rows):
            for index, item in enumerate(normalized_items):
                self._update_row(index, item)
        else:
            for row in self._rows:
                try:
                    row["frame"].destroy()
                except tk.TclError:
                    pass
            self._rows.clear()

            for index, item in enumerate(normalized_items):
                self._rows.append(self._build_row(index, item))

        if target_index is None and self.selected_index is not None:
            previous = self.selected_index
            self.selected_index = None
            self._apply_row_style(previous)
        elif target_index is not None:
            self.select(target_index, notify=False)
        try:
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(top_fraction if self._rows else 0.0)
        except tk.TclError:
            pass
        self._update_row_wraps()

    def select(self, index: int, *, notify: bool = True) -> None:
        if not (0 <= index < len(self._rows)):
            return
        if notify and not self._enabled:
            return
        previous = self.selected_index
        self.selected_index = index
        if previous is not None and previous != index:
            self._apply_row_style(previous)
        self._apply_row_style(index)
        if notify and self.on_select is not None:
            self.on_select(index)

    def activate(self, index: int | None = None) -> None:
        if not self._enabled:
            return
        target = self.selected_index if index is None else index
        if target is None or not (0 <= target < len(self._rows)):
            return
        self.select(target)
        if self.on_activate is not None:
            self.on_activate(target)

    def _build_row(self, index: int, item: dict[str, str]) -> dict[str, Any]:
        row = tk.Frame(
            self.body,
            bg="#fbfcff",
            highlightbackground="#e4e8f0",
            highlightthickness=1,
            bd=0,
            cursor="hand2",
        )
        row.pack(fill=tk.X, pady=4)

        marker = tk.Frame(row, bg="#fbfcff", width=4, bd=0)
        marker.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        content = tk.Frame(row, bg="#fbfcff")
        content.pack(fill=tk.X, expand=True, padx=(0, 12), pady=10)

        header = tk.Frame(content, bg="#fbfcff")
        header.pack(fill=tk.X)
        header.grid_columnconfigure(0, weight=1)

        title = tk.Label(
            header,
            text=item.get("title", ""),
            bg="#fbfcff",
            fg=_TEXT,
            anchor="w",
            justify="left",
            font=make_font(11, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        badge = tk.Label(
            header,
            text=item.get("badge", ""),
            bg="#eef2f7",
            fg=_SUBTEXT,
            padx=8,
            pady=3,
            font=make_font(9, weight="bold"),
        )
        if item.get("badge", "").strip():
            badge.grid(row=0, column=1, sticky="e", padx=(10, 0))

        subtitle = tk.Label(
            content,
            text=item.get("subtitle", ""),
            bg="#fbfcff",
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10),
        )
        if item.get("subtitle", "").strip():
            subtitle.pack(fill=tk.X, pady=(6, 0))

        detail = tk.Label(
            content,
            text=item.get("detail", ""),
            bg="#fbfcff",
            fg=_MUTED,
            anchor="w",
            justify="left",
            font=make_font(9),
        )
        if item.get("detail", "").strip():
            detail.pack(fill=tk.X, pady=(4, 0))

        widgets = [row, marker, content, header, title, badge, subtitle, detail]
        for widget in widgets:
            self._bind_row_widget(widget, index)

        return {
            "frame": row,
            "marker": marker,
            "content": content,
            "header": header,
            "title": title,
            "badge": badge,
            "subtitle": subtitle,
            "detail": detail,
        }

    def _update_row(self, index: int, item: dict[str, str]) -> None:
        if not (0 <= index < len(self._rows)):
            return
        row = self._rows[index]
        row["title"].configure(text=item.get("title", ""))
        self._sync_grid_label(
            row["badge"],
            item.get("badge", ""),
            row=0,
            column=1,
            sticky="e",
            padx=(10, 0),
        )
        self._sync_packed_label(row["subtitle"], item.get("subtitle", ""), pady=(6, 0))
        self._sync_packed_label(row["detail"], item.get("detail", ""), pady=(4, 0))
        self._apply_row_style(index)

    @staticmethod
    def _sync_packed_label(widget: tk.Label, text: str, *, pady: tuple[int, int]) -> None:
        widget.configure(text=text)
        if text.strip():
            if widget.winfo_manager() != "pack":
                widget.pack(fill=tk.X, pady=pady)
        elif widget.winfo_manager():
            widget.pack_forget()

    @staticmethod
    def _sync_grid_label(widget: tk.Label, text: str, **grid_kwargs) -> None:
        widget.configure(text=text)
        if text.strip():
            widget.grid(**grid_kwargs)
        else:
            widget.grid_remove()

    def _bind_row_widget(self, widget: tk.Misc, index: int) -> None:
        widget.bind("<Button-1>", lambda _event, idx=index: self.select(idx), add="+")
        widget.bind("<Double-Button-1>", lambda _event, idx=index: self.activate(idx), add="+")
        self._bind_mousewheel(widget)

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_mousewheel, add="+")

    def _on_mousewheel(self, event) -> str:
        try:
            if getattr(event, "num", None) == 4:
                delta = -3
            elif getattr(event, "num", None) == 5:
                delta = 3
            else:
                raw_delta = getattr(event, "delta", 0)
                if raw_delta == 0:
                    return "break"
                delta = -3 if raw_delta > 0 else 3
            self.canvas.yview_scroll(delta, "units")
        except tk.TclError:
            return "break"
        return "break"

    def _on_body_configure(self, _event=None) -> None:
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            return
        self._update_row_wraps()

    def _on_canvas_configure(self, event=None) -> None:
        if event is None:
            return
        try:
            self.canvas.itemconfigure(self._window, width=event.width)
        except tk.TclError:
            return
        self._update_row_wraps()

    def _update_row_wraps(self) -> None:
        width = self.canvas.winfo_width()
        if width <= 1:
            return
        title_wrap = max(180, width - 168)
        detail_wrap = max(220, width - 44)
        for row in self._rows:
            for key, wrap in (("title", title_wrap), ("subtitle", detail_wrap), ("detail", detail_wrap)):
                try:
                    row[key].configure(wraplength=wrap)
                except tk.TclError:
                    pass

    def _apply_row_style(self, index: int) -> None:
        if not (0 <= index < len(self._rows)):
            return
        row = self._rows[index]
        selected = index == self.selected_index

        if not self._enabled:
            row_bg = "#f6f7fb"
            row_border = "#eceff5"
            title_fg = _MUTED
            subtitle_fg = _MUTED
            detail_fg = _MUTED
            badge_bg = "#eef1f5"
            badge_fg = _MUTED
            marker_bg = row_bg
        elif selected:
            row_bg = "#eaf4ff"
            row_border = "#b8d9ff"
            title_fg = _TEXT
            subtitle_fg = _TEXT
            detail_fg = _SUBTEXT
            badge_bg = _ACCENT
            badge_fg = _ACCENT_FG
            marker_bg = _ACCENT
        else:
            row_bg = "#fbfcff"
            row_border = "#e4e8f0"
            title_fg = _TEXT
            subtitle_fg = _SUBTEXT
            detail_fg = _MUTED
            badge_bg = "#eef2f7"
            badge_fg = _SUBTEXT
            marker_bg = row_bg

        for key in ("frame", "content", "header"):
            row[key].configure(bg=row_bg, highlightbackground=row_border, cursor="hand2" if self._enabled else "arrow")
        row["marker"].configure(bg=marker_bg, cursor="hand2" if self._enabled else "arrow")
        row["title"].configure(bg=row_bg, fg=title_fg, cursor="hand2" if self._enabled else "arrow")
        row["subtitle"].configure(bg=row_bg, fg=subtitle_fg, cursor="hand2" if self._enabled else "arrow")
        row["detail"].configure(bg=row_bg, fg=detail_fg, cursor="hand2" if self._enabled else "arrow")
        row["badge"].configure(bg=badge_bg, fg=badge_fg, cursor="hand2" if self._enabled else "arrow")

def open_mihomo_panel(app: "DeskVaneApp") -> None:
    global _active_panel
    if _active_panel is not None:
        try:
            _active_panel.sync_from_config()
            _active_panel.refresh()
            _active_panel.lift()
            _active_panel.focus_force()
            return
        except tk.TclError:
            _active_panel = None
    _active_panel = _MihomoPanel(app)


class _MihomoPanel:
    def __init__(self, app: "DeskVaneApp") -> None:
        self.app = app
        self.manager = app.mihomo_manager
        self.groups: list[MihomoProxyGroup] = []
        self._selected_group_name = ""
        self._selected_proxy_name = ""
        self._runtime_mode = ""
        self._delay_results: dict[str, str] = {}
        self._manual_delay_results: dict[str, str] = {}
        self._refresh_job = None
        self._action_busy = False
        self._refresh_inflight = False
        self._runtime_controls_available = False
        self._delay_url_user_override = False
        self._delay_url_trace_suspended = False
        self._auto_delay_url = DEFAULT_DELAY_TEST_URL
        self.mode_buttons: dict[str, tk.Button] = {}
        self._wrap_labels: list[tk.Label] = []

        self.win = tk.Toplevel(app.root)
        self.win.title("Mihomo 控制面板")
        self.win.configure(bg=_BG)
        self.win.geometry("980x760")
        self.win.minsize(760, 560)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self.win.bind("<Configure>", self._on_resize, add="+")

        self.status_var = tk.StringVar(value="加载中...")
        self.endpoint_var = tk.StringVar(value="")
        self.port_var = tk.StringVar(value="")
        self.active_route_var = tk.StringVar(value="")
        self.config_state_var = tk.StringVar(value="")
        self.subscription_state_var = tk.StringVar(value="")
        self.subscription_groups_var = tk.StringVar(value="")
        self.subscription_servers_var = tk.StringVar(value="")
        self.logs_var = tk.StringVar(value="")
        self.error_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="")
        self.mode_summary_var = tk.StringVar(value="等待 Core API")
        self.mode_detail_var = tk.StringVar(value="等待 Core API")
        self.primary_group_var = tk.StringVar(value="-")
        self.primary_node_var = tk.StringVar(value="-")
        self.auto_group_var = tk.StringVar(value="未启用")
        self.selection_title_var = tk.StringVar(value="当前生效组")
        self.selection_meta_var = tk.StringVar(value="请选择一个订阅节点")
        self.subscription_var = tk.StringVar(value=app.config.mihomo.subscription_url)
        self.delay_url_var = tk.StringVar(value=DEFAULT_DELAY_TEST_URL)
        self.delay_url_var.trace_add("write", self._on_delay_url_var_changed)
        self.delay_status_var = tk.StringVar(value="延迟测试：选择节点后可测速")
        self.tun_bypass_state_var = tk.StringVar(value="")
        self.pac_remote_url_var = tk.StringVar(value=app.config.mihomo.pac_remote_url)
        self.pac_proxy_domains_var = tk.StringVar(value=app.config.mihomo.pac_proxy_domains)
        self.pac_direct_domains_var = tk.StringVar(value=app.config.mihomo.pac_direct_domains)
        self.pac_default_action_var = tk.StringVar(value=app.config.mihomo.pac_default_action)
        self.pac_port_var = tk.StringVar(value=str(app.config.mihomo.pac_port))
        self.pac_url_var = tk.StringVar(value="")
        self.pac_state_var = tk.StringVar(value="")
        self.status_chip_var = tk.StringVar(value="检测中")
        self.summary_var = tk.StringVar(value="正在读取核心状态与订阅信息。")
        self._last_snapshot_signature: tuple[Any, ...] | None = None
        self._canvas: tk.Canvas | None = None
        self._canvas_window = None
        self._content: tk.Frame | None = None
        self._diagnostics_visible = False
        self._proxy_layout_mode: str | None = None
        self._proxy_section: tk.Frame | None = None
        self._proxy_left_card: tk.Frame | None = None
        self._proxy_right_card: tk.Frame | None = None
        self._advanced_groups: list[MihomoProxyGroup] = []
        self._advanced_groups_visible = False
        self._advanced_groups_body: tk.Frame | None = None
        self._advanced_groups_toggle_btn: tk.Button | None = None
        self.group_cards: _SelectableCardList | None = None
        self.proxy_cards: _SelectableCardList | None = None
        self._diagnostics_body: tk.Frame | None = None
        self._diagnostics_toggle_btn: tk.Button | None = None

        self._build()
        self._update_wrap_labels()
        self.sync_from_config()
        self._refresh_initial()
        self.win.after(1200, self._refresh_if_loading)

    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=_BG)
        outer.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(outer, bg=_BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(
            outer,
            orient="vertical",
            command=self._canvas.yview,
            bg=_PANEL_ALT,
            troughcolor=_BG,
            activebackground=_BORDER,
        )
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._content = tk.Frame(self._canvas, bg=_BG)
        self._canvas_window = self._canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self.win.bind("<Button-4>", self._on_mousewheel, add="+")
        self.win.bind("<Button-5>", self._on_mousewheel, add="+")
        self.win.bind("<MouseWheel>", self._on_mousewheel, add="+")

        has_external_ui = bool(
            self.app.config.mihomo.external_ui.strip()
            or self.app.config.mihomo.external_ui_name.strip()
            or self.app.config.mihomo.external_ui_url.strip()
        )
        header = tk.Frame(self._content, bg=_BG)
        header.pack(fill=tk.X, padx=24, pady=(24, 12))

        title_box = tk.Frame(header, bg=_BG)
        title_box.pack(fill=tk.X)
        tk.Label(
            title_box,
            text="Mihomo 控制台",
            bg=_BG,
            fg=_TEXT,
            font=make_font(18, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="状态、模式与节点切换。",
            bg=_BG,
            fg=_SUBTEXT,
            font=make_font(11),
        ).pack(anchor="w", pady=(4, 0))

        hero = themed_card(self._content, fill=tk.X, padx=24, pady=(0, 16))
        hero_body = tk.Frame(hero, bg=_PANEL)
        hero_body.pack(fill=tk.X, padx=18, pady=18)
        hero_top = tk.Frame(hero_body, bg=_PANEL)
        hero_top.pack(fill=tk.X)

        hero_left = tk.Frame(hero_top, bg=_PANEL)
        hero_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            hero_left,
            text="状态",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10, weight="bold"),
        ).pack(anchor="w")
        self.status_label = tk.Label(
            hero_left,
            textvariable=self.status_var,
            bg=_PANEL,
            fg=_TEXT,
            anchor="w",
            justify="left",
            font=make_font(17, weight="bold"),
        )
        self.status_label.pack(fill=tk.X, pady=(8, 6))
        summary_label = tk.Label(
            hero_left,
            textvariable=self.summary_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(11),
        )
        summary_label.pack(fill=tk.X)
        self._wrap_labels.append(summary_label)

        hero_right = tk.Frame(hero_top, bg=_PANEL)
        hero_right.pack(side=tk.RIGHT, anchor="ne", padx=(18, 0))
        self.status_chip = tk.Label(
            hero_right,
            textvariable=self.status_chip_var,
            bg="#eef4ff",
            fg=_ACCENT,
            padx=14,
            pady=7,
            font=make_font(10, weight="bold"),
            highlightbackground="#d7e6ff",
            highlightthickness=1,
        )
        self.status_chip.pack(anchor="e")

        actions = tk.Frame(hero_body, bg=_PANEL)
        actions.pack(fill=tk.X, pady=(18, 0))
        action_row_top = tk.Frame(actions, bg=_PANEL)
        action_row_top.pack(anchor="w")

        self.start_btn = themed_button(
            action_row_top,
            "启动",
            self._toggle_running,
            variant="primary",
            compact=True,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        themed_button(
            action_row_top,
            "刷新状态",
            self.refresh,
            variant="secondary",
            compact=True,
        ).pack(side=tk.LEFT, padx=(0, 10))
        themed_button(
            action_row_top,
            "重载配置",
            self._reload_config,
            variant="secondary",
            compact=True,
        ).pack(side=tk.LEFT, padx=(0, 10))

        overview = tk.Frame(hero_body, bg=_PANEL)
        overview.pack(fill=tk.X, pady=(18, 0))
        for column in range(4):
            overview.grid_columnconfigure(column, weight=1, uniform="overview")
        self._build_overview_card(overview, 0, 0, "控制地址", self.endpoint_var, mono=True)
        self._build_overview_card(overview, 0, 1, "端口", self.port_var, mono=True)
        self._build_overview_card(overview, 0, 2, "当前路径", self.active_route_var, mono=True)
        self._build_overview_card(overview, 0, 3, "配置与订阅", self.config_state_var)

        sub = themed_card(self._content, fill=tk.X, padx=24, pady=(0, 16))
        sub_body = tk.Frame(sub, bg=_PANEL)
        sub_body.pack(fill=tk.X, padx=18, pady=18)
        tk.Label(
            sub_body,
            text="订阅",
            bg=_PANEL,
            fg=_TEXT,
            font=make_font(12, weight="bold"),
        ).pack(anchor="w")
        sub_note = tk.Label(
            sub_body,
            text="只更新受管 Provider，不改你手写的主配置。",
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(11),
        )
        sub_note.pack(fill=tk.X, pady=(4, 10))
        self._wrap_labels.append(sub_note)
        subscription_state_label = tk.Label(
            sub_body,
            textvariable=self.subscription_state_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10, mono=True),
        )
        subscription_state_label.pack(fill=tk.X, pady=(0, 10))
        self._wrap_labels.append(subscription_state_label)
        tk.Label(
            sub_body,
            textvariable=self.subscription_groups_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10),
        ).pack(fill=tk.X, pady=(0, 4))
        subscription_servers_label = tk.Label(
            sub_body,
            textvariable=self.subscription_servers_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10, mono=True),
        )
        subscription_servers_label.pack(fill=tk.X, pady=(0, 10))
        self._wrap_labels.append(subscription_servers_label)

        sub_row = tk.Frame(sub_body, bg=_PANEL)
        sub_row.pack(fill=tk.X)

        self.subscription_entry = tk.Entry(
            sub_row,
            textvariable=self.subscription_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
        )
        self.subscription_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=6)
        actions_row = tk.Frame(sub_body, bg=_PANEL)
        actions_row.pack(fill=tk.X, pady=(10, 0))
        themed_button(actions_row, "保存地址", self._save_subscription_url, variant="secondary", compact=True).pack(side=tk.LEFT, padx=(0, 8))
        themed_button(actions_row, "更新当前输入", self._update_subscription, variant="primary", compact=True).pack(side=tk.LEFT, padx=(0, 8))
        self.subscription_update_saved_btn = themed_button(
            actions_row,
            "更新已保存地址",
            self._update_saved_subscription,
            variant="ghost",
            compact=True,
        )
        self.subscription_update_saved_btn.pack(side=tk.LEFT)

        modes = themed_card(self._content, fill=tk.X, padx=24, pady=(0, 16))
        modes_body = tk.Frame(modes, bg=_PANEL)
        modes_body.pack(fill=tk.X, padx=18, pady=18)
        tk.Label(
            modes_body,
            text="模式",
            bg=_PANEL,
            fg=_TEXT,
            font=make_font(12, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            modes_body,
            text="选择当前路由模式。",
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(11),
        ).pack(fill=tk.X, pady=(4, 10))
        tk.Label(
            modes_body,
            textvariable=self.mode_summary_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10, weight="bold"),
        ).pack(fill=tk.X, pady=(0, 10))

        self.mode_segment = tk.Frame(
            modes_body,
            bg=_PANEL_ALT,
            highlightbackground=_BORDER,
            highlightthickness=1,
            bd=0,
            padx=4,
            pady=4,
        )
        self.mode_segment.pack(anchor="w")
        for column in range(3):
            self.mode_segment.grid_columnconfigure(column, weight=1, uniform="mode")
        for mode, label in (("rule", "Rule"), ("global", "Global"), ("direct", "Direct")):
            button = tk.Button(
                self.mode_segment,
                text=label,
                command=lambda m=mode: self._switch_mode(m),
                bg=_PANEL_ALT,
                fg=_SUBTEXT,
                activebackground=_PANEL_ALT,
                activeforeground=_TEXT,
                bd=0,
                relief="flat",
                overrelief="flat",
                cursor="hand2",
                font=make_font(11, weight="bold"),
                padx=22,
                pady=12,
                highlightthickness=0,
                highlightcolor=_ACCENT,
                width=8,
            )
            button.grid(row=0, column=len(self.mode_buttons), sticky="nsew", padx=0, pady=0)
            self.mode_buttons[mode] = button

        # TUN toggle
        tun_row = tk.Frame(modes_body, bg=_PANEL)
        tun_row.pack(fill=tk.X, pady=(12, 0))
        tk.Label(
            tun_row,
            text="TUN 模式",
            bg=_PANEL,
            fg=_TEXT,
            font=make_font(11, weight="bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            tun_row,
            text="启用后应用无需单独设置代理",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.tun_btn = tk.Button(
            tun_row,
            text="TUN: 关",
            command=self._toggle_tun,
            bg=_PANEL_ALT,
            fg=_SUBTEXT,
            activebackground=_PANEL_ALT,
            activeforeground=_TEXT,
            bd=0,
            relief="flat",
            overrelief="flat",
            cursor="hand2",
            font=make_font(10, weight="bold"),
            padx=14,
            pady=6,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
        )
        self.tun_btn.pack(side=tk.RIGHT)

        # TUN bypass processes
        bypass_row = tk.Frame(modes_body, bg=_PANEL)
        bypass_row.pack(fill=tk.X, pady=(8, 0))
        tk.Label(
            bypass_row,
            text="直连程序",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(side=tk.LEFT)
        self.tun_bypass_var = tk.StringVar(value=self.app.config.mihomo.tun_direct_processes)
        self.tun_bypass_entry = tk.Entry(
            bypass_row,
            textvariable=self.tun_bypass_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
        )
        self.tun_bypass_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), ipady=4)
        self.tun_bypass_entry.bind("<Return>", lambda _event: self._save_tun_bypass(), add="+")
        self.tun_bypass_apply_btn = themed_button(
            bypass_row,
            "应用",
            self._save_tun_bypass,
            variant="secondary",
            compact=True,
        )
        self.tun_bypass_apply_btn.pack(side=tk.LEFT)
        tk.Label(
            modes_body,
            textvariable=self.tun_bypass_state_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10),
        ).pack(fill=tk.X, pady=(8, 0))

        # ── PAC 配置卡片 ──
        pac_card = themed_card(self._content, fill=tk.X, padx=24, pady=(0, 16))
        pac_body = tk.Frame(pac_card, bg=_PANEL)
        pac_body.pack(fill=tk.X, padx=18, pady=18)

        pac_header = tk.Frame(pac_body, bg=_PANEL)
        pac_header.pack(fill=tk.X)
        tk.Label(
            pac_header,
            text="PAC 自动代理",
            bg=_PANEL,
            fg=_TEXT,
            font=make_font(12, weight="bold"),
        ).pack(side=tk.LEFT)
        self.pac_btn = tk.Button(
            pac_header,
            text="PAC: 关",
            command=self._toggle_pac,
            bg=_PANEL_ALT,
            fg=_SUBTEXT,
            activebackground=_PANEL_ALT,
            activeforeground=_TEXT,
            bd=0,
            relief="flat",
            overrelief="flat",
            cursor="hand2",
            font=make_font(10, weight="bold"),
            padx=14,
            pady=6,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
        )
        self.pac_btn.pack(side=tk.RIGHT)

        pac_desc = tk.Label(
            pac_body,
            text="启用后浏览器/系统可通过 PAC URL 自动决定代理或直连。TUN 模式下规则同步到 Mihomo rules。",
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10),
        )
        pac_desc.pack(fill=tk.X, pady=(4, 10))
        self._wrap_labels.append(pac_desc)

        # PAC URL display
        pac_url_row = tk.Frame(pac_body, bg=_PANEL)
        pac_url_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            pac_url_row,
            text="PAC 地址",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(side=tk.LEFT)
        tk.Label(
            pac_url_row,
            textvariable=self.pac_url_var,
            bg=_PANEL,
            fg=_ACCENT,
            font=make_font(10, mono=True),
        ).pack(side=tk.LEFT, padx=(8, 8))
        themed_button(
            pac_url_row,
            "复制",
            self._copy_pac_url,
            variant="ghost",
            compact=True,
        ).pack(side=tk.LEFT)

        # PAC port
        pac_port_row = tk.Frame(pac_body, bg=_PANEL)
        pac_port_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            pac_port_row,
            text="PAC 端口",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(side=tk.LEFT)
        tk.Entry(
            pac_port_row,
            textvariable=self.pac_port_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
            width=8,
        ).pack(side=tk.LEFT, padx=(8, 0), ipady=4)

        # Remote PAC URL
        pac_remote_head = tk.Frame(pac_body, bg=_PANEL)
        pac_remote_head.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            pac_remote_head,
            text="远程 PAC 地址",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(anchor="w")
        pac_remote_hint = tk.Label(
            pac_remote_head,
            text="填写后自动下载并代理地址替换，优先于手动域名配置",
            bg=_PANEL,
            fg=_MUTED,
            font=make_font(9),
        )
        pac_remote_hint.pack(anchor="w")
        self._wrap_labels.append(pac_remote_hint)
        tk.Entry(
            pac_body,
            textvariable=self.pac_remote_url_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
        ).pack(fill=tk.X, pady=(0, 8), ipady=4)

        # Proxy domains
        pac_proxy_row = tk.Frame(pac_body, bg=_PANEL)
        pac_proxy_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            pac_proxy_row,
            text="代理域名",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(anchor="w")
        tk.Label(
            pac_proxy_row,
            text="逗号分隔的域名后缀，例如: google.com, github.com",
            bg=_PANEL,
            fg=_MUTED,
            font=make_font(9),
        ).pack(anchor="w")
        tk.Entry(
            pac_body,
            textvariable=self.pac_proxy_domains_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
        ).pack(fill=tk.X, pady=(0, 8), ipady=4)

        # Direct domains
        pac_direct_row = tk.Frame(pac_body, bg=_PANEL)
        pac_direct_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            pac_direct_row,
            text="直连域名",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(anchor="w")
        tk.Label(
            pac_direct_row,
            text="逗号分隔的域名后缀，例如: baidu.com, qq.com",
            bg=_PANEL,
            fg=_MUTED,
            font=make_font(9),
        ).pack(anchor="w")
        tk.Entry(
            pac_body,
            textvariable=self.pac_direct_domains_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
        ).pack(fill=tk.X, pady=(0, 8), ipady=4)

        # Default action
        pac_action_row = tk.Frame(pac_body, bg=_PANEL)
        pac_action_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            pac_action_row,
            text="默认行为",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(side=tk.LEFT)
        tk.Label(
            pac_action_row,
            text="未匹配域名的默认路由",
            bg=_PANEL,
            fg=_MUTED,
            font=make_font(9),
        ).pack(side=tk.LEFT, padx=(4, 0))
        self.pac_action_segment = tk.Frame(
            pac_action_row,
            bg=_PANEL_ALT,
            highlightbackground=_BORDER,
            highlightthickness=1,
            bd=0,
            padx=2,
            pady=2,
        )
        self.pac_action_segment.pack(side=tk.RIGHT)
        self.pac_action_buttons: dict[str, tk.Button] = {}
        for action, label in (("PROXY", "代理"), ("DIRECT", "直连")):
            btn = tk.Button(
                self.pac_action_segment,
                text=label,
                command=lambda a=action: self.pac_default_action_var.set(a),
                bg=_PANEL_ALT,
                fg=_SUBTEXT,
                activebackground=_PANEL_ALT,
                activeforeground=_TEXT,
                bd=0,
                relief="flat",
                overrelief="flat",
                cursor="hand2",
                font=make_font(10, weight="bold"),
                padx=12,
                pady=4,
                highlightthickness=0,
            )
            btn.pack(side=tk.LEFT)
            self.pac_action_buttons[action] = btn

        # Save button
        pac_save_row = tk.Frame(pac_body, bg=_PANEL)
        pac_save_row.pack(fill=tk.X, pady=(4, 0))
        themed_button(
            pac_save_row,
            "保存 PAC 配置",
            self._save_pac_config,
            variant="primary",
            compact=True,
        ).pack(side=tk.LEFT)
        tk.Label(
            pac_save_row,
            textvariable=self.pac_state_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(side=tk.LEFT, padx=(10, 0))

        self._proxy_section = tk.Frame(self._content, bg=_BG)
        self._proxy_section.pack(fill=tk.BOTH, padx=24, pady=(0, 16))
        self._proxy_left_card = themed_card(self._proxy_section)
        self._proxy_right_card = themed_card(self._proxy_section)

        left_body = tk.Frame(self._proxy_left_card, bg=_PANEL)
        left_body.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        right_body = tk.Frame(self._proxy_right_card, bg=_PANEL)
        right_body.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        left_head = tk.Frame(left_body, bg=_PANEL)
        left_head.pack(fill=tk.X)
        left_title = tk.Frame(left_head, bg=_PANEL)
        left_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(left_title, text="当前路由", bg=_PANEL, fg=_TEXT, font=make_font(12, weight="bold")).pack(anchor="w")
        tk.Label(
            left_title,
            text="主视图只保留常用节点。",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(11),
        ).pack(anchor="w", pady=(4, 0))
        self._advanced_groups_toggle_btn = themed_button(
            left_head,
            "显示高级",
            self._toggle_advanced_groups,
            variant="ghost",
            compact=True,
        )
        self._advanced_groups_toggle_btn.pack(side=tk.RIGHT)

        route_box = tk.Frame(
            left_body,
            bg="#f7f9fd",
            highlightbackground="#e6eaf2",
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        route_box.pack(fill=tk.X, pady=(12, 0))
        for caption, variable, color in (
            ("当前模式", self.mode_detail_var, _TEXT),
            ("当前生效组", self.primary_group_var, _TEXT),
            ("当前节点", self.primary_node_var, _TEXT),
            ("自动选择", self.auto_group_var, _SUBTEXT),
        ):
            row = tk.Frame(route_box, bg="#f7f9fd")
            row.pack(fill=tk.X, pady=(2, 2))
            tk.Label(
                row,
                text=caption,
                bg="#eef2f8",
                fg=_SUBTEXT,
                padx=8,
                pady=2,
                font=make_font(9, weight="bold"),
            ).pack(side=tk.LEFT, padx=(0, 8))
            value = tk.Label(
                row,
                textvariable=variable,
                bg="#f7f9fd",
                fg=color,
                anchor="w",
                justify="left",
                font=make_font(10, weight="bold" if caption != "自动选择" else "normal"),
            )
            value.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._wrap_labels.append(value)

        self._advanced_groups_body = tk.Frame(left_body, bg=_PANEL)
        advanced_title = tk.Frame(self._advanced_groups_body, bg=_PANEL)
        advanced_title.pack(fill=tk.X, pady=(14, 8))
        tk.Label(
            advanced_title,
            text="高级代理组",
            bg=_PANEL,
            fg=_TEXT,
            font=make_font(11, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            advanced_title,
            text="仅在需要时调整 Auto / Global / Direct。",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10),
        ).pack(anchor="w", pady=(4, 0))
        group_box = tk.Frame(self._advanced_groups_body, bg=_PANEL)
        group_box.pack(fill=tk.BOTH, expand=True)
        self.group_cards = _SelectableCardList(
            group_box,
            height=260,
            on_select=self._on_group_card_selected,
        )
        self.group_cards.container.pack(fill=tk.BOTH, expand=True)

        tk.Label(right_body, text="订阅节点与延迟", bg=_PANEL, fg=_TEXT, font=make_font(12, weight="bold")).pack(anchor="w")
        tk.Label(
            right_body,
            text="默认应用到当前生效组，双击节点即可切换。",
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(11),
        ).pack(fill=tk.X, pady=(4, 8))
        selection_box = tk.Frame(
            right_body,
            bg="#f7f9fd",
            highlightbackground="#e6eaf2",
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        selection_box.pack(fill=tk.X, pady=(0, 10))
        for caption, variable, color in (
            ("应用到", self.selection_title_var, _TEXT),
            ("当前节点", self.selection_meta_var, _SUBTEXT),
        ):
            row = tk.Frame(selection_box, bg="#f7f9fd")
            row.pack(fill=tk.X, pady=(2, 2))
            tk.Label(
                row,
                text=caption,
                bg="#eef2f8",
                fg=_SUBTEXT,
                padx=8,
                pady=2,
                font=make_font(9, weight="bold"),
            ).pack(side=tk.LEFT, padx=(0, 8))
            value = tk.Label(
                row,
                textvariable=variable,
                bg="#f7f9fd",
                fg=color,
                anchor="w",
                justify="left",
                font=make_font(10, weight="bold" if caption == "当前组" else "normal"),
            )
            value.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._wrap_labels.append(value)
        delay_row = tk.Frame(right_body, bg=_PANEL)
        delay_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            delay_row,
            text="测试 URL",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(10, weight="bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.delay_test_entry = tk.Entry(
            delay_row,
            textvariable=self.delay_url_var,
            bg=_PANEL_ALT,
            fg=_TEXT,
            insertbackground=_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            font=make_font(10, mono=True),
        )
        self.delay_test_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        proxy_box = tk.Frame(right_body, bg=_PANEL)
        proxy_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.proxy_cards = _SelectableCardList(
            proxy_box,
            height=350,
            on_select=self._on_proxy_card_selected,
            on_activate=lambda _index: self._apply_selected_proxy(),
        )
        self.proxy_cards.container.pack(fill=tk.BOTH, expand=True)

        delay_status_label = tk.Label(
            right_body,
            textvariable=self.delay_status_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10),
        )
        delay_status_label.pack(fill=tk.X, pady=(0, 10))
        self._wrap_labels.append(delay_status_label)

        proxy_actions = tk.Frame(right_body, bg=_PANEL)
        proxy_actions.pack(fill=tk.X)
        self.proxy_apply_btn = themed_button(proxy_actions, "应用所选节点", self._apply_selected_proxy, variant="primary", compact=True)
        self.proxy_apply_btn.pack(side=tk.LEFT)
        self.delay_selected_btn = themed_button(
            proxy_actions,
            "测试所选节点",
            self._test_selected_proxy_delay,
            variant="secondary",
            compact=True,
        )
        self.delay_selected_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.delay_group_btn = themed_button(
            proxy_actions,
            "测试当前组",
            self._test_current_group_delay,
            variant="ghost",
            compact=True,
        )
        self.delay_group_btn.pack(side=tk.LEFT, padx=(8, 0))

        diagnostics = themed_card(self._content, fill=tk.X, padx=24, pady=(0, 24))
        diagnostics_body = tk.Frame(diagnostics, bg=_PANEL)
        diagnostics_body.pack(fill=tk.X, padx=18, pady=18)
        diagnostics_head = tk.Frame(diagnostics_body, bg=_PANEL)
        diagnostics_head.pack(fill=tk.X)
        tk.Label(
            diagnostics_head,
            text="详细信息",
            bg=_PANEL,
            fg=_TEXT,
            font=make_font(12, weight="bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            diagnostics_head,
            text="需要时再展开日志、错误和辅助入口。",
            bg=_PANEL,
            fg=_SUBTEXT,
            font=make_font(11),
        ).pack(side=tk.LEFT, padx=(10, 0))
        self._diagnostics_toggle_btn = themed_button(
            diagnostics_head,
            "显示",
            self._toggle_diagnostics,
            variant="ghost",
            compact=True,
        )
        self._diagnostics_toggle_btn.pack(side=tk.RIGHT)

        self._diagnostics_body = tk.Frame(diagnostics_body, bg=_PANEL)
        self._diagnostics_body.pack(fill=tk.X, pady=(12, 0))
        self.logs_label = tk.Label(
            self._diagnostics_body,
            textvariable=self.logs_var,
            bg=_PANEL,
            fg=_SUBTEXT,
            anchor="w",
            justify="left",
            font=make_font(10, mono=True),
        )
        self.logs_label.pack(fill=tk.X, pady=(0, 4))
        self._wrap_labels.append(self.logs_label)
        self.error_label = tk.Label(
            self._diagnostics_body,
            textvariable=self.error_var,
            bg=_PANEL,
            fg=_DANGER,
            anchor="w",
            justify="left",
            font=make_font(10, mono=True),
        )
        self.error_label.pack(fill=tk.X, pady=(0, 4))
        self._wrap_labels.append(self.error_label)
        utility_row = tk.Frame(self._diagnostics_body, bg=_PANEL)
        utility_row.pack(fill=tk.X, pady=(10, 0))
        self.controller_btn = themed_button(
            utility_row,
            "打开 Web UI" if has_external_ui else "打开 API",
            self._open_controller,
            variant="secondary",
            compact=True,
        )
        self.controller_btn.pack(side=tk.LEFT, padx=(0, 10))
        themed_button(
            utility_row,
            "打开日志",
            self._open_logs,
            variant="secondary",
            compact=True,
        ).pack(side=tk.LEFT, padx=(0, 10))
        themed_button(
            utility_row,
            "打开配置",
            self._open_config,
            variant="ghost",
            compact=True,
        ).pack(side=tk.LEFT)

        self._set_diagnostics_visible(False)
        self._sync_advanced_groups_section()
        self._layout_proxy_section()

    def _build_overview_card(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        title: str,
        variable: tk.StringVar,
        *,
        mono: bool = False,
    ) -> tk.Label:
        tile = themed_card(parent, alt=True)
        tile.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
        body = tk.Frame(tile, bg=_PANEL_ALT)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        tk.Label(
            body,
            text=title,
            bg=_PANEL_ALT,
            fg=_SUBTEXT,
            anchor="w",
            font=make_font(9, weight="bold"),
        ).pack(fill=tk.X)
        value_label = tk.Label(
            body,
            textvariable=variable,
            bg=_PANEL_ALT,
            fg=_TEXT,
            anchor="w",
            justify="left",
            font=make_font(10, mono=mono),
        )
        value_label.pack(fill=tk.X, pady=(8, 0))
        self._wrap_labels.append(value_label)
        return value_label

    def sync_from_config(self) -> None:
        self.subscription_var.set(self.app.config.mihomo.subscription_url)
        self.tun_bypass_var.set(self.app.config.mihomo.tun_direct_processes)
        self._refresh_tun_bypass_state()
        self.pac_remote_url_var.set(self.app.config.mihomo.pac_remote_url)
        self.pac_proxy_domains_var.set(self.app.config.mihomo.pac_proxy_domains)
        self.pac_direct_domains_var.set(self.app.config.mihomo.pac_direct_domains)
        self.pac_default_action_var.set(self.app.config.mihomo.pac_default_action)
        self.pac_port_var.set(str(self.app.config.mihomo.pac_port))
        self._refresh_pac_state()

    def _refresh_tun_bypass_state(self) -> None:
        processes = self.app.config.mihomo.tun_direct_processes.strip()
        if processes:
            self.tun_bypass_state_var.set(f"当前直连程序: {processes}")
        else:
            self.tun_bypass_state_var.set("当前直连程序: 未配置")

    def refresh(self) -> None:
        if self._refresh_inflight:
            return
        if self._action_busy:
            self._schedule_refresh(delay_ms=600)
            return
        self._run_async(self._fetch_snapshot, self._apply_snapshot, task_kind="refresh")

    def _refresh_initial(self) -> None:
        try:
            self._apply_snapshot(self._fetch_snapshot())
        except Exception:
            self.refresh()

    def _refresh_if_loading(self) -> None:
        if not self.win.winfo_exists():
            return
        if self.status_var.get() in {"加载中...", "Mihomo Core 启动中"}:
            self.refresh()

    def _fetch_snapshot(self):
        core_status = self.manager.get_core_status()
        if core_status.api_ready:
            runtime = self.manager.get_runtime_state()
        else:
            runtime = MihomoRuntimeState(
                api_ready=False,
                controller=core_status.controller,
                mode="",
                mixed_port=None,
                port=None,
                socks_port=None,
                tun_enabled=False,
                groups=[],
            )
        return core_status, runtime

    def _apply_snapshot(self, snapshot) -> None:
        core_status, runtime = snapshot
        signature = self._snapshot_signature(core_status, runtime)
        refresh_delay_ms = 1000 if core_status.running and not (core_status.api_ready or runtime.api_ready) else 3000
        if signature == self._last_snapshot_signature:
            self._schedule_refresh(delay_ms=refresh_delay_ms)
            return
        self._last_snapshot_signature = signature
        self.start_btn.configure(text="关闭" if core_status.running else "启动")
        api_ready = bool(core_status.api_ready or runtime.api_ready)

        if api_ready:
            status_text = "Mihomo Core 运行中"
            status_color = _TEXT
            badge_text = "在线"
            badge_bg = "#eaf7ef"
            badge_fg = _SUCCESS
            badge_border = "#d3eedc"
        elif core_status.running:
            status_text = "Mihomo Core 启动中"
            status_color = _TEXT
            badge_text = "等待 API"
            badge_bg = "#fff6e8"
            badge_fg = _WARN
            badge_border = "#f3dfb4"
        else:
            status_text = "Mihomo Core 未运行"
            status_color = _TEXT
            badge_text = "已停止"
            badge_bg = "#f3f4f7"
            badge_fg = _SUBTEXT
            badge_border = _BORDER

        self.status_var.set(status_text)
        self.status_chip_var.set(badge_text)
        self.status_chip.configure(bg=badge_bg, fg=badge_fg, highlightbackground=badge_border)
        self.endpoint_var.set(core_status.controller)
        self.port_var.set(
            f"Mixed: {runtime.mixed_port or '-'}  |  Socks: {runtime.socks_port or '-'}"
        )
        config_state = "存在" if core_status.config_exists else "缺失"
        config_msg = f"主配置: {config_state}"
        if core_status.config_error:
            config_msg += f"  |  解析错误: {core_status.config_error}"
        self.config_state_var.set(
            f"{config_msg}  |  Provider: {'已生成' if core_status.provider_exists else '未生成'}  |  代理组: {len(runtime.groups)}"
        )
        if core_status.subscription_updated_at:
            subscription_text = f"{core_status.subscription_proxy_count} 个节点，最近更新 {core_status.subscription_updated_at}"
        elif self.subscription_var.get().strip():
            subscription_text = "已保存订阅地址，尚未同步到本地 Provider"
        else:
            subscription_text = "未配置订阅地址"
        self.subscription_state_var.set(subscription_text)
        if core_status.provider_exists:
            self.subscription_groups_var.set("订阅组: DESKVANE-PROXY / DESKVANE-AUTO")
            source = self._subscription_source_label(core_status.subscription_source)
            servers = self._truncate_middle(self._provider_server_preview(core_status.provider_path), 88)
            self.subscription_servers_var.set(
                f"订阅服务器: {servers}  |  节点数: {core_status.subscription_proxy_count}  |  来源: {source}"
            )
        else:
            self.subscription_groups_var.set("订阅组: 未生成受管订阅组")
            self.subscription_servers_var.set("订阅服务器: 暂无已同步节点")
        self.logs_var.set(f"stdout: {core_status.stdout_log_path}\nstderr: {core_status.stderr_log_path}")
        errors = []
        if core_status.last_error:
            errors.append(f"最近错误: {core_status.last_error}")
        if core_status.config_error:
            errors.append(f"配置异常: {core_status.config_error}")
        self.error_var.set("  |  ".join(errors) if errors else "最近错误: 无")
        if api_ready:
            tun_tag = "  TUN 已开启。" if runtime.tun_enabled else ""
            self.summary_var.set(f"{self.manager.display_name} 已连接，{len(runtime.groups)} 个代理组可用。{tun_tag}")
        elif core_status.running:
            self.summary_var.set("核心已启动，但控制 API 还没就绪。")
        else:
            self.summary_var.set("当前未启动 Mihomo Core。")
        self._runtime_mode = runtime.mode if api_ready else ""
        if api_ready and runtime.mode:
            self.mode_summary_var.set(f"当前模式: {runtime.mode.capitalize()}")
        elif core_status.running:
            self.mode_summary_var.set("当前模式: 等待 Core API")
        else:
            self.mode_summary_var.set("当前模式: Core 未启动")
        self.groups = self._ordered_groups(runtime.groups if api_ready else [])
        if api_ready:
            self._prime_delay_results(self.groups)
        self._refresh_route_summary()
        self.active_route_var.set(self._active_route_summary(self.groups) if api_ready else "未连接")
        self.mode_var.set(self._runtime_mode)
        self._rebuild_group_list()
        self._set_runtime_controls_enabled(api_ready)
        self._sync_mode_button_styles(runtime.mode if api_ready else "", api_ready)
        self._sync_tun_button(runtime.tun_enabled if api_ready else False, api_ready)
        self._refresh_pac_state()
        if not api_ready:
            self._set_selection_placeholder("等待 Core API", "启动后才能查看候选节点与延迟")
            self.delay_status_var.set("延迟测试：等待 Core API 就绪")
        self.status_label.configure(fg=status_color)
        self.error_label.configure(fg=_DANGER if errors else _SUCCESS)
        if errors and not self._diagnostics_visible:
            self._set_diagnostics_visible(True)
        self._refresh_tun_bypass_state()
        self._layout_proxy_section()

        self._schedule_refresh(delay_ms=refresh_delay_ms)

    def _rebuild_group_list(self) -> None:
        group_map = self._group_map(self.groups)
        primary_name = self._primary_group_name(self.groups)
        if self._selected_group_name not in group_map:
            self._selected_group_name = primary_name

        if self.groups:
            self._advanced_groups = self._advanced_groups_for_display(self.groups)
            if self.group_cards is not None:
                self.group_cards.set_items(
                    [
                        {
                            "title": group.name,
                            "badge": self._group_role_text(group),
                            "subtitle": self._truncate_middle(group.current or "-", 42),
                            "detail": self._group_card_detail(group),
                        }
                        for group in self._advanced_groups
                    ],
                    selected_index=next(
                        (index for index, group in enumerate(self._advanced_groups) if group.name == self._selected_group_name),
                        None,
                    ),
                )
            current_group = self._current_group()
            if current_group is not None:
                self._populate_proxy_list(current_group)
        else:
            self._advanced_groups = []
            if self.group_cards is not None:
                self.group_cards.set_items([])
            if self.proxy_cards is not None:
                self.proxy_cards.set_items([])
            self._selected_group_name = ""
            self._selected_proxy_name = ""
            self._set_selection_placeholder("没有可切换的代理组", "当前配置没有暴露可切换的代理组")
        self._sync_advanced_groups_section()

    def _on_group_card_selected(self, index: int) -> None:
        if index >= len(self._advanced_groups):
            return
        group = self._advanced_groups[index]
        self._selected_group_name = group.name
        self._populate_proxy_list(group)

    def _on_proxy_card_selected(self, index: int) -> None:
        group = self._current_group()
        if group is None or index >= len(group.candidates):
            self._selected_proxy_name = ""
            return
        self._selected_proxy_name = group.candidates[index]
        self._set_selection_summary(group)

    def _populate_proxy_list(self, group: MihomoProxyGroup) -> None:
        self._set_selection_summary(group)
        self._maybe_adopt_group_test_url(group)
        visible_candidates = self._visible_candidates(group, self.groups)
        selected_index = 0
        if self._selected_proxy_name in visible_candidates:
            selected_index = visible_candidates.index(self._selected_proxy_name)
        else:
            current_leaf = self._leaf_candidate_name(group, self.groups)
            if current_leaf in visible_candidates:
                selected_index = visible_candidates.index(current_leaf)

        rows: list[dict[str, str]] = []
        for index, candidate in enumerate(visible_candidates):
            compact_name = self._truncate_middle(candidate, 42)
            is_current = candidate == self._leaf_candidate_name(group, self.groups)
            is_selected = index == selected_index
            if is_current:
                subtitle = "当前节点"
                detail = ""
            elif is_selected:
                subtitle = "已选中"
                detail = candidate if compact_name != candidate else ""
            else:
                subtitle = ""
                detail = ""
            delay = self._delay_badge_text(candidate)
            rows.append(
                {
                    "title": compact_name,
                    "badge": delay,
                    "subtitle": subtitle,
                    "detail": detail,
                }
            )
        if visible_candidates:
            if self.proxy_cards is not None:
                self.proxy_cards.set_items(rows, selected_index=selected_index)
            self._selected_proxy_name = visible_candidates[selected_index]
        else:
            if self.proxy_cards is not None:
                self.proxy_cards.set_items([])
            self._selected_proxy_name = ""
            if group.name == "Direct" or group.current.strip().upper() == "DIRECT":
                self.selection_meta_var.set("当前为 Direct 模式，无需选择节点")
            else:
                self.selection_meta_var.set("这个组没有可直接选择的订阅节点")

    def _ordered_groups(self, groups: list[MihomoProxyGroup]) -> list[MihomoProxyGroup]:
        group_names = {group.name for group in groups}
        active_name = self._active_group_name(groups)
        active_child = self._active_child_group_name(groups, active_name)

        preferred_order: list[str] = []
        if active_name and active_name in group_names:
            preferred_order.append(active_name)
        if active_child and active_child not in preferred_order:
            preferred_order.append(active_child)
        for name in ("PROXY", "GLOBAL", "Auto", "Direct"):
            if name in group_names and name not in preferred_order:
                preferred_order.append(name)

        order_map = {name: index for index, name in enumerate(preferred_order)}
        return sorted(groups, key=lambda group: (order_map.get(group.name, 99), group.name.lower()))

    def _primary_group_name(self, groups: list[MihomoProxyGroup]) -> str:
        if not groups:
            return ""
        available = {group.name for group in groups}
        active_name = self._active_group_name(groups)
        preferred: list[str] = []
        if active_name:
            preferred.append(active_name)
        if self._runtime_mode == "rule":
            preferred.extend(["PROXY", "DESKVANE-PROXY"])
        elif self._runtime_mode == "global":
            preferred.append("GLOBAL")
        elif self._runtime_mode == "direct":
            preferred.append("Direct")
        preferred.extend(["PROXY", "DESKVANE-PROXY", "GLOBAL", "Auto", "Direct"])
        for name in preferred:
            if name in available:
                return name
        return groups[0].name

    def _advanced_groups_for_display(self, groups: list[MihomoProxyGroup]) -> list[MihomoProxyGroup]:
        primary_name = self._primary_group_name(groups)
        preferred_order = ["Auto", "GLOBAL", "Direct", "DESKVANE-AUTO", "DESKVANE-PROXY"]
        group_map = self._group_map(groups)
        ordered: list[MihomoProxyGroup] = []
        seen: set[str] = set()
        for name in preferred_order:
            if name == primary_name or name in seen:
                continue
            group = group_map.get(name)
            if group is None:
                continue
            ordered.append(group)
            seen.add(name)
        for group in self._ordered_groups(groups):
            if group.name == primary_name or group.name in seen:
                continue
            ordered.append(group)
            seen.add(group.name)
        return ordered

    def _visible_candidates(self, group: MihomoProxyGroup, groups: list[MihomoProxyGroup] | None = None) -> list[str]:
        group_names = {item.name for item in (groups if groups is not None else self.groups)}
        visible: list[str] = []
        for candidate in group.candidates:
            normalized = candidate.strip()
            if not normalized:
                continue
            if normalized in group_names:
                continue
            if normalized.upper() in {"DIRECT", "REJECT"}:
                continue
            visible.append(normalized)
        return visible

    def _leaf_candidate_name(self, group: MihomoProxyGroup, groups: list[MihomoProxyGroup]) -> str:
        group_map = self._group_map(groups)
        current = group.current.strip()
        seen: set[str] = set()
        while current and current in group_map and current not in seen:
            seen.add(current)
            current = group_map[current].current.strip()
        return current or group.current or "-"

    def _active_group_name(self, groups: list[MihomoProxyGroup] | None = None) -> str:
        available = {group.name for group in (groups if groups is not None else self.groups)}
        if self._runtime_mode == "global":
            return "GLOBAL" if "GLOBAL" in available else ""
        if self._runtime_mode == "rule":
            return "PROXY" if "PROXY" in available else ""
        if self._runtime_mode == "direct":
            return "Direct" if "Direct" in available else ""
        return ""

    @staticmethod
    def _group_map(groups: list[MihomoProxyGroup]) -> dict[str, MihomoProxyGroup]:
        return {group.name: group for group in groups}

    @staticmethod
    def _format_mode_label(mode: str) -> str:
        mapping = {
            "rule": "Rule",
            "global": "Global",
            "direct": "Direct",
        }
        return mapping.get(mode, mode or "-")

    def _active_child_group_name(self, groups: list[MihomoProxyGroup], active_name: str) -> str:
        if not active_name:
            return ""
        group = self._group_map(groups).get(active_name)
        if group is None:
            return ""
        candidate = group.current.strip()
        return candidate if candidate in self._group_map(groups) else ""

    @staticmethod
    def _truncate_middle(text: str, limit: int) -> str:
        value = text.strip()
        if len(value) <= limit:
            return value
        keep_head = max(12, limit // 2 - 2)
        keep_tail = max(10, limit - keep_head - 1)
        return f"{value[:keep_head]}…{value[-keep_tail:]}"

    @staticmethod
    def _subscription_source_label(source: str) -> str:
        raw = source.strip()
        if not raw:
            return "本地 Provider"
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return parsed.netloc
        return _MihomoPanel._truncate_middle(raw, 48)

    @staticmethod
    def _provider_server_preview(provider_path: str, limit: int = 4) -> str:
        path = Path(provider_path)
        if not path.exists():
            return "-"
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return "读取失败"
        proxies = loaded.get("proxies")
        if not isinstance(proxies, list):
            return "-"

        servers: list[str] = []
        seen: set[str] = set()
        for item in proxies:
            if not isinstance(item, dict):
                continue
            server = str(item.get("server") or "").strip()
            if not server or server in seen:
                continue
            seen.add(server)
            servers.append(server)

        if not servers:
            return "-"

        preview = ", ".join(servers[:limit])
        if len(servers) > limit:
            preview += f" 等 {len(servers)} 个"
        return preview

    def _group_role_text(self, group: MihomoProxyGroup) -> str:
        active_name = self._active_group_name(self.groups)
        active_child = self._active_child_group_name(self.groups, active_name)
        if group.name == active_name:
            return "生效中"
        if group.name == active_child:
            return "链路子组"
        if group.name == "PROXY" and self._runtime_mode != "rule":
            return "Rule"
        if group.name == "GLOBAL" and self._runtime_mode != "global":
            return "Global"
        if group.name == "Auto":
            return "测速"
        if group.name == "Direct":
            return "直连"
        return ""

    def _set_selection_placeholder(self, title: str, detail: str) -> None:
        self.selection_title_var.set(title)
        self.selection_meta_var.set(detail)

    def _set_selection_summary(self, group: MihomoProxyGroup) -> None:
        title = group.name
        selected = self._truncate_middle(
            self._selected_proxy_name or self._leaf_candidate_name(group, self.groups) or "-",
            54,
        )
        suffix = ""
        if self._selected_proxy_name:
            if self._selected_proxy_name == self._leaf_candidate_name(group, self.groups):
                suffix = "当前节点"
            else:
                suffix = "双击可应用"
        detail = f"{selected} · {suffix}" if suffix else selected
        self.selection_title_var.set(title)
        self.selection_meta_var.set(detail)

    def _refresh_route_summary(self) -> None:
        mode_label = self._format_mode_label(self._runtime_mode)
        self.mode_detail_var.set(mode_label if self._runtime_mode else "等待 Core API")
        primary_name = self._primary_group_name(self.groups)
        self.primary_group_var.set(primary_name or "-")
        group_map = self._group_map(self.groups)
        primary_group = group_map.get(primary_name)
        if primary_group is not None:
            self.primary_node_var.set(self._truncate_middle(self._leaf_candidate_name(primary_group, self.groups), 48))
        else:
            self.primary_node_var.set("-")

        auto_group = group_map.get("Auto") or group_map.get("DESKVANE-AUTO")
        if auto_group is not None:
            self.auto_group_var.set(self._truncate_middle(self._leaf_candidate_name(auto_group, self.groups), 48))
        else:
            self.auto_group_var.set("未启用")

    def _delay_badge_text(self, candidate: str) -> str:
        delay = self._delay_results.get(candidate, "").strip()
        return delay.replace(" ms", "ms") if delay else "未测速"

    def _group_card_detail(self, group: MihomoProxyGroup) -> str:
        active_name = self._active_group_name(self.groups)
        active_child = self._active_child_group_name(self.groups, active_name)
        if group.name == active_name:
            return "立即生效"
        if group.name == active_child:
            return "当前链路子组"
        if group.name == "GLOBAL" and self._runtime_mode == "rule":
            return "Rule 下暂不生效"
        if group.name == "PROXY" and self._runtime_mode == "global":
            return "Global 下暂不生效"
        if group.name == "Auto":
            return "自动选择节点"
        if group.name == "Direct":
            return "手动直连"
        return ""

    def _snapshot_signature(self, core_status, runtime) -> tuple[Any, ...]:
        group_signature = tuple(
            (
                group.name,
                group.group_type,
                group.current,
                tuple(group.candidates),
                group.last_delay_ms,
                tuple(sorted(group.candidate_delays.items())),
                group.test_url,
            )
            for group in runtime.groups
        )
        return (
            core_status.running,
            core_status.api_ready,
            core_status.controller,
            core_status.last_error,
            core_status.config_exists,
            core_status.config_error,
            core_status.provider_exists,
            core_status.stdout_log_path,
            core_status.stderr_log_path,
            core_status.subscription_updated_at,
            core_status.subscription_proxy_count,
            runtime.api_ready,
            runtime.mode,
            runtime.mixed_port,
            runtime.socks_port,
            runtime.tun_enabled,
            group_signature,
        )

    def _prime_delay_results(self, groups: list[MihomoProxyGroup]) -> None:
        runtime_results: dict[str, str] = {}
        for group in groups:
            if group.last_delay_ms is not None:
                runtime_results[group.name] = f"{group.last_delay_ms} ms"
            for candidate, delay in group.candidate_delays.items():
                runtime_results[candidate] = f"{delay} ms"
        runtime_results.update(self._manual_delay_results)
        self._delay_results = runtime_results

    def _maybe_adopt_group_test_url(self, group: MihomoProxyGroup) -> None:
        recommended = group.test_url.strip() or DEFAULT_DELAY_TEST_URL
        if not self._delay_url_user_override:
            self._set_delay_url(recommended)

    def _active_route_summary(self, groups: list[MihomoProxyGroup]) -> str:
        mode = self._runtime_mode.strip() or "-"
        active_name = self._active_group_name(groups)
        if not active_name:
            return mode.capitalize()

        group_map = self._group_map(groups)
        path: list[str] = [mode.capitalize()]
        current = active_name
        seen: set[str] = set()
        while current and current not in seen:
            path.append(current)
            seen.add(current)
            group = group_map.get(current)
            if group is None:
                break
            candidate = group.current.strip()
            if not candidate or candidate == current:
                break
            current = candidate

        return " -> ".join(path)

    def _group_hint(self, group: MihomoProxyGroup) -> str:
        active_name = self._active_group_name(self.groups)
        active_child = self._active_child_group_name(self.groups, active_name)

        if group.name == active_name:
            return "切换后立即影响流量"
        if group.name == active_child:
            return f"{active_name} 正在使用这个子组"
        if group.name == "GLOBAL" and self._runtime_mode == "rule":
            return "当前是 Rule，切到 Global 后才会生效"
        if group.name == "PROXY" and self._runtime_mode == "global":
            return "当前是 Global，切回 Rule 后才会生效"
        if group.name == "Auto":
            if active_child == "Auto":
                return "当前链路正在使用 Auto"
            return "只有当前链路指向 Auto 时才会生效"
        return "切换后会更新这个组的当前节点"

    def _set_delay_url(self, value: str) -> None:
        normalized = value.strip() or DEFAULT_DELAY_TEST_URL
        self._delay_url_trace_suspended = True
        self.delay_url_var.set(normalized)
        self._delay_url_trace_suspended = False
        self._auto_delay_url = normalized
        self._delay_url_user_override = False

    def _on_delay_url_var_changed(self, *_args) -> None:
        if self._delay_url_trace_suspended:
            return
        current = self.delay_url_var.get().strip()
        self._delay_url_user_override = bool(current and current != self._auto_delay_url)

    def _switch_mode(self, mode: str) -> None:
        self._run_async(
            lambda: self.app.mihomo_set_mode(mode),
            lambda success: self._after_action(
                success,
                f"模式切换失败：{mode}。请确认 Core API 已就绪。",
            ),
            task_kind="action",
        )

    def _toggle_tun(self) -> None:
        self._run_async(
            self.app.mihomo_toggle_tun,
            lambda success: self._after_action(
                success,
                "TUN 模式切换失败。请确认 Core API 已就绪且拥有必要权限。",
            ),
            task_kind="action",
        )

    def _save_tun_bypass(self) -> None:
        raw = self.tun_bypass_var.get().strip()
        self._run_async(
            lambda: self.app.mihomo_set_tun_bypass(raw),
            self._after_tun_bypass_saved,
            task_kind="action",
        )

    def _after_tun_bypass_saved(self, success: bool) -> None:
        if success:
            self.sync_from_config()
            self._after_action(True, "")
            return
        self.tun_bypass_state_var.set("当前直连程序: 保存失败")
        self.refresh()

    def _toggle_pac(self) -> None:
        self._run_async(
            self.app.mihomo_toggle_pac,
            lambda success: self._after_pac_action(
                success,
                "PAC 模式切换失败。",
            ),
            task_kind="action",
        )

    def _after_pac_action(self, success: bool, error_msg: str) -> None:
        self._refresh_pac_state()
        self._after_action(success, error_msg)

    def _save_pac_config(self) -> None:
        remote_url = self.pac_remote_url_var.get()
        proxy_domains = self.pac_proxy_domains_var.get()
        direct_domains = self.pac_direct_domains_var.get()
        default_action = self.pac_default_action_var.get()
        try:
            pac_port = int(self.pac_port_var.get().strip())
        except (ValueError, TypeError):
            pac_port = None
        self._run_async(
            lambda: self.app.mihomo_save_pac_config(
                proxy_domains, direct_domains, default_action, pac_port,
                remote_url=remote_url,
            ),
            lambda success: self._after_pac_action(
                success,
                "PAC 配置保存失败。",
            ),
            task_kind="action",
        )

    def _copy_pac_url(self) -> None:
        self.app.mihomo_copy_pac_url()

    def _refresh_pac_state(self) -> None:
        cfg = self.app.config.mihomo
        pac_enabled = cfg.pac_enabled
        pac_running = self.manager.is_pac_running()

        # Update button
        if pac_enabled:
            self.pac_btn.configure(
                text="PAC: 开",
                bg=_ACCENT,
                fg=_ACCENT_FG,
                activebackground=_ACCENT_HOVER,
                activeforeground=_ACCENT_FG,
            )
        else:
            self.pac_btn.configure(
                text="PAC: 关",
                bg=_PANEL_ALT,
                fg=_SUBTEXT,
                activebackground=_PANEL_ALT,
                activeforeground=_TEXT,
            )

        # Update PAC URL
        self.pac_url_var.set(self.manager.pac_url if pac_enabled else "（未启用）")

        # Update default action buttons
        current_action = self.pac_default_action_var.get()
        for action, btn in self.pac_action_buttons.items():
            if action == current_action:
                btn.configure(bg=_ACCENT, fg=_ACCENT_FG)
            else:
                btn.configure(bg=_PANEL_ALT, fg=_SUBTEXT)

        # State label
        remote_url = getattr(cfg, "pac_remote_url", "") or ""
        if pac_enabled and pac_running and remote_url.strip():
            self.pac_state_var.set("PAC 服务运行中（远程 PAC）")
        elif pac_enabled and pac_running:
            self.pac_state_var.set("PAC 服务运行中")
        elif pac_enabled and not pac_running:
            self.pac_state_var.set("PAC 已启用但服务未运行")
        else:
            self.pac_state_var.set("")

    def _apply_selected_proxy(self, _event=None) -> None:
        group = self._current_group()
        if group is None:
            return
        candidate = self._selected_proxy_name.strip()
        if not candidate:
            return
        self._run_async(
            lambda: self.app.mihomo_switch_proxy(group.name, candidate),
            lambda success: self._after_action(
                success,
                f"节点切换失败：{group.name} -> {candidate}",
            ),
            task_kind="action",
        )

    def _reload_config(self) -> None:
        self._run_async(
            self.app.mihomo_reload_core_config,
            lambda success: self._after_action(
                success,
                "配置重载失败，请检查错误信息区和日志。",
            ),
            task_kind="action",
        )

    def _save_subscription_url(self) -> None:
        url = self.subscription_var.get().strip()
        self._run_async(
            lambda: self.app.mihomo_save_subscription_url(url),
            lambda success: self._after_action(
                success,
                "订阅地址保存失败。",
            ),
            task_kind="action",
        )

    def _update_saved_subscription(self) -> None:
        self._run_async(
            self.app.mihomo_update_subscription,
            lambda success: self._after_action(
                success,
                "订阅更新失败，请先保存有效订阅地址。",
            ),
            task_kind="action",
        )

    def _update_subscription(self) -> None:
        url = self.subscription_var.get().strip()
        self._run_async(
            lambda: self.app.mihomo_update_subscription(url),
            lambda success: self._after_action(
                success,
                "订阅更新失败，请检查订阅地址和错误信息区。",
            ),
            task_kind="action",
        )

    def _test_selected_proxy_delay(self) -> None:
        group = self._current_group()
        if group is None:
            return
        candidate = self._selected_proxy_name.strip()
        if not candidate:
            return
        self._run_delay_test(candidate)

    def _test_current_group_delay(self) -> None:
        group = self._current_group()
        if group is None:
            return
        self._run_delay_test(group.name)

    def _run_delay_test(self, target_name: str) -> None:
        group = self._current_group()
        recommended_url = group.test_url.strip() if group is not None else ""
        test_url = self.delay_url_var.get().strip() or recommended_url or DEFAULT_DELAY_TEST_URL
        self.delay_status_var.set(f"延迟测试中：{target_name}")
        self._run_async(
            lambda: self.app.mihomo_test_proxy_delay(target_name, test_url),
            lambda delay, target=target_name, url=test_url: self._after_delay_test(target, url, delay),
            task_kind="action",
        )

    def _after_delay_test(self, target_name: str, test_url: str, delay: int | None) -> None:
        if delay is None:
            self.delay_status_var.set(f"延迟测试失败：{target_name}  |  URL: {test_url}")
            messagebox.showwarning(
                "延迟测试失败",
                f"{target_name}\n未能完成延迟测试，请确认节点可用或更换测试 URL。",
                parent=self.win,
            )
            return

        self._manual_delay_results[target_name] = f"{delay} ms"
        self._delay_results[target_name] = f"{delay} ms"
        self.delay_status_var.set(f"最近测试：{target_name}  |  {delay} ms  |  URL: {test_url}")
        self.app.tray.refresh()
        self._last_snapshot_signature = None
        self.refresh()

    def _toggle_running(self) -> None:
        self._run_async(
            self._toggle_running_sync,
            lambda success: self._after_action(
                success,
                "启动或关闭 Mihomo Core 失败，请检查日志。",
            ),
            task_kind="action",
        )

    def _toggle_running_sync(self):
        return self.app.toggle_mihomo()

    def _open_config(self) -> None:
        config_path = self.manager.get_core_status().config_path
        try:
            subprocess.Popen(["xdg-open", config_path])
        except FileNotFoundError:
            messagebox.showerror("打开失败", config_path, parent=self.win)

    def _open_logs(self) -> None:
        logs_dir = self.manager.get_core_status().logs_dir
        try:
            subprocess.Popen(["xdg-open", logs_dir])
        except FileNotFoundError:
            messagebox.showerror("打开失败", logs_dir, parent=self.win)

    def _open_controller(self) -> None:
        self.app.open_mihomo_controller()

    def _after_action(self, success: bool, failure_message: str) -> None:
        if success:
            self.sync_from_config()
            self.app.tray.refresh()
            self.refresh()
            return
        messagebox.showwarning("操作失败", failure_message, parent=self.win)
        self.refresh()

    def _current_group(self) -> MihomoProxyGroup | None:
        group_map = self._group_map(self.groups)
        selected = group_map.get(self._selected_group_name)
        if selected is not None:
            return selected
        primary_name = self._primary_group_name(self.groups)
        primary = group_map.get(primary_name)
        if primary is not None:
            return primary
        return self.groups[0] if self.groups else None

    def _run_async(self, fn, on_done, task_kind: str = "action") -> None:
        if task_kind == "refresh":
            if self._refresh_inflight:
                return
            self._refresh_inflight = True
        else:
            if self._action_busy:
                self.delay_status_var.set("正在处理上一个操作，请稍候")
                return
            self._set_busy_state(task_kind, True)

        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:
                self._dispatch_ui(self._on_async_error, exc, task_kind)
                return
            self._dispatch_ui(self._on_async_done, on_done, result, task_kind)

        threading.Thread(target=worker, daemon=True).start()

    def _dispatch_ui(self, fn, *args) -> None:
        dispatcher = getattr(self.app, "dispatcher", None)
        if dispatcher is not None:
            dispatcher.call_soon(fn, *args)
            return
        if not self._ui_alive():
            return
        try:
            self.win.after(0, lambda: fn(*args))
        except tk.TclError:
            pass

    def _ui_alive(self) -> bool:
        win = getattr(self, "win", None)
        if win is None:
            return False
        exists = getattr(win, "winfo_exists", None)
        if exists is None:
            return True
        try:
            return bool(exists())
        except tk.TclError:
            return False

    def _on_async_done(self, on_done, result, task_kind: str) -> None:
        self._set_busy_state(task_kind, False)
        if not self._ui_alive():
            return
        on_done(result)

    def _on_async_error(self, exc: Exception, task_kind: str) -> None:
        self._set_busy_state(task_kind, False)
        if not self._ui_alive():
            return
        messagebox.showerror("Mihomo 错误", str(exc), parent=self.win)
        self._schedule_refresh()

    def _schedule_refresh(self, delay_ms: int = 3000) -> None:
        if not self._ui_alive():
            return
        if self._refresh_job is not None:
            try:
                self.win.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        self._refresh_job = self.win.after(delay_ms, self.refresh)

    def _set_busy_state(self, task_kind: str, busy: bool) -> None:
        if task_kind == "refresh":
            self._refresh_inflight = busy
            return
        self._action_busy = busy
        if busy:
            self.delay_status_var.set("正在处理操作，请稍候")

    def _set_runtime_controls_enabled(self, enabled: bool) -> None:
        self._runtime_controls_available = enabled
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in self.mode_buttons.values():
            button.configure(state=state)
        if self.group_cards is not None:
            self.group_cards.set_enabled(enabled)
        if self.proxy_cards is not None:
            self.proxy_cards.set_enabled(enabled)
        self.proxy_apply_btn.configure(state=state)
        self.delay_test_entry.configure(state=state)
        self.delay_selected_btn.configure(state=state)
        self.delay_group_btn.configure(state=state)
        self.controller_btn.configure(state=state)

    def _sync_advanced_groups_section(self) -> None:
        if self._advanced_groups_toggle_btn is None or self._advanced_groups_body is None:
            return
        has_advanced = bool(self._advanced_groups)
        self._advanced_groups_toggle_btn.configure(
            state=tk.NORMAL if has_advanced else tk.DISABLED,
            text="收起高级" if self._advanced_groups_visible and has_advanced else ("显示高级" if has_advanced else "无高级项"),
        )
        if self._advanced_groups_visible and has_advanced:
            self._advanced_groups_body.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        else:
            self._advanced_groups_body.pack_forget()

    def _toggle_advanced_groups(self) -> None:
        if not self._advanced_groups:
            return
        self._advanced_groups_visible = not self._advanced_groups_visible
        if not self._advanced_groups_visible:
            primary_name = self._primary_group_name(self.groups)
            if primary_name and self._selected_group_name != primary_name:
                self._selected_group_name = primary_name
                current_group = self._current_group()
                if current_group is not None:
                    self._populate_proxy_list(current_group)
        self._sync_advanced_groups_section()

    def _layout_proxy_section(self) -> None:
        if self._proxy_section is None or self._proxy_left_card is None or self._proxy_right_card is None:
            return
        width = self.win.winfo_width()
        if self._canvas is not None:
            try:
                canvas_width = self._canvas.winfo_width()
                if canvas_width > 1:
                    width = canvas_width
            except tk.TclError:
                pass

        layout_mode = "stack" if width < 920 else "split"
        if layout_mode == self._proxy_layout_mode:
            return
        self._proxy_layout_mode = layout_mode
        self._proxy_left_card.grid_forget()
        self._proxy_right_card.grid_forget()
        self._proxy_section.grid_rowconfigure(0, weight=0)
        self._proxy_section.grid_rowconfigure(1, weight=0)
        if layout_mode == "stack":
            self._proxy_section.grid_columnconfigure(0, weight=1)
            self._proxy_left_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12), padx=0)
            self._proxy_right_card.grid(row=1, column=0, sticky="nsew", padx=0)
        else:
            self._proxy_section.grid_columnconfigure(0, weight=4)
            self._proxy_section.grid_columnconfigure(1, weight=6)
            self._proxy_left_card.grid(row=0, column=0, sticky="nsew")
            self._proxy_right_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

    def _set_diagnostics_visible(self, visible: bool) -> None:
        self._diagnostics_visible = visible
        if self._diagnostics_body is None or self._diagnostics_toggle_btn is None:
            return
        if visible:
            self._diagnostics_body.pack(fill=tk.X, pady=(12, 0))
            self._diagnostics_toggle_btn.configure(text="收起")
        else:
            self._diagnostics_body.pack_forget()
            self._diagnostics_toggle_btn.configure(text="显示")

    def _toggle_diagnostics(self) -> None:
        self._set_diagnostics_visible(not self._diagnostics_visible)

    def _sync_mode_button_styles(self, active_mode: str, enabled: bool) -> None:
        for mode, button in self.mode_buttons.items():
            if mode == active_mode and enabled:
                button.configure(
                    bg=_ACCENT,
                    fg=_ACCENT_FG,
                    activebackground=_ACCENT_HOVER,
                    activeforeground=_ACCENT_FG,
                    relief="raised",
                    bd=1,
                    highlightthickness=1,
                    highlightbackground=_ACCENT,
                    cursor="hand2",
                )
            else:
                button.configure(
                    bg=_PANEL_ALT,
                    fg=_SUBTEXT if enabled else _TEXT,
                    activebackground=_PANEL_ALT,
                    activeforeground=_TEXT,
                    relief="flat",
                    bd=0,
                    highlightthickness=1,
                    highlightbackground=_BORDER,
                    cursor="hand2" if enabled else "arrow",
                )

    def _sync_tun_button(self, tun_enabled: bool, api_ready: bool) -> None:
        state = tk.NORMAL if api_ready else tk.DISABLED
        self.tun_btn.configure(state=state)
        if tun_enabled and api_ready:
            self.tun_btn.configure(
                text="TUN: 开",
                bg=_ACCENT,
                fg=_ACCENT_FG,
                activebackground=_ACCENT_HOVER,
                activeforeground=_ACCENT_FG,
                highlightbackground=_ACCENT,
            )
        else:
            self.tun_btn.configure(
                text="TUN: 关",
                bg=_PANEL_ALT,
                fg=_SUBTEXT if api_ready else _TEXT,
                activebackground=_PANEL_ALT,
                activeforeground=_TEXT,
                highlightbackground=_BORDER,
            )

    def _on_resize(self, _event=None) -> None:
        self._update_wrap_labels()
        self._layout_proxy_section()

    def _on_content_configure(self, _event=None) -> None:
        if self._canvas is None:
            return
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            return
        self._update_wrap_labels()

    def _on_canvas_configure(self, event=None) -> None:
        if self._canvas is None or self._canvas_window is None or event is None:
            return
        try:
            self._canvas.itemconfigure(self._canvas_window, width=event.width)
        except tk.TclError:
            return
        self._update_wrap_labels()

    def _on_mousewheel(self, event) -> None:
        if self._canvas is None:
            return
        try:
            if getattr(event, "num", None) == 4:
                delta = -3
            elif getattr(event, "num", None) == 5:
                delta = 3
            else:
                raw_delta = getattr(event, "delta", 0)
                if raw_delta == 0:
                    return
                delta = -3 if raw_delta > 0 else 3
            self._canvas.yview_scroll(delta, "units")
        except tk.TclError:
            pass

    def _update_wrap_labels(self) -> None:
        available_width = self.win.winfo_width()
        if self._canvas is not None:
            try:
                canvas_width = self._canvas.winfo_width()
                if canvas_width > 1:
                    available_width = canvas_width
            except tk.TclError:
                pass
        wrap = max(320, available_width - 80)
        for label in self._wrap_labels:
            try:
                label.configure(wraplength=wrap)
            except tk.TclError:
                pass

    def _close(self) -> None:
        global _active_panel
        _active_panel = None
        if self._refresh_job is not None:
            try:
                self.win.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def lift(self) -> None:
        self.win.lift()

    def focus_force(self) -> None:
        self.win.focus_force()
