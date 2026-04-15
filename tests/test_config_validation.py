"""Tests for config validation logic."""

import tempfile
from pathlib import Path
from unittest import mock

import yaml

from deskvane.config import load_config


def test_port_clamped_to_valid_range() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_data = {"subconverter": {"port": 80}}
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            cfg = load_config()
            assert cfg.subconverter.port >= 1024


def test_poll_interval_clamped() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_data = {"translator": {"poll_interval_ms": 1}}
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            cfg = load_config()
            assert cfg.translator.poll_interval_ms >= 50


def test_max_chars_at_least_one() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_data = {"translator": {"max_chars": -5}}
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            cfg = load_config()
            assert cfg.translator.max_chars >= 1


def test_normal_values_unchanged() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        config_path = config_dir / "config.yaml"

        config_data = {
            "subconverter": {"port": 7777},
            "translator": {"poll_interval_ms": 350, "max_chars": 1600},
        }
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(config_data))

        with mock.patch("deskvane.config.CONFIG_DIR", config_dir), \
             mock.patch("deskvane.config.CONFIG_PATH", config_path):
            cfg = load_config()
            assert cfg.subconverter.port == 7777
            assert cfg.translator.poll_interval_ms == 350
            assert cfg.translator.max_chars == 1600
