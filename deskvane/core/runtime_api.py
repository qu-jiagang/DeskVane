from __future__ import annotations

from dataclasses import fields, is_dataclass
from types import SimpleNamespace
from typing import Any, Callable

from .runtime_events import RuntimeEventStore


class RuntimeApi:
    """UI-neutral runtime boundary for future sidecar and Tauri callers."""

    _ACTION_METHODS: dict[str, str] = {
        "capture.screenshot": "do_screenshot",
        "capture.screenshot_and_pin": "do_screenshot_and_pin",
        "capture.interactive_screenshot": "do_screenshot_interactive",
        "capture.pure_ocr": "do_pure_ocr",
        "capture.pin_clipboard": "do_pin_clipboard",
        "clipboard.show_history": "show_clipboard_history",
        "proxy.toggle_git": "toggle_git_proxy",
        "proxy.toggle_terminal": "toggle_terminal_proxy",
        "settings.show": "show_settings",
        "help.show": "show_help",
        "subconverter.show": "show_subconverter",
        "translator.copy_last": "translator_copy_last",
        "translator.retry_last": "translator_retry_last",
        "translator.toggle_pause": "translator_toggle_pause",
        "app.quit": "quit",
    }

    def __init__(self, app: Any, events: RuntimeEventStore | None = None) -> None:
        self.app = app
        self.events = events or RuntimeEventStore()

    def get_state(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of the current runtime state."""
        state = {
            "capture": self._serialize(self.app.get_capture_state()),
            "clipboard_history": self._serialize(self.app.get_clipboard_history_state()),
            "translator": self._serialize(self.app.get_translator_state()),
            "shell": self._serialize(self.app.get_shell_state()),
            "proxy": self._serialize(self.app.get_proxy_state()),
            "subconverter": self._serialize(self.app.get_subconverter_state()),
        }
        system_getter = getattr(self.app, "get_system_state", None)
        if system_getter is not None:
            state["system"] = self._serialize(system_getter())
        return state

    def get_config(self) -> dict[str, Any]:
        return self._serialize(self.app.config)

    def translate_text(self, text: str) -> dict[str, Any]:
        translator = getattr(self.app, "translate_text", None)
        if translator is None:
            raise RuntimeError("runtime does not support text translation")
        result = translator(text)
        self.events.add("translator.translated", "Text translated")
        return self._serialize(result)

    def get_clipboard_history(self) -> dict[str, Any]:
        getter = getattr(self.app, "get_clipboard_history_items", None)
        if getter is None:
            raise RuntimeError("runtime does not support clipboard history items")
        return {"items": self._serialize(getter())}

    def select_clipboard_history_item(self, index: int) -> dict[str, Any]:
        selector = getattr(self.app, "select_clipboard_history_item", None)
        if selector is None:
            raise RuntimeError("runtime does not support clipboard history selection")
        item = selector(index)
        self.events.add("clipboard.selected", "Clipboard history item selected", data={"index": index})
        return {"item": self._serialize(item)}

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("config patch must be an object")

        config = self.app.config
        for section_name, section_patch in patch.items():
            if not isinstance(section_patch, dict):
                raise ValueError(f"config section must be an object: {section_name}")
            if not hasattr(config, section_name):
                raise KeyError(f"unknown config section: {section_name}")

            section = getattr(config, section_name)
            if not is_dataclass(section):
                raise KeyError(f"unknown config section: {section_name}")
            field_names = {field.name for field in fields(section)}

            for field_name, raw_value in section_patch.items():
                if field_name not in field_names:
                    raise KeyError(f"unknown config field: {section_name}.{field_name}")
                old_value = getattr(section, field_name)
                setattr(section, field_name, self._coerce_config_value(old_value, raw_value))

        config_manager = getattr(self.app, "config_manager", None)
        if config_manager is not None:
            config_manager.save(config)
        if hasattr(self.app, "reload_config"):
            self.app.reload_config()
        self.events.add("config.updated", "Configuration updated", data={"sections": sorted(patch)})
        return self.get_config()

    def dispatch_action(self, name: str, *args: Any) -> None:
        """Invoke a named runtime action.

        Names are intentionally feature-scoped strings so a future HTTP or
        Tauri command layer can expose the same action surface directly.
        """
        method_name = self._ACTION_METHODS.get(name)
        if method_name is None:
            raise KeyError(f"Unknown runtime action: {name}")
        method: Callable[..., Any] = getattr(self.app, method_name)
        method(*args)
        self.events.add("action.dispatched", f"Action dispatched: {name}", data={"action": name})

    def action_names(self) -> tuple[str, ...]:
        supported = getattr(self.app, "supported_runtime_actions", None)
        if supported is None:
            return tuple(sorted(self._ACTION_METHODS))
        return tuple(sorted(action for action in self._ACTION_METHODS if action in supported))

    def get_events(self, after_id: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return [self._serialize(event) for event in self.events.list(after_id=after_id, limit=limit)]

    def health(self) -> dict[str, str]:
        return {"status": "ok"}

    @staticmethod
    def _coerce_config_value(old_value: Any, raw_value: Any) -> Any:
        if isinstance(old_value, bool):
            if isinstance(raw_value, bool):
                return raw_value
            if isinstance(raw_value, str):
                lowered = raw_value.strip().lower()
                if lowered in {"1", "true", "yes", "on", "启用"}:
                    return True
                if lowered in {"0", "false", "no", "off", "关闭"}:
                    return False
            raise ValueError(f"expected boolean value, got {raw_value!r}")
        if isinstance(old_value, int) and not isinstance(old_value, bool):
            return int(raw_value)
        if isinstance(old_value, str):
            return str(raw_value)
        return raw_value

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        if is_dataclass(value):
            return {field.name: cls._serialize(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, SimpleNamespace):
            return cls._serialize(vars(value))
        if isinstance(value, dict):
            return {str(k): cls._serialize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._serialize(v) for v in value]
        return value
