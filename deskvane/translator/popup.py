from __future__ import annotations

import math
import tkinter as tk
import unicodedata

from ..ui.ui_theme import ACCENT, BORDER, CARD, CARD_ALT, SUBTEXT, TEXT, button as themed_button, make_font


def clamp_popup_position(
    pointer_x: int,
    pointer_y: int,
    popup_width: int,
    popup_height: int,
    screen_x: int,
    screen_y: int,
    screen_width: int,
    screen_height: int,
    offset_x: int = 18,
    offset_y: int = 20,
    margin: int = 12,
) -> tuple[int, int]:
    min_x = screen_x + margin
    min_y = screen_y + margin
    max_x = max(min_x, screen_x + screen_width - popup_width - margin)
    max_y = max(min_y, screen_y + screen_height - popup_height - margin)
    x = min(max_x, max(min_x, pointer_x + offset_x))
    y = min(max_y, max(min_y, pointer_y + offset_y))
    return x, y


def detect_resize_region(
    local_x: int,
    local_y: int,
    width: int,
    height: int,
    edge_margin: int = 10,
) -> str | None:
    left = local_x <= edge_margin
    right = local_x >= width - edge_margin
    top = local_y <= edge_margin
    bottom = local_y >= height - edge_margin

    if top and left:
        return "nw"
    if top and right:
        return "ne"
    if bottom and left:
        return "sw"
    if bottom and right:
        return "se"
    if left:
        return "w"
    if right:
        return "e"
    if top:
        return "n"
    if bottom:
        return "s"
    return None


def clamp_window_position(
    window_x: int,
    window_y: int,
    popup_width: int,
    popup_height: int,
    screen_x: int,
    screen_y: int,
    screen_width: int,
    screen_height: int,
    margin: int = 12,
) -> tuple[int, int]:
    min_x = screen_x + margin
    min_y = screen_y + margin
    max_x = max(min_x, screen_x + screen_width - popup_width - margin)
    max_y = max(min_y, screen_y + screen_height - popup_height - margin)
    return min(max_x, max(min_x, window_x)), min(max_y, max(min_y, window_y))


