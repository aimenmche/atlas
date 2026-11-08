"""The version bump helper must keep package metadata and code in sync."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "atlas_bump_version", ROOT / "scripts" / "bump_version.py"
)
assert SPEC and SPEC.loader
bump_version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bump_version)


def _project(tmp_path: Path, version: str = "1.4.2") -> Path:
    (tmp_path / "atlas").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "atlas-analyst"\nversion = "'
        + version
        + '"\n',
        encoding="utf-8",
    )
    (tmp_path / "atlas" / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    return tmp_path


def test_bump_components():
    assert bump_version.bump("1.4.2", "patch") == "1.4.3"
    assert bump_version.bump("1.4.2", "minor") == "1.5.0"
    assert bump_version.bump("1.4.2", "major") == "2.0.0"


def test_apply_updates_both_files(tmp_path):
    root = _project(tmp_path, "1.4.2")
    assert bump_version.read_version(root) == "1.4.2"
    bump_version.apply(root, "1.5.0", dry_run=False)
    assert bump_version.read_version(root) == "1.5.0"
    init = (root / "atlas" / "__init__.py").read_text(encoding="utf-8")
    assert '__version__ = "1.5.0"' in init
    assert "1.4.2" not in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_dry_run_leaves_versions_alone(tmp_path):
    root = _project(tmp_path)
    bump_version.apply(root, "9.9.9", dry_run=True)
    assert bump_version.read_version(root) == "1.4.2"
    assert "__version__ = \"1.4.2\"" in (root / "atlas" / "__init__.py").read_text(
        encoding="utf-8"
    )


def test_non_semantic_version_is_rejected(tmp_path):
    root = _project(tmp_path, "1.4.2rc1")
    with pytest.raises(SystemExit):
        bump_version.read_version(root)
