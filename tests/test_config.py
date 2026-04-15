import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock
import yaml

from deskvane.config import load_config


def test_config_load_default() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"
        
        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            config = load_config()
            assert config.screenshot.hotkey == "<ctrl>+<shift>+a"
            assert config.screenshot.copy_to_clipboard is True
            assert config.general.notifications_enabled is True
            assert config.translator.target_language == "简体中文"
            assert config.mihomo.backend == "party"
            assert config.mihomo.core_binary == "mihomo"
            assert config.screenshot.save_dir == "~/Pictures/DeskVane"
            assert config.mihomo.core_home_dir == "~/.config/deskvane/mihomo"
            assert config.mihomo.subscription_url == ""
            assert config.mihomo.saved_subscriptions == []
            assert config_path.exists()
            
            # Check saved YAML
            data = yaml.safe_load(config_path.read_text())
            assert data["screenshot"]["hotkey"] == "<ctrl>+<shift>+a"


def test_config_load_existing() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"
        
        # Create a pre-existing config with some changes
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "screenshot": {"hotkey": "<ctrl>+p"},
            "general": {"notifications_enabled": False},
        }
        config_path.write_text(yaml.dump(config_data))
        
        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            config = load_config()
            assert config.screenshot.hotkey == "<ctrl>+p"
            assert config.general.notifications_enabled is False
            # Fallback to default for missing fields
            assert config.translator.poll_interval_ms == 350


def test_config_promotes_current_subscription_into_saved_list() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "mihomo": {
                "subscription_url": "https://example.com/sub",
            }
        }
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            config = load_config()
            assert config.mihomo.subscription_url == "https://example.com/sub"
            assert config.mihomo.saved_subscriptions == ["https://example.com/sub"]


def test_mihomo_alias_fields_are_migrated() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "mihomo": {
                "ui_mode": "core",
                "binary_path": "/usr/local/bin/mihomo",
                "working_dir": "~/custom/mihomo",
            }
        }
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            config = load_config()
            assert config.mihomo.backend == "core"
            assert config.mihomo.core_binary == "/usr/local/bin/mihomo"
            assert config.mihomo.core_home_dir == "~/custom/mihomo"


def test_config_ignore_unknown_fields() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"
        
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "screenshot": {"hotkey": "x"},
            "unknown_field": 123,
            "general": {"fake_field": "abc"}
        }
        config_path.write_text(yaml.dump(config_data))
        
        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            config = load_config()
            assert config.screenshot.hotkey == "x"
            # It loads gracefully despite unknown fields
            assert config.general.notifications_enabled is True
