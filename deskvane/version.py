from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
import re
from functools import lru_cache
from pathlib import Path


_ROOT_DIR = Path(__file__).resolve().parents[1]
_PYPROJECT_PATH = _ROOT_DIR / "pyproject.toml"
_PACKAGE_NAME = "deskvane"


@lru_cache(maxsize=1)
def get_version() -> str:
    try:
        return package_version(_PACKAGE_NAME)
    except PackageNotFoundError:
        pass

    text = _PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to read version from {_PYPROJECT_PATH}")
    return match.group(1)
