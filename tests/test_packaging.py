from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_exposes_console_script_entrypoint():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    scripts = data.get("project", {}).get("scripts", {})
    assert scripts.get("sql-obfuscator") == "sql_obfuscator.cli:main"
