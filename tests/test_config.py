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
            assert config.screenshot.save_dir == "~/Pictures/DeskVane"
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


def test_config_ignore_unknown_fields() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "screenshot": {"hotkey": "x"},
            "unknown_field": 123,
            "general": {"fake_field": "abc"},
            "mihomo": {"backend": "core"},
        }
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            config = load_config()
            assert config.screenshot.hotkey == "x"
            # It loads gracefully despite unknown fields
            assert config.general.notifications_enabled is True
            assert not hasattr(config, "mihomo")