class TranslationPopup:
    def __init__(self, root: tk.Tk, on_copy: callable | None = None) -> None:
        self.root = root
        self._on_copy = on_copy
        self.edge_margin = 10
        self.min_width = 180
        self.min_height = 136
        self.padding_x = 14
        self.padding_y = 12
        self.container_border_width = 1
        self.topbar_padding_x = 14
        self.topbar_padding_y = (12, 8)
        self.body_outer_padding_x = 6
        self.body_outer_padding_y = (0, 8)
        self.scrollbar_width = 12
        self.min_font_size = 10
        self.default_font_size = 15
        self.max_font_size = 18
        self._drag_origin: tuple[int, int] | None = None
        self._window_origin: tuple[int, int, int, int] | None = None
        self._interaction_mode: str | None = None
        self._resize_region: str | None = None
        self._saved_bounds: tuple[int, int, int, int] | None = None
        self._layout_after_id: str | None = None
        self._pending_layout: tuple[int, int] | None = None
        self._current_text = ""
        self._rendered_text = ""
        self._paragraph_weights: tuple[float, ...] = (1.0,)
        self._current_font_size = 13
        self._body_scrollbar_visible = False

        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg=CARD)
        try:
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            self.window.attributes("-alpha", 0.98)
        except tk.TclError:
            pass

        self.body_font = make_font(13)
        self.measure_font = self.body_font.copy()
        self.measure_var = tk.StringVar(value="")
        self.measure_label = tk.Label(
            root,
            textvariable=self.measure_var,
            font=self.measure_font,
            bg=CARD,
            fg=TEXT,
            justify="left",
            anchor="nw",
            padx=self.padding_x,
            pady=self.padding_y,
            wraplength=360,
            bd=0,
            highlightthickness=0,
        )

        self.container = tk.Frame(
            self.window,
            bg=CARD,
            bd=0,
            highlightthickness=self.container_border_width,
            highlightbackground=BORDER,
        )
        self.container.pack(fill="both", expand=True)

        self.topbar = tk.Frame(self.container, bg=CARD)
        self.topbar.pack(fill="x", padx=self.topbar_padding_x, pady=self.topbar_padding_y)
        title_box = tk.Frame(self.topbar, bg=CARD)
        title_box.pack(side=tk.LEFT, fill="x", expand=True)
        tk.Label(
            title_box,
            text="翻译结果",
            bg=CARD,
            fg=TEXT,
            font=make_font(10, weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="可拖动 · 双击关闭",
            bg=CARD,
            fg=SUBTEXT,
            font=make_font(9),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        self._copy_btn = themed_button(
            self.topbar,
            "复制",
            self._copy_text,
            variant="secondary",
            compact=True,
            font=make_font(9, weight="bold"),
        )
        self._copy_btn.pack(side=tk.RIGHT)
        self._copy_after_id: str | None = None

        self.body_frame = tk.Frame(self.container, bg=CARD, bd=0, highlightthickness=0)
        self.body_frame.pack(
            fill="both",
            expand=True,
            padx=self.body_outer_padding_x,
            pady=self.body_outer_padding_y,
        )
        self.body_text = tk.Text(
            self.body_frame,
            wrap=tk.CHAR,
            height=1,
            width=1,
            bg=CARD,
            fg=TEXT,
            font=self.body_font,
            padx=self.padding_x,
            pady=self.padding_y,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor="fleur",
            state=tk.DISABLED,
        )
        self.body_scrollbar = tk.Scrollbar(
            self.body_frame,
            orient=tk.VERTICAL,
            command=self.body_text.yview,
            width=self.scrollbar_width,
        )
        self.body_text.configure(yscrollcommand=self.body_scrollbar.set)
        self.body_text.pack(side=tk.LEFT, fill="both", expand=True)

        for widget in (self.window, self.container, self.topbar, title_box, self.body_frame, self.body_text):
            widget.bind("<Motion>", self._update_cursor, add="+")
            widget.bind("<ButtonPress-1>", self._start_interaction, add="+")
            widget.bind("<B1-Motion>", self._continue_interaction, add="+")
            widget.bind("<ButtonRelease-1>", self._end_interaction, add="+")
            widget.bind("<Double-Button-1>", self._close_on_double_click, add="+")
        self.body_text.bind("<MouseWheel>", self._on_body_mousewheel, add="+")
        self.body_text.bind("<Button-4>", self._on_body_mousewheel, add="+")
        self.body_text.bind("<Button-5>", self._on_body_mousewheel, add="+")

    def show(
        self,
        text: str,
        pointer_x: int | None,
        pointer_y: int | None,
        width_px: int,
    ) -> None:
        was_visible = bool(self.window.winfo_viewable())
        if pointer_x is None or pointer_y is None:
            pointer_x, pointer_y = self._pointer_position()
        if text != self._current_text:
            self._current_text = text
            self._paragraph_weights = self._build_paragraph_weights(text)

        self.window.deiconify()
        self.window.lift()

        screen_x, screen_y, screen_width, screen_height = self._screen_bounds()
        if was_visible:
            x = self.window.winfo_x()
            y = self.window.winfo_y()
            popup_width = max(self.min_width, self.window.winfo_width())
            popup_height = max(self.min_height, self.window.winfo_height())
            popup_width = min(popup_width, max(self.min_width, screen_width - 24))
            popup_height = min(popup_height, max(self.min_height, screen_height - 24))
            self._apply_text_layout(popup_width, popup_height, precise=True)
        else:
            popup_width = self._popup_width_for_text_width(width_px)
            popup_width = min(popup_width, max(self.min_width, screen_width - 24))
            popup_height = self._initial_popup_height(popup_width, screen_height)
            popup_height = self._fit_initial_height(
                popup_width=popup_width,
                popup_height=popup_height,
                screen_height=screen_height,
            )
            x, y = clamp_popup_position(
                pointer_x=pointer_x,
                pointer_y=pointer_y,
                popup_width=popup_width,
                popup_height=popup_height,
                screen_x=screen_x,
                screen_y=screen_y,
                screen_width=screen_width,
                screen_height=screen_height,
            )

        popup_width = min(popup_width, max(self.min_width, screen_width - 24))
        popup_height = min(popup_height, max(self.min_height, screen_height - 24))
        x, y = clamp_window_position(
            window_x=x,
            window_y=y,
            popup_width=popup_width,
            popup_height=popup_height,
            screen_x=screen_x,
            screen_y=screen_y,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        if not was_visible:
            self._apply_text_layout(
                popup_width,
                popup_height,
                precise=True,
                font_ceiling=self.default_font_size,
            )
        self.window.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
        self._saved_bounds = (x, y, popup_width, popup_height)

    def hide(self) -> None:
        self._cancel_scheduled_layout()
        self._cancel_copy_feedback()
        self._drag_origin = None
        self._window_origin = None
        self._interaction_mode = None
        self._resize_region = None
        self._saved_bounds = None
        self.window.withdraw()

    def _copy_text(self) -> None:
        """Copy current translation text to clipboard with visual feedback."""
        if not self._current_text:
            return
        try:
            if self._on_copy is not None:
                copied = self._on_copy(self._current_text)
                if copied is False:
                    raise tk.TclError("clipboard write failed")
            else:
                self.root.clipboard_clear()
                self.root.clipboard_append(self._current_text)
                self.root.update_idletasks()
        except tk.TclError:
            return
        self._copy_btn.configure(text="已复制")
        self._cancel_copy_feedback()
        self._copy_after_id = self.root.after(
            1200, lambda: self._copy_btn.configure(text="复制")
        )

    def _cancel_copy_feedback(self) -> None:
        if self._copy_after_id:
            try:
                self.root.after_cancel(self._copy_after_id)
            except tk.TclError:
                pass
            self._copy_after_id = None

    def _pointer_position(self) -> tuple[int, int]:
        try:
            return self.root.winfo_pointerxy()
        except tk.TclError:
            return 48, 48

    def _screen_bounds(self) -> tuple[int, int, int, int]:
        return (
            self.root.winfo_vrootx(),
            self.root.winfo_vrooty(),
            self.root.winfo_vrootwidth() or self.root.winfo_screenwidth(),
            self.root.winfo_vrootheight() or self.root.winfo_screenheight(),
        )

    def _container_border(self) -> int:
        try:
            return int(self.container.cget("highlightthickness") or 0)
        except (tk.TclError, ValueError):
            return self.container_border_width

    def _vertical_chrome_height(self) -> int:
        try:
            self.root.update_idletasks()
            topbar_height = self.topbar.winfo_reqheight()
        except tk.TclError:
            topbar_height = 40
        return (
            topbar_height
            + sum(self.topbar_padding_y)
            + sum(self.body_outer_padding_y)
            + (self._container_border() * 2)
        )

    def _body_horizontal_overhead(self, reserve_scrollbar: bool = False) -> int:
        scrollbar = self.scrollbar_width if reserve_scrollbar else 0
        return (
            (self._container_border() * 2)
            + (self.body_outer_padding_x * 2)
            + (self.padding_x * 2)
            + scrollbar
        )

    def _body_wrap_width(self, popup_width: int, reserve_scrollbar: bool = False) -> int:
        return max(80, popup_width - self._body_horizontal_overhead(reserve_scrollbar))

    def _popup_width_for_text_width(self, text_width: int) -> int:
        return max(self.min_width, text_width + self._body_horizontal_overhead())

    def _set_body_text(self) -> None:
        if self._rendered_text == self._current_text:
            return
        try:
            self.body_text.configure(state=tk.NORMAL)
            self.body_text.delete("1.0", tk.END)
            self.body_text.insert("1.0", self._current_text)
            self.body_text.configure(state=tk.DISABLED)
            self.body_text.yview_moveto(0)
        except tk.TclError:
            return
        self._rendered_text = self._current_text

    def _set_body_scrollbar_visible(self, visible: bool) -> None:
        if visible == self._body_scrollbar_visible:
            return
        if visible:
            self.body_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.body_scrollbar.pack_forget()
        self._body_scrollbar_visible = visible

    def _on_body_mousewheel(self, event: tk.Event) -> str | None:
        if not self._body_scrollbar_visible:
            return None
        if getattr(event, "num", None) == 4:
            delta = -3
        elif getattr(event, "num", None) == 5:
            delta = 3
        else:
            delta = -1 * int(getattr(event, "delta", 0) / 120)
        if delta:
            self.body_text.yview_scroll(delta, "units")
        return "break"

    def _start_interaction(self, event: tk.Event) -> str:
        width = max(self.min_width, self.window.winfo_width())
        height = max(self.min_height, self.window.winfo_height())
        local_x = event.x_root - self.window.winfo_x()
        local_y = event.y_root - self.window.winfo_y()
        self._resize_region = detect_resize_region(
            local_x=local_x,
            local_y=local_y,
            width=width,
            height=height,
            edge_margin=self.edge_margin,
        )
        self._drag_origin = (event.x_root, event.y_root)
        self._window_origin = (
            self.window.winfo_x(),
            self.window.winfo_y(),
            width,
            height,
        )
        self._interaction_mode = "resize" if self._resize_region else "move"
        return "break"

    def _continue_interaction(self, event: tk.Event) -> str:
        if not self._drag_origin or not self._window_origin:
            return "break"

        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]
        if self._interaction_mode == "resize" and self._resize_region:
            x, y, width, height = self._resize_bounds(dx, dy)
            self.window.geometry(f"{width}x{height}+{x}+{y}")
            self._saved_bounds = (x, y, width, height)
            self._schedule_layout(width, height)
            return "break"

        screen_x, screen_y, screen_width, screen_height = self._screen_bounds()
        x, y = clamp_window_position(
            window_x=self._window_origin[0] + dx,
            window_y=self._window_origin[1] + dy,
            popup_width=self._window_origin[2],
            popup_height=self._window_origin[3],
            screen_x=screen_x,
            screen_y=screen_y,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        self.window.geometry(
            f"{self._window_origin[2]}x{self._window_origin[3]}+{x}+{y}"
        )
        self._saved_bounds = (x, y, self._window_origin[2], self._window_origin[3])
        return "break"

    def _end_interaction(self, _event: tk.Event) -> str:
        mode = self._interaction_mode
        self._drag_origin = None
        self._window_origin = None
        self._interaction_mode = None
        self._resize_region = None
        if mode == "resize" and self.window.winfo_viewable():
            self._cancel_scheduled_layout()
            self._apply_text_layout(
                max(self.min_width, self.window.winfo_width()),
                max(self.min_height, self.window.winfo_height()),
                precise=True,
            )
        return "break"

    def _close_on_double_click(self, _event: tk.Event) -> str:
        self.hide()
        return "break"

    def _update_cursor(self, event: tk.Event) -> str:
        width = max(self.min_width, self.window.winfo_width())
        height = max(self.min_height, self.window.winfo_height())
        local_x = event.x_root - self.window.winfo_x()
        local_y = event.y_root - self.window.winfo_y()
        region = detect_resize_region(
            local_x=local_x,
            local_y=local_y,
            width=width,
            height=height,
            edge_margin=self.edge_margin,
        )
        cursor = {
            "n": "sb_v_double_arrow",
            "s": "sb_v_double_arrow",
            "e": "sb_h_double_arrow",
            "w": "sb_h_double_arrow",
            "ne": "top_right_corner",
            "sw": "bottom_left_corner",
            "nw": "top_left_corner",
            "se": "bottom_right_corner",
        }.get(region, "fleur")
        try:
            self.window.configure(cursor=cursor)
            self.container.configure(cursor=cursor)
            self.body_frame.configure(cursor=cursor)
            self.body_text.configure(cursor=cursor)
        except tk.TclError:
            pass
        return "break"

    def _resize_bounds(self, dx: int, dy: int) -> tuple[int, int, int, int]:
        if not self._window_origin or not self._resize_region:
            return (
                self.window.winfo_x(),
                self.window.winfo_y(),
                max(self.min_width, self.window.winfo_width()),
                max(self.min_height, self.window.winfo_height()),
            )

        orig_x, orig_y, orig_width, orig_height = self._window_origin
        x = orig_x
        y = orig_y
        width = orig_width
        height = orig_height

        if "e" in self._resize_region:
            width = orig_width + dx
        if "s" in self._resize_region:
            height = orig_height + dy
        if "w" in self._resize_region:
            x = orig_x + dx
            width = orig_width - dx
        if "n" in self._resize_region:
            y = orig_y + dy
            height = orig_height - dy

        width = max(self.min_width, width)
        height = max(self.min_height, height)

        screen_x, screen_y, screen_width, screen_height = self._screen_bounds()
        max_width = max(self.min_width, screen_width - 24)
        max_height = max(self.min_height, screen_height - 24)
        width = min(width, max_width)
        height = min(height, max_height)

        if "w" in self._resize_region:
            x = orig_x + (orig_width - width)
        if "n" in self._resize_region:
            y = orig_y + (orig_height - height)

        x, y = clamp_window_position(
            window_x=x,
            window_y=y,
            popup_width=width,
            popup_height=height,
            screen_x=screen_x,
            screen_y=screen_y,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        return x, y, width, height

    def _apply_text_layout(
        self,
        popup_width: int,
        popup_height: int,
        precise: bool = False,
        font_ceiling: int | None = None,
    ) -> None:
        self._set_body_text()
        font_size = self._best_font_size(
            popup_width,
            popup_height,
            precise=precise,
            font_ceiling=font_ceiling,
        )
        if font_size != self._current_font_size:
            self.body_font.configure(size=font_size)
            self._current_font_size = font_size
        overflowing = self._measure_popup_height(font_size, popup_width) > popup_height
        self._set_body_scrollbar_visible(overflowing)

    def _initial_popup_height(self, popup_width: int, screen_height: int) -> int:
        max_height = max(self.min_height, screen_height // 3)
        return min(
            max(self.min_height, self._measure_popup_height(self.default_font_size, popup_width)),
            max_height,
        )

    def _fit_initial_height(
        self,
        popup_width: int,
        popup_height: int,
        screen_height: int,
    ) -> int:
        max_height = max(self.min_height, screen_height - 24)
        return min(max(self.min_height, popup_height), max_height)

    def _best_font_size(
        self,
        popup_width: int,
        popup_height: int,
        precise: bool = False,
        font_ceiling: int | None = None,
    ) -> int:
        content_width = self._body_wrap_width(popup_width)
        content_height = max(1, popup_height - self._vertical_chrome_height())
        upper = max(self.min_font_size, min(self.max_font_size, font_ceiling or self.max_font_size))
        if not precise:
            for font_size in range(upper, self.min_font_size - 1, -1):
                if self._estimate_text_height(font_size, content_width) <= content_height:
                    return font_size
            return self.min_font_size

        low = self.min_font_size
        high = upper
        best = self.min_font_size
        while low <= high:
            font_size = (low + high) // 2
            if self._measure_popup_height(font_size, popup_width) <= popup_height:
                best = font_size
                low = font_size + 1
            else:
                high = font_size - 1
        return best

    def _measure_popup_height(
        self,
        font_size: int,
        popup_width: int,
        reserve_scrollbar: bool = False,
    ) -> int:
        content_width = self._body_wrap_width(popup_width, reserve_scrollbar=reserve_scrollbar)
        if self.measure_var.get() != self._current_text:
            self.measure_var.set(self._current_text)
        self.measure_font.configure(size=font_size)
        self.measure_label.configure(wraplength=content_width)
        try:
            self.root.update_idletasks()
        except tk.TclError:
            return self._estimate_text_height(font_size, content_width) + self._vertical_chrome_height()
        return max(
            self.min_height,
            self.measure_label.winfo_reqheight() + self._vertical_chrome_height(),
        )

    def _estimate_text_height(self, font_size: int, content_width: int) -> int:
        try:
            self.measure_font.configure(size=font_size)
            line_height = self.measure_font.metrics("linespace")
        except tk.TclError:
            line_height = max(font_size + 6, int(font_size * 1.65))
        line_count = self._estimate_line_count(font_size, content_width)
        return max(line_height, line_count * line_height) + (self.padding_y * 2)

    def _estimate_line_count(self, font_size: int, content_width: int) -> int:
        units_per_line = max(4.0, content_width / max(6.0, font_size * 0.92))
        return max(
            1,
            sum(max(1, math.ceil(weight / units_per_line)) for weight in self._paragraph_weights),
        )

    def _build_paragraph_weights(self, text: str) -> tuple[float, ...]:
        paragraphs = text.splitlines() or [text]
        weights = []
        for paragraph in paragraphs:
            if not paragraph:
                weights.append(1.0)
                continue
            weights.append(sum(self._char_weight(char) for char in paragraph))
        return tuple(weights) or (1.0,)

    @staticmethod
    def _char_weight(char: str) -> float:
        if char.isspace():
            return 0.35
        east = unicodedata.east_asian_width(char)
        if east in {"W", "F"}:
            return 1.0
        if east == "A":
            return 0.85
        return 0.55

    def _schedule_layout(self, popup_width: int, popup_height: int) -> None:
        self._pending_layout = (popup_width, popup_height)
        if self._layout_after_id:
            return
        self._layout_after_id = self.root.after(16, self._flush_scheduled_layout)

    def _flush_scheduled_layout(self) -> None:
        self._layout_after_id = None
        if not self._pending_layout:
            return
        popup_width, popup_height = self._pending_layout
        self._pending_layout = None
        self._apply_text_layout(popup_width, popup_height)

    def _cancel_scheduled_layout(self) -> None:
        if not self._layout_after_id:
            self._pending_layout = None
            return
        try:
            self.root.after_cancel(self._layout_after_id)
        except tk.TclError:
            pass
        self._layout_after_id = None
        self._pending_layout = None
