from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
RUNNER = CliRunner()


def test_project_script_points_to_root_app() -> None:
    pyproject_text = PYPROJECT.read_text(encoding="utf-8")

    assert 'aurora = "aurora.cli.app:app"' in pyproject_text


def test_root_help_renders_stable_usage() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["--help"])

    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "aurora" in result.output
