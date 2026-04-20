import tkinter as tk

import pytest
from unittest import mock

from deskvane import ui_theme
from deskvane.translator.popup import TranslationPopup


def _make_root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    return root


def test_ui_font_prefers_cjk_family_over_arial(monkeypatch) -> None:
    ui_theme._FONT_CACHE.clear()
    monkeypatch.setattr(ui_theme.tkfont, "families", lambda: ("Arial", "Noto Sans CJK SC"))

    try:
        assert ui_theme._resolve_font_family("ui") == "Noto Sans CJK SC"
    finally:
        ui_theme._FONT_CACHE.clear()


def test_translation_popup_short_text_has_full_body_height() -> None:
    root = _make_root()
    try:
        popup = TranslationPopup(root)
        popup.window.deiconify()
        popup._current_text = "这是一句短翻译结果"
        popup._paragraph_weights = popup._build_paragraph_weights(popup._current_text)

        width = popup._popup_width_for_text_width(360)
        height = popup._initial_popup_height(width, root.winfo_screenheight())
        popup._apply_text_layout(width, height, precise=True, font_ceiling=popup.default_font_size)
        popup.window.geometry(f"{width}x{height}+10+10")
        root.update()

        min_body_height = popup.body_font.metrics("linespace") + (popup.padding_y * 2)
        assert popup.body_text.winfo_height() >= min_body_height
        assert not popup._body_scrollbar_visible
        assert popup.body_text.yview() == (0.0, 1.0)
    finally:
        root.destroy()


def test_translation_popup_long_cjk_text_uses_scrollbar() -> None:
    root = _make_root()
    try:
        popup = TranslationPopup(root)
        popup.window.deiconify()
        popup._current_text = "很长的翻译结果。" * 200
        popup._paragraph_weights = popup._build_paragraph_weights(popup._current_text)

        width = popup._popup_width_for_text_width(360)
        height = popup._initial_popup_height(width, root.winfo_screenheight())
        popup._apply_text_layout(width, height, precise=True, font_ceiling=popup.default_font_size)
        popup.window.geometry(f"{width}x{height}+10+10")
        root.update()

        display_lines = popup.body_text.count("1.0", "end", "displaylines")
        assert popup._body_scrollbar_visible
        assert display_lines is not None and display_lines[0] > 1
        assert popup.body_text.yview()[1] < 1.0
    finally:
        root.destroy()


def test_translation_popup_prefers_callback_for_copy() -> None:
    root = _make_root()
    try:
        on_copy = mock.Mock(return_value=True)
        popup = TranslationPopup(root, on_copy=on_copy)
        popup._current_text = "平台文本复制"

        popup._copy_text()

        on_copy.assert_called_once_with("平台文本复制")
    finally:
        root.destroy()
