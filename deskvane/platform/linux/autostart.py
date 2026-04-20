from __future__ import annotations

import os
from pathlib import Path

from ..base import AutostartService


class LinuxAutostartService(AutostartService):
    def __init__(
        self,
        autostart_dir: Path | None = None,
        entry_name: str = "deskvane.desktop",
        command: str = "deskvane",
    ) -> None:
        env_dir = os.environ.get("DESKVANE_AUTOSTART_DIR")
        self._autostart_dir = autostart_dir or Path(env_dir) if env_dir else autostart_dir
        if self._autostart_dir is None:
            self._autostart_dir = Path.home() / ".config" / "autostart"
        self._entry_name = entry_name
        self._command = command

    def is_supported(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return self._entry_path().exists()

    def enable(self, command: str | None = None) -> bool:
        entry_path = self._entry_path()
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        exec_command = command or self._command
        entry_path.write_text(
            "\n".join(
                (
                    "[Desktop Entry]",
                    "Type=Application",
                    "Name=DeskVane",
                    f"Exec={exec_command}",
                    "X-GNOME-Autostart-enabled=true",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return True

    def disable(self) -> bool:
        entry_path = self._entry_path()
        if not entry_path.exists():
            return False
        entry_path.unlink()
        return True

    def _entry_path(self) -> Path:
        return self._autostart_dir / self._entry_name
