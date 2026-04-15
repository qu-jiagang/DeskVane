import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from deskvane import bootstrap


def test_configure_linux_tray_backend_prefers_appindicator_when_available() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        dist_packages = Path(temp_dir) / "dist-packages"
        dist_packages.mkdir()

        with mock.patch.object(bootstrap, "SYSTEM_DIST_PACKAGES", (dist_packages,)), \
             mock.patch.object(sys, "platform", "linux"), \
             mock.patch.object(bootstrap, "_can_use_appindicator", return_value=True), \
             mock.patch.dict(os.environ, {}, clear=True):
            original_sys_path = list(sys.path)
            try:
                bootstrap.configure_linux_tray_backend()
                assert os.environ["PYSTRAY_BACKEND"] == "appindicator"
                assert str(dist_packages) in sys.path
            finally:
                sys.path[:] = original_sys_path


def test_configure_linux_tray_backend_respects_existing_backend() -> None:
    with mock.patch.object(sys, "platform", "linux"), \
         mock.patch.object(bootstrap, "_inject_system_dist_packages") as inject_mock, \
         mock.patch.object(bootstrap, "_can_use_appindicator") as can_use_mock, \
         mock.patch.dict(os.environ, {"PYSTRAY_BACKEND": "xorg"}, clear=True):
        bootstrap.configure_linux_tray_backend()
        assert os.environ["PYSTRAY_BACKEND"] == "xorg"

    inject_mock.assert_not_called()
    can_use_mock.assert_not_called()


def test_configure_linux_tray_backend_does_not_force_backend_when_unavailable() -> None:
    with mock.patch.object(sys, "platform", "linux"), \
         mock.patch.object(bootstrap, "_can_use_appindicator", return_value=False), \
         mock.patch.dict(os.environ, {}, clear=True):
        bootstrap.configure_linux_tray_backend()

    assert "PYSTRAY_BACKEND" not in os.environ
