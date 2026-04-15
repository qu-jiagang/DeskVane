"""Centralized logging for DeskVane."""

from __future__ import annotations

import logging
import sys

_FORMAT = "[deskvane.%(name)s] %(levelname)s: %(message)s"
_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the ``deskvane`` namespace.

    On first call, configures the root ``deskvane`` logger to write to stderr.
    """
    global _configured  # noqa: PLW0603
    if not _configured:
        _configured = True
        root = logging.getLogger("deskvane")
        root.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
    return logging.getLogger(f"deskvane.{name}")
