from __future__ import annotations

from unittest import mock

from deskvane.app import _normalize_platform_specific_config
from deskvane.config import AppConfig
from deskvane.platform.factory import create_platform_services
from deskvane.ui.settings_panel import mihomo_backend_options


def test_mihomo_backend_options_hides_party_on_non_linux() -> None:
    assert mihomo_backend_options(False) == [("core", "Mihomo Core")]


def test_mihomo_backend_options_includes_party_on_linux() -> None:
    assert mihomo_backend_options(True) == [
        ("party", "Mihomo Party"),
        ("core", "Mihomo Core"),
    ]


def test_normalize_platform_specific_config_forces_core_when_party_unsupported() -> None:
    cfg = AppConfig()
    cfg.mihomo.backend = "party"

    with mock.patch("deskvane.platform.factory.sys.platform", "win32"):
        services = create_platform_services()

    changed = _normalize_platform_specific_config(cfg, services)

    assert changed is True
    assert cfg.mihomo.backend == "core"
