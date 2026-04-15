from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import yaml

CONFIG_DIR = Path.home() / ".config" / "deskvane"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
OLD_JSON_PATH = CONFIG_DIR / "config.json"


@dataclass(slots=True)
class ScreenshotConfig:
    save_dir: str = "~/Pictures/DeskVane"
    hotkey: str = "<ctrl>+<shift>+a"
    hotkey_pin: str = "<f1>"
    hotkey_pure_ocr: str = "<alt>+<f1>"
    hotkey_interactive: str = "<ctrl>+<f1>"
    hotkey_pin_clipboard: str = "<f3>"
    copy_to_clipboard: bool = True
    save_to_disk: bool = False
    notifications_enabled: bool = False


@dataclass(slots=True)
class ProxyConfig:
    address: str = "http://127.0.0.1:7890"


@dataclass(slots=True)
class TranslatorConfig:
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = ""
    source_language: str = "auto"
    target_language: str = "简体中文"
    poll_interval_ms: int = 350
    selection_enabled: bool = False
    clipboard_enabled: bool = True
    popup_enabled: bool = True
    debounce_ms: int = 220
    max_chars: int = 1600
    min_chars: int = 2
    keep_alive: str = "15m"
    request_timeout_s: int = 25
    auto_copy: bool = False
    disable_thinking: bool = True
    max_output_tokens: int = 1024
    popup_width_px: int = 360
    prompt_extra: str = ""
    hotkey_toggle_pause: str = "<ctrl>+<alt>+t"


@dataclass(slots=True)
class GeneralConfig:
    notifications_enabled: bool = True
    clipboard_history_enabled: bool = True
    hotkey_clipboard_history: str = "<alt>+v"
    tray_display: str = "default"


@dataclass(slots=True)
class SubconverterConfig:
    port: int = 7777
    enable_server: bool = True


@dataclass(slots=True)
class MihomoConfig:
    backend: str = "party"
    autostart: bool = True
    core_binary: str = "mihomo"
    core_home_dir: str = "~/.config/deskvane/mihomo"
    subscription_url: str = ""
    saved_subscriptions: list[str] = field(default_factory=list)
    external_controller: str = "127.0.0.1:9090"
    secret: str = ""
    external_ui: str = ""
    external_ui_name: str = ""
    external_ui_url: str = ""
    startup_timeout_s: int = 8
    tun_enabled: bool = False
    tun_direct_processes: str = ""
    pac_enabled: bool = False
    pac_port: int = 7893
    pac_remote_url: str = ""
    pac_proxy_domains: str = ""
    pac_direct_domains: str = ""
    pac_default_action: str = "PROXY"


@dataclass(slots=True)
class AppConfig:
    screenshot: ScreenshotConfig = field(default_factory=ScreenshotConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)
    subconverter: SubconverterConfig = field(default_factory=SubconverterConfig)
    mihomo: MihomoConfig = field(default_factory=MihomoConfig)


def _migrate_old_json() -> None:
    """Migrate settings from config.json to config.yaml if JSON exists but YAML doesn't."""
    if not OLD_JSON_PATH.exists() or CONFIG_PATH.exists():
        return
    
    try:
        import json
        data = json.loads(OLD_JSON_PATH.read_text(encoding="utf-8"))
        
        # Build nested config from flat JSON
        cfg = AppConfig()
        
        def map_field(old_key: str, dest_obj: object, new_key: str):
            if old_key in data:
                setattr(dest_obj, new_key, data[old_key])
                
        # Screenshot
        map_field("screenshot_save_dir", cfg.screenshot, "save_dir")
        map_field("screenshot_hotkey", cfg.screenshot, "hotkey")
        map_field("screenshot_copy_to_clipboard", cfg.screenshot, "copy_to_clipboard")
        # Git / Terminal Proxy
        map_field("git_proxy_address", cfg.proxy, "address")
        # General
        map_field("notifications_enabled", cfg.general, "notifications_enabled")
        # Translator
        for key in data.keys():
            if key.startswith("translator_"):
                map_field(key, cfg.translator, key.replace("translator_", "", 1))

        _save_config(cfg)
        
        # Rename old JSON to .bak
        OLD_JSON_PATH.rename(OLD_JSON_PATH.with_suffix(".json.bak"))
    except Exception:
        pass


