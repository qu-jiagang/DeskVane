from __future__ import annotations

import re
import subprocess
from pathlib import Path

from deskvane.version import get_version


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_packaging_extra() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(
        r"\[project\.optional-dependencies\]\s+packaging\s*=\s*\[(.*?)\]",
        text,
        re.DOTALL,
    )
    assert match is not None
    assert "pyinstaller>=" in match.group(1).lower()


def test_shell_packaging_scripts_are_valid_bash() -> None:
    for relative_path in ("scripts/build-pyinstaller.sh", "scripts/build-macos.sh"):
        subprocess.run(
            ["bash", "-n", str(ROOT / relative_path)],
            check=True,
            cwd=ROOT,
        )


def test_packaging_templates_exist_and_reference_expected_outputs() -> None:
    spec_text = (ROOT / "packaging/pyinstaller/deskvane.spec").read_text(
        encoding="utf-8"
    )
    assert 'collect_data_files("deskvane"' in spec_text
    assert "read_pyproject_version" in spec_text

    iss_text = (ROOT / "packaging/windows/deskvane.iss").read_text(
        encoding="utf-8"
    )
    assert "dist\\pyinstaller" in iss_text
    assert "OutputDir={#SourceDir}\\dist\\installer" in iss_text
    assert '#error AppVersion must be provided by the build script' in iss_text


def test_packaging_docs_and_scripts_reference_cross_platform_builds() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "./scripts/build-deb.sh" in readme
    assert "scripts/build-macos.sh" in readme
    assert "build-win.ps1" in readme
    assert "docs/release-process.md" in readme

    win_script = (ROOT / "scripts/build-win.ps1").read_text(encoding="utf-8")
    assert "PyInstaller" in win_script
    assert "deskvane.iss" in win_script


def test_release_process_doc_references_signing_steps() -> None:
    release_doc = (ROOT / "docs/release-process.md").read_text(encoding="utf-8")

    assert "codesign" in release_doc
    assert "notarytool" in release_doc
    assert "Inno Setup" in release_doc


def test_runtime_version_comes_from_pyproject() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None
    assert get_version() == match.group(1)


def test_runtime_version_prefers_installed_package_metadata(monkeypatch) -> None:
    monkeypatch.setattr("deskvane.version.package_version", lambda name: "9.9.9")
    get_version.cache_clear()
    try:
        assert get_version() == "9.9.9"
    finally:
        get_version.cache_clear()
