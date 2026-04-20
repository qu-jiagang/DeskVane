from __future__ import annotations

from collections import defaultdict

from ...core.contributions import HotkeySpec, SettingsSectionSpec, TraySectionContribution


class HotkeyRegistry:
    def __init__(self) -> None:
        self._specs: list[HotkeySpec] = []

    def extend(self, specs: tuple[HotkeySpec, ...]) -> None:
        self._specs.extend(specs)

    def bind(self, app) -> None:
        hotkeys = getattr(app, "hotkeys", None)
        if hotkeys is None or not hasattr(hotkeys, "register"):
            return
        if hasattr(hotkeys, "clear"):
            hotkeys.clear()
        for spec in self._specs:
            if spec.enabled_when is not None and not spec.enabled_when(app):
                continue
            config_section = getattr(app.config, spec.config_section)
            hotkey = getattr(config_section, spec.config_field, spec.default)
            hotkeys.register(hotkey, getattr(app, spec.action_name))


class SettingsRegistry:
    def __init__(self) -> None:
        self._sections: list[SettingsSectionSpec] = []

    def extend(self, sections: tuple[SettingsSectionSpec, ...]) -> None:
        self._sections.extend(sections)

    def ordered_sections(self) -> list[SettingsSectionSpec]:
        return sorted(self._sections, key=lambda item: (item.order, item.label))


class TrayRegistry:
    def __init__(self) -> None:
        self._sections: dict[str, list[TraySectionContribution]] = defaultdict(list)

    def extend(self, contributions: tuple[TraySectionContribution, ...]) -> None:
        for contribution in contributions:
            self._sections[contribution.section].append(contribution)

    def build_entries(self, section: str, state) -> tuple:
        items: list = []
        for contribution in sorted(self._sections.get(section, []), key=lambda item: item.order):
            items.extend(contribution.build_entries(state))
        return tuple(items)