def _save_config(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Convert to dict and dump YAML
    data = asdict(config)
    CONFIG_PATH.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _clamp(value: int | float, lo: int | float, hi: int | float) -> int | float:
    return max(lo, min(hi, value))


def _validate_config(cfg: AppConfig) -> None:
    """Clamp numeric settings to safe ranges."""
    cfg.subconverter.port = int(_clamp(cfg.subconverter.port, 1024, 65535))
    cfg.translator.poll_interval_ms = int(_clamp(cfg.translator.poll_interval_ms, 50, 5000))
    cfg.translator.max_chars = max(1, cfg.translator.max_chars)
    cfg.translator.min_chars = max(1, cfg.translator.min_chars)
    cfg.translator.request_timeout_s = int(_clamp(cfg.translator.request_timeout_s, 1, 300))
    cfg.translator.max_output_tokens = int(_clamp(cfg.translator.max_output_tokens, 16, 65536))
    cfg.translator.popup_width_px = int(_clamp(cfg.translator.popup_width_px, 100, 2000))
    cfg.translator.debounce_ms = int(_clamp(cfg.translator.debounce_ms, 0, 5000))
    if cfg.mihomo.backend not in {"party", "core"}:
        cfg.mihomo.backend = "party"
    cfg.mihomo.startup_timeout_s = int(_clamp(cfg.mihomo.startup_timeout_s, 1, 60))
    cfg.mihomo.pac_port = int(_clamp(cfg.mihomo.pac_port, 1024, 65535))
    if cfg.mihomo.pac_default_action not in {"PROXY", "DIRECT"}:
        cfg.mihomo.pac_default_action = "PROXY"
    saved_subscriptions: list[str] = []
    seen: set[str] = set()
    for raw in [cfg.mihomo.subscription_url, *cfg.mihomo.saved_subscriptions]:
        normalized = str(raw).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        saved_subscriptions.append(normalized)
    cfg.mihomo.subscription_url = saved_subscriptions[0] if saved_subscriptions else ""
    cfg.mihomo.saved_subscriptions = saved_subscriptions[:8]


def load_config() -> AppConfig:
    """Load config from disk; create default file on first run."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Try migration first
    _migrate_old_json()

    if not CONFIG_PATH.exists():
        _save_config(AppConfig())
        return AppConfig()
        
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        
        # Construct dataclasses manually to ignore unknown fields
        def _extract(data_dict, cls):
            if not isinstance(data_dict, dict):
                data_dict = {}
            known_fields = {f.name for f in cls.__dataclass_fields__.values()}
            return cls(**{k: v for k, v in data_dict.items() if k in known_fields})

        
        proxy_data = data.get("proxy") or data.get("git_proxy") or {}
        
        mihomo_data = data.get("mihomo", {})
        if not isinstance(mihomo_data, dict):
            mihomo_data = {}
        else:
            mihomo_data = dict(mihomo_data)
            if "ui_mode" in mihomo_data and "backend" not in mihomo_data:
                mihomo_data["backend"] = mihomo_data["ui_mode"]
            if "binary_path" in mihomo_data and "core_binary" not in mihomo_data:
                mihomo_data["core_binary"] = mihomo_data["binary_path"]
            if "working_dir" in mihomo_data and "core_home_dir" not in mihomo_data:
                mihomo_data["core_home_dir"] = mihomo_data["working_dir"]

        cfg = AppConfig(
            screenshot=_extract(data.get("screenshot", {}), ScreenshotConfig),
            proxy=_extract(proxy_data, ProxyConfig),
            translator=_extract(data.get("translator", {}), TranslatorConfig),
            general=_extract(data.get("general", {}), GeneralConfig),
            subconverter=_extract(data.get("subconverter", {}), SubconverterConfig),
            mihomo=_extract(mihomo_data, MihomoConfig),
        )
        _validate_config(cfg)
        # Always re-save to ensure missing fields are populated in the YAML
        _save_config(cfg)
        return cfg
    except Exception:
        # Fallback if file is corrupted
        from .log import get_logger
        get_logger("config").warning(
            "Config file %s is corrupted, falling back to defaults", CONFIG_PATH
        )
        default_cfg = AppConfig()
        _save_config(default_cfg)
        return default_cfg
