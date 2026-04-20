"""Full-screen transparent overlay for rubber-band area selection."""

from __future__ import annotations

import tkinter as tk

from PIL import ImageEnhance, ImageTk

from .ui_theme import ACCENT, BORDER, CARD, CARD_ALT, DANGER, SUBTEXT, TEXT, button as themed_button, make_font


class SelectionOverlay:
    """Full-screen transparent overlay for rubber-band area selection."""

    def __init__(self, background, on_done, on_cancel, interactive=False) -> None:
        self._bg_image = background
        self._on_done = on_done
        self._on_cancel = on_cancel
        self._interactive = interactive

        self._state = "IDLE"
        self._start_x = None
        self._start_y = None
        self._end_x = None
        self._end_y = None

        self._drag_start_x = None
        self._drag_start_y = None
        self._drag_zone = None
        self._toolbar = None

        self._root = tk.Toplevel()
        self._root.attributes("-fullscreen", True)
        self._root.attributes("-topmost", True)
        self._root.configure(cursor="crosshair", background=CARD)
        self._root.overrideredirect(True)

        dim_bg = ImageEnhance.Brightness(background).enhance(0.62)
        self._tk_dim_bg = ImageTk.PhotoImage(image=dim_bg)
        self._tk_bright_bg = ImageTk.PhotoImage(image=background)

        self._canvas = tk.Canvas(self._root, width=background.width, height=background.height, highlightthickness=0, bd=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_dim_bg)

        self._cutout = tk.Canvas(self._canvas, highlightthickness=1, highlightbackground=ACCENT, bd=0)
        self._cutout.place(x=-1000, y=-1000, width=0, height=0)
        self._cutout.create_image(0, 0, anchor=tk.NW, image=self._tk_bright_bg, tags="bright_img")

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Button-3>", lambda e: self._cancel())
        self._canvas.bind("<Motion>", self._on_hover)

        self._cutout.bind("<ButtonPress-1>", self._on_press)
        self._cutout.bind("<B1-Motion>", self._on_drag)
        self._cutout.bind("<ButtonRelease-1>", self._on_release)
        self._cutout.bind("<Button-3>", lambda e: self._cancel())
        self._cutout.bind("<Motion>", self._on_hover)

        self._root.bind("<Escape>", lambda e: self._cancel())
        self._root.focus_force()
        self._root.grab_set()

    def _cancel(self) -> None:
        self._root.grab_release()
        self._root.destroy()
        self._on_cancel()

    def _get_hover_zone(self, x, y):
        if self._state not in ("EDITING", "MOVING", "RESIZING"): return None
        if self._start_x is None or self._end_x is None: return None
        min_x, max_x = min(self._start_x, self._end_x), max(self._start_x, self._end_x)
        min_y, max_y = min(self._start_y, self._end_y), max(self._start_y, self._end_y)
        m = 8
        if not (min_x - m <= x <= max_x + m and min_y - m <= y <= max_y + m): return None
        if abs(x - min_x) <= m and abs(y - min_y) <= m: return "NW"
        if abs(x - max_x) <= m and abs(y - max_y) <= m: return "SE"
        if abs(x - min_x) <= m and abs(y - max_y) <= m: return "SW"
        if abs(x - max_x) <= m and abs(y - min_y) <= m: return "NE"
        if abs(x - min_x) <= m: return "W"
        if abs(x - max_x) <= m: return "E"
        if abs(y - min_y) <= m: return "N"
        if abs(y - max_y) <= m: return "S"
        return "C"

    def _on_hover(self, event):
        zone = self._get_hover_zone(event.x_root, event.y_root)
        if zone in ("NW", "SE"): self._root.configure(cursor="size_nw_se")
        elif zone in ("NE", "SW"): self._root.configure(cursor="size_ne_sw")
        elif zone in ("N", "S"): self._root.configure(cursor="sb_v_double_arrow")
        elif zone in ("E", "W"): self._root.configure(cursor="sb_h_double_arrow")
        elif zone == "C": self._root.configure(cursor="fleur")
        else: self._root.configure(cursor="crosshair")

    def _show_toolbar(self):
        if self._toolbar:
            self._toolbar.destroy()
        self._toolbar = tk.Frame(
            self._root,
            bg=CARD,
            padx=12,
            pady=12,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        title = tk.Frame(self._toolbar, bg=CARD)
        title.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            title,
            text="选区",
            bg=CARD,
            fg=TEXT,
            font=make_font(10, weight="bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            title,
            text="调整后再选择处理方式。",
            bg=CARD,
            fg=SUBTEXT,
            font=make_font(9),
        ).pack(side=tk.LEFT, padx=(8, 0))

        actions = tk.Frame(self._toolbar, bg=CARD)
        actions.pack(fill=tk.X)
        themed_button(
            actions,
            "取消",
            self._cancel,
            variant="danger",
            compact=True,
            font=make_font(9, weight="bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        themed_button(
            actions,
            "固定",
            lambda: self._finish_interactive("pin"),
            variant="secondary",
            compact=True,
            font=make_font(9, weight="bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        themed_button(
            actions,
            "保存",
            lambda: self._finish_interactive("save"),
            variant="secondary",
            compact=True,
            font=make_font(9, weight="bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        themed_button(
            actions,
            "完成",
            lambda: self._finish_interactive("done"),
            variant="primary",
            compact=True,
            font=make_font(9, weight="bold"),
        ).pack(side=tk.LEFT)

        min_x, max_x = min(self._start_x, self._end_x), max(self._start_x, self._end_x)
        min_y, max_y = min(self._start_y, self._end_y), max(self._start_y, self._end_y)
        self._toolbar.update_idletasks()
        toolbar_x = max_x - self._toolbar.winfo_reqwidth()
        toolbar_y = max_y + 10
        if toolbar_y > self._root.winfo_screenheight() - self._toolbar.winfo_reqheight() - 10:
            toolbar_y = max_y - self._toolbar.winfo_reqheight() - 10
        if toolbar_x < 10: toolbar_x = 10
        self._toolbar.place(x=toolbar_x, y=toolbar_y)
        self._toolbar.lift()

    def _hide_toolbar(self):
        if self._toolbar:
            self._toolbar.destroy()
            self._toolbar = None

    def _finish_interactive(self, action: str):
        self._root.grab_release()
        self._root.destroy()
        min_x, max_x = min(self._start_x, self._end_x), max(self._start_x, self._end_x)
        min_y, max_y = min(self._start_y, self._end_y), max(self._start_y, self._end_y)
        self._on_done((min_x, min_y, max_x, max_y), action)

    def _on_press(self, event) -> None:
        abs_x, abs_y = event.x_root, event.y_root
        if self._state == "EDITING":
            zone = self._get_hover_zone(abs_x, abs_y)
            if zone:
                self._state = "MOVING" if zone == "C" else "RESIZING"
                self._drag_zone = zone
                self._drag_start_x, self._drag_start_y = abs_x, abs_y
                self._hide_toolbar()
                return
            else:
                self._hide_toolbar()
                self._state = "DRAWING"
                self._start_x, self._start_y = abs_x, abs_y
                self._end_x, self._end_y = abs_x, abs_y
                self._update_cutout(abs_x, abs_y, abs_x, abs_y)
                return

        self._state = "DRAWING"
        self._start_x, self._start_y = abs_x, abs_y
        self._end_x, self._end_y = abs_x, abs_y
        self._update_cutout(abs_x, abs_y, abs_x, abs_y)

    def _on_drag(self, event) -> None:
        abs_x, abs_y = event.x_root, event.y_root
        if self._state in ("IDLE", "DRAWING"):
            self._state = "DRAWING"
            if self._start_x is None: self._start_x, self._start_y = abs_x, abs_y
            self._end_x, self._end_y = abs_x, abs_y
            self._update_cutout(self._start_x, self._start_y, self._end_x, self._end_y)
        elif self._state == "MOVING":
            dx = abs_x - self._drag_start_x
            dy = abs_y - self._drag_start_y
            self._start_x += dx
            self._end_x += dx
            self._start_y += dy
            self._end_y += dy
            self._drag_start_x, self._drag_start_y = abs_x, abs_y
            self._update_cutout(self._start_x, self._start_y, self._end_x, self._end_y)
        elif self._state == "RESIZING":
            min_x, max_x = min(self._start_x, self._end_x), max(self._start_x, self._end_x)
            min_y, max_y = min(self._start_y, self._end_y), max(self._start_y, self._end_y)
            dx = abs_x - self._drag_start_x
            dy = abs_y - self._drag_start_y
            if "N" in self._drag_zone: min_y += dy
            if "S" in self._drag_zone: max_y += dy
            if "W" in self._drag_zone: min_x += dx
            if "E" in self._drag_zone: max_x += dx
            if min_x > max_x: min_x, max_x = max_x, min_x
            if min_y > max_y: min_y, max_y = max_y, min_y
            self._start_x, self._start_y = min_x, min_y
            self._end_x, self._end_y = max_x, max_y
            self._drag_start_x, self._drag_start_y = abs_x, abs_y
            self._update_cutout(self._start_x, self._start_y, self._end_x, self._end_y)

    def _update_cutout(self, x1, y1, x2, y2) -> None:
        if x1 is None or x2 is None: return
        min_x, max_x = min(x1, x2), max(x1, x2)
        min_y, max_y = min(y1, y2), max(y1, y2)
        w, h = max_x - min_x, max_y - min_y
        if w > 0 and h > 0:
            self._cutout.place(x=min_x, y=min_y, width=w, height=h)
            self._cutout.coords("bright_img", -min_x, -min_y)
        else:
            self._cutout.place(x=-1000, y=-1000, width=0, height=0)

    def _on_release(self, event) -> None:
        if self._state in ("IDLE", "DRAWING"):
            if self._start_x is None:
                self._on_cancel()
                return
            self._end_x, self._end_y = event.x_root, event.y_root
            x1 = min(self._start_x, self._end_x)
            y1 = min(self._start_y, self._end_y)
            x2 = max(self._start_x, self._end_x)
            y2 = max(self._start_y, self._end_y)
            if (x2 - x1) < 2 or (y2 - y1) < 2:
                self._on_cancel()
                return
            if self._interactive:
                self._state = "EDITING"
                self._start_x, self._start_y = x1, y1
                self._end_x, self._end_y = x2, y2
                self._show_toolbar()
            else:
                self._root.grab_release()
                self._root.destroy()
                self._on_done((x1, y1, x2, y2), None)
        elif self._state in ("MOVING", "RESIZING"):
            self._state = "EDITING"
            self._show_toolbar()
