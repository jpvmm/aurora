from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from typer.testing import CliRunner


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
RUNNER = CliRunner()


def test_project_script_points_to_root_app() -> None:
    pyproject_data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = pyproject_data["project"]["scripts"]

    assert scripts["aurora"] == "aurora.cli.app:app"


def test_root_help_renders_stable_usage() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["--help"], prog_name="aurora")

    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "aurora" in result.output
