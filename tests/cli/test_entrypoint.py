from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest
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


@pytest.mark.parametrize("command_group", ["setup", "config", "model", "doctor"])
def test_phase_one_command_groups_are_listed_in_root_help(command_group: str) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["--help"], prog_name="aurora")

    assert result.exit_code == 0
    assert command_group in result.output


@pytest.mark.parametrize("command_group", ["setup", "config", "model", "doctor"])
def test_phase_one_group_placeholders_are_explicit_in_pt_br(command_group: str) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, [command_group], prog_name="aurora")

    assert result.exit_code == 1
    assert "ainda não implementado" in result.output.lower()
