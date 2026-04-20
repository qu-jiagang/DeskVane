"""Floating pinned image window — borderless, draggable, zoomable."""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageTk

from .ui_theme import BG, BORDER, CARD, SUBTEXT, TEXT, button as themed_button, make_font


class PinnedImage:
    """Floating borderless window that displays an image. Supports dragging and zooming."""

    def __init__(self, root: tk.Tk, image: Image.Image, x: int, y: int, on_close) -> None:
        self.root = root
        self.original_image = image
        self.on_close = on_close

        self.scale = 1.0
        self.min_scale = 0.1
        self.max_scale = 5.0

        self.border_width = 1

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.configure(bg=BG)
        try:
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(
            self.window,
            highlightthickness=self.border_width,
            highlightbackground=BORDER,
            background=CARD,
            bd=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.chrome = tk.Frame(
            self.window,
            bg=CARD,
            padx=10,
            pady=8,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        title_row = tk.Frame(self.chrome, bg=CARD)
        title_row.pack(fill=tk.X)
        tk.Label(
            title_row,
            text="已固定",
            bg=CARD,
            fg=TEXT,
            font=make_font(9, weight="bold"),
        ).pack(side=tk.LEFT)
        themed_button(
            title_row,
            "关闭",
            self.destroy,
            variant="secondary",
            compact=True,
            font=make_font(9, weight="bold"),
        ).pack(side=tk.RIGHT)
        tk.Label(
            self.chrome,
            text="拖动 · 滚轮缩放 · 双击关闭",
            bg=CARD,
            fg=SUBTEXT,
            font=make_font(8),
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))
        self.chrome.place(relx=1.0, x=-12, y=12, anchor="ne")
        self.chrome.lift()

        self._tk_image = None
        self._image_id = None
        self._chrome_after_id: str | None = None

        self._drag_start_x = 0
        self._drag_start_y = 0

        self._update_image()

        # Move window back by border_width to place image perfectly on (x, y)
        win_x = x - self.border_width
        win_y = y - self.border_width
        self.window.geometry(f"+{win_x}+{win_y}")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

        for widget in (self.window, self.canvas, self.chrome):
            widget.bind("<Enter>", self._on_hover_enter, add="+")
            widget.bind("<Leave>", self._on_hover_leave, add="+")
        self._show_chrome(autohide=True)

    def _update_image(self) -> None:
        new_width = int(self.original_image.width * self.scale)
        new_height = int(self.original_image.height * self.scale)

        if new_width < 10 or new_height < 10:
            return

        resized = self.original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(image=resized)

        total_w = new_width + self.border_width * 2
        total_h = new_height + self.border_width * 2
        self.window.geometry(f"{total_w}x{total_h}")
        self.canvas.config(width=new_width, height=new_height)

        if self._image_id is not None:
            self.canvas.delete(self._image_id)
        self._image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_image)

    def _show_chrome(self, autohide: bool = False) -> None:
        self._cancel_chrome_hide()
        self.chrome.place(relx=1.0, x=-12, y=12, anchor="ne")
        self.chrome.lift()
        if autohide:
            self._schedule_chrome_hide()

    def _hide_chrome(self) -> None:
        self._cancel_chrome_hide()
        self.chrome.place_forget()

    def _schedule_chrome_hide(self, delay_ms: int = 1800) -> None:
        self._cancel_chrome_hide()
        self._chrome_after_id = self.window.after(delay_ms, self._hide_chrome)

    def _cancel_chrome_hide(self) -> None:
        if self._chrome_after_id is None:
            return
        try:
            self.window.after_cancel(self._chrome_after_id)
        except tk.TclError:
            pass
        self._chrome_after_id = None

    def _on_hover_enter(self, _event=None) -> None:
        self._show_chrome()

    def _on_hover_leave(self, _event=None) -> None:
        self._schedule_chrome_hide(delay_ms=900)

    def _on_press(self, event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event) -> None:
        x = self.window.winfo_x() - self._drag_start_x + event.x
        y = self.window.winfo_y() - self._drag_start_y + event.y
        self.window.geometry(f"+{x}+{y}")

    def _on_double_click(self, event) -> None:
        self.destroy()

    def _on_mousewheel(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            scale_factor = 1.1
        elif event.num == 5 or event.delta < 0:
            scale_factor = 1.0 / 1.1
        else:
            return

        new_scale = self.scale * scale_factor
        if self.min_scale <= new_scale <= self.max_scale:
            win_x = self.window.winfo_x()
            win_y = self.window.winfo_y()
            pointer_x = self.window.winfo_pointerx() - win_x
            pointer_y = self.window.winfo_pointery() - win_y

            new_win_x = int(win_x + pointer_x - pointer_x * scale_factor)
            new_win_y = int(win_y + pointer_y - pointer_y * scale_factor)

            self.scale = new_scale
            self._update_image()
            self.window.geometry(f"+{new_win_x}+{new_win_y}")

    def destroy(self) -> None:
        self._cancel_chrome_hide()
        self.window.destroy()
        self.on_close(self)
