from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    id: str
    config_section: str
    config_field: str
    default: str
    description: str
    action_name: str
    enabled_when: Callable[[Any], bool] | None = None


@dataclass(frozen=True, slots=True)
class SettingsGroupSpec:
    title: str
    description: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SettingsSectionSpec:
    id: str
    label: str
    config_attr: str
    summary: str = ""
    order: int = 100
    groups: tuple[SettingsGroupSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class TraySectionContribution:
    section: str
    order: int
    build_entries: Callable[[Any], tuple[Any, ...]]
