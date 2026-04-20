from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

BG = "#f3f4f8"
SIDEBAR = "#ebeef4"
CARD = "#ffffff"
CARD_ALT = "#f7f8fb"
BORDER = "#d9dde5"
TEXT = "#1b2230"
SUBTEXT = "#667085"
MUTED = "#9aa3b2"
ACCENT = "#0a84ff"
ACCENT_HOVER = "#409cff"
ACCENT_FG = "#ffffff"
SUCCESS = "#2f9e67"
WARN = "#c78300"
DANGER = "#d14d4d"

_FONT_UI_CANDIDATES = (
    "PingFang SC",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "Droid Sans Fallback",
    "SF Pro Text",
    "SF Pro Display",
    "Helvetica Neue",
    "Helvetica",
    "Arial",
)
_FONT_MONO_CANDIDATES = (
    "SF Mono",
    "Menlo",
    "Monaco",
    "Consolas",
    "DejaVu Sans Mono",
)
_FONT_CACHE: dict[str, str] = {}


def _resolve_font_family(kind: str) -> str:
    cached = _FONT_CACHE.get(kind)
    if cached:
        return cached
    candidates = _FONT_MONO_CANDIDATES if kind == "mono" else _FONT_UI_CANDIDATES
    fallback = "TkFixedFont" if kind == "mono" else "TkDefaultFont"
    try:
        families = {name.lower(): name for name in tkfont.families()}
    except tk.TclError:
        _FONT_CACHE[kind] = fallback
        return fallback
    for name in candidates:
        match = families.get(name.lower())
        if match:
            _FONT_CACHE[kind] = match
            return match
    _FONT_CACHE[kind] = fallback
    return fallback


def make_font(size: int, weight: str = "normal", mono: bool = False) -> tkfont.Font:
    return tkfont.Font(
        family=_resolve_font_family("mono" if mono else "ui"),
        size=size,
        weight=weight,
    )


def card(parent: tk.Misc, alt: bool = False, **pack_kwargs) -> tk.Frame:
    frame = tk.Frame(
        parent,
        bg=CARD_ALT if alt else CARD,
        bd=0,
        highlightbackground=BORDER,
        highlightthickness=1,
    )
    if pack_kwargs:
        frame.pack(**pack_kwargs)
    return frame


def button(
    parent: tk.Misc,
    text: str,
    command,
    *,
    variant: str = "secondary",
    compact: bool = False,
    font: tkfont.Font | None = None,
    **kwargs,
) -> tk.Button:
    styles = {
        "primary": {
            "bg": ACCENT,
            "fg": ACCENT_FG,
            "activebackground": ACCENT_HOVER,
            "activeforeground": ACCENT_FG,
            "highlightbackground": ACCENT,
            "highlightcolor": ACCENT,
        },
        "secondary": {
            "bg": CARD,
            "fg": TEXT,
            "activebackground": CARD_ALT,
            "activeforeground": TEXT,
            "highlightbackground": BORDER,
            "highlightcolor": ACCENT,
        },
        "ghost": {
            "bg": BG,
            "fg": SUBTEXT,
            "activebackground": SIDEBAR,
            "activeforeground": TEXT,
            "highlightbackground": BG,
            "highlightcolor": ACCENT,
        },
        "danger": {
            "bg": "#fff1f1",
            "fg": DANGER,
            "activebackground": "#ffe1e1",
            "activeforeground": DANGER,
            "highlightbackground": "#f4c8c8",
            "highlightcolor": DANGER,
        },
    }
    style = styles.get(variant, styles["secondary"])
    return tk.Button(
        parent,
        text=text,
        command=command,
        bd=0,
        relief="flat",
        overrelief="flat",
        cursor="hand2",
        padx=14 if compact else 18,
        pady=7 if compact else 10,
        font=font or make_font(10, weight="bold" if variant == "primary" else "normal"),
        disabledforeground=MUTED,
        highlightthickness=1,
        **style,
        **kwargs,
    )
