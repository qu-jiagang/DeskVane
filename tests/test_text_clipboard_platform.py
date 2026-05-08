from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from deskvane.features.clipboard_history.manager import ClipboardHistoryManager


def test_clipboard_history_uses_platform_text_clipboard(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "clipboard_history.json"
    monkeypatch.setattr(ClipboardHistoryManager, "_HISTORY_PATH", history_path)

    app = SimpleNamespace(
        platform_services=SimpleNamespace(
            clipboard=SimpleNamespace(
                read_text=mock.Mock(return_value="platform text"),
                write_text=mock.Mock(return_value=True),
            )
        ),
        root=SimpleNamespace(
            after=mock.Mock(),
            clipboard_get=mock.Mock(return_value="fallback text"),
            clipboard_clear=mock.Mock(),
            clipboard_append=mock.Mock(),
        ),
        config=SimpleNamespace(
            general=SimpleNamespace(
                clipboard_history_enabled=False,
                notifications_enabled=False,
            )
        ),
        notifier=SimpleNamespace(show=mock.Mock()),
    )

    manager = ClipboardHistoryManager(app)
    manager._poll_clipboard()

    assert manager.history == ["platform text"]
    app.platform_services.clipboard.read_text.assert_called_once_with("clipboard")

    manager._on_select(0)

    app.platform_services.clipboard.write_text.assert_called_once_with("platform text")
    app.root.clipboard_clear.assert_not_called()
    app.root.clipboard_append.assert_not_called()
