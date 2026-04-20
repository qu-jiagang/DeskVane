# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_NAME = os.environ.get("DESKVANE_APP_NAME", "DeskVane")
TARGET_OS = os.environ.get("DESKVANE_TARGET_OS", sys.platform)
BUNDLE_IDENTIFIER = os.environ.get(
    "DESKVANE_BUNDLE_IDENTIFIER",
    "io.github.deskvane.app",
)
ICON_FILE = os.environ.get("DESKVANE_ICON_FILE") or None
WINDOWED = os.environ.get("DESKVANE_WINDOWED", "1") != "0"
ONEFILE = os.environ.get("DESKVANE_ONEFILE", "0") == "1"


def read_pyproject_version() -> str:
    text = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    import re

    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to read version from pyproject.toml")
    return match.group(1)


APP_VERSION = os.environ.get("DESKVANE_APP_VERSION") or read_pyproject_version()

datas = collect_data_files("deskvane", includes=["assets/*.png", "assets/*.svg"])
hiddenimports = sorted(
    set(
        collect_submodules("pystray")
        + collect_submodules("pynput")
        + collect_submodules("PIL")
    )
)

a = Analysis(
    [str(ROOT_DIR / "deskvane" / "__main__.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=not ONEFILE,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=not WINDOWED,
    disable_windowed_traceback=False,
    target_arch=None,
    icon=ICON_FILE,
)

if ONEFILE:
    app = exe
else:
    app = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )

if TARGET_OS == "macos":
    bundle = BUNDLE(
        app,
        name=f"{APP_NAME}.app",
        icon=ICON_FILE,
        bundle_identifier=BUNDLE_IDENTIFIER,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleIdentifier": BUNDLE_IDENTIFIER,
            "CFBundleVersion": APP_VERSION,
            "CFBundleShortVersionString": APP_VERSION,
            "NSHighResolutionCapable": True,
        },
    )
