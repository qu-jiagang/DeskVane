from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized


def is_translatable(text: str, min_chars: int) -> bool:
    if len(text) < min_chars:
        return False
    return bool(re.search(r"[\w\u00C0-\u024F\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]", text))


def ellipsize(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"

