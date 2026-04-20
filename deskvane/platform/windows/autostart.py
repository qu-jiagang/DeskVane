from __future__ import annotations

import os
from pathlib import Path

from ..base import AutostartService


class WindowsAutostartService(AutostartService):
    def __init__(
        self,
        startup_dir: Path | None = None,
        entry_name: str = "DeskVane.cmd",
        command: str = "deskvane",
    ) -> None:
        env_dir = os.environ.get("DESKVANE_WINDOWS_STARTUP_DIR")
        self._startup_dir = startup_dir or Path(env_dir) if env_dir else startup_dir
        if self._startup_dir is None:
            appdata = os.environ.get("APPDATA")
            base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
            self._startup_dir = base_dir / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        self._entry_name = entry_name
        self._command = command

    def is_supported(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return self._entry_path().exists()

    def enable(self, command: str | None = None) -> bool:
        entry_path = self._entry_path()
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        startup_command = command or self._command
        entry_path.write_text(f"@echo off\r\n{startup_command}\r\n", encoding="utf-8")
        return True

    def disable(self) -> bool:
        entry_path = self._entry_path()
        if not entry_path.exists():
            return False
        entry_path.unlink()
        return True

    def _entry_path(self) -> Path:
        return self._startup_dir / self._entry_name
