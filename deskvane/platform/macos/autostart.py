from __future__ import annotations

import os
from pathlib import Path

from ..base import AutostartService


class MacOSAutostartService(AutostartService):
    def __init__(
        self,
        launch_agents_dir: Path | None = None,
        label: str = "io.github.deskvane",
        command: str = "deskvane",
    ) -> None:
        env_dir = os.environ.get("DESKVANE_MACOS_LAUNCH_AGENTS_DIR")
        self._launch_agents_dir = launch_agents_dir or Path(env_dir) if env_dir else launch_agents_dir
        if self._launch_agents_dir is None:
            self._launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        self._label = label
        self._command = command

    def is_supported(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return self._entry_path().exists()

    def enable(self, command: str | None = None) -> bool:
        entry_path = self._entry_path()
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        startup_command = command or self._command
        entry_path.write_text(
            "\n".join(
                (
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                    '<plist version="1.0">',
                    "<dict>",
                    f"  <key>Label</key><string>{self._label}</string>",
                    "  <key>ProgramArguments</key>",
                    "  <array>",
                    "    <string>/bin/sh</string>",
                    "    <string>-lc</string>",
                    f"    <string>{startup_command}</string>",
                    "  </array>",
                    "  <key>RunAtLoad</key><true/>",
                    "</dict>",
                    "</plist>",
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
        return self._launch_agents_dir / f"{self._label}.plist"
