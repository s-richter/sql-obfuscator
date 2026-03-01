from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_exposes_console_script_entrypoint():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    scripts = data.get("project", {}).get("scripts", {})
    assert scripts.get("sql-obfuscator") == "sql_obfuscator.cli:main"


def test_pyproject_declares_runtime_text_assets_as_package_data():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    package_data = data.get("tool", {}).get("setuptools", {}).get("package-data", {})
    assert package_data.get("sql_obfuscator") == ["*.txt"]


def test_pyproject_description_mentions_supported_dialects():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    description = data.get("project", {}).get("description", "").lower()
    assert "t-sql" in description
    assert "hive" in description
