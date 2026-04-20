from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class TrayMenuSeparator:
    pass


@dataclass(frozen=True, slots=True)
class TrayMenuItem:
    label: str
    action: str | None = None
    action_args: tuple[object, ...] = ()
    enabled: bool = True
    checked: bool | None = None
    radio: bool = False
    default: bool = False
    submenu: tuple["TrayMenuEntry", ...] = ()


TrayMenuEntry: TypeAlias = TrayMenuItem | TrayMenuSeparator


@dataclass(frozen=True, slots=True)
class TrayMenuModel:
    items: tuple[TrayMenuEntry, ...]
