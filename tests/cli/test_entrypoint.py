from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from aurora.runtime.llama_client import RuntimeValidationResult


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


def test_root_no_args_shows_help_when_wizard_is_not_required(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setattr(app_module, "should_run_first_run_wizard", lambda: False)

    result = RUNNER.invoke(app_module.app, [], prog_name="aurora")

    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "setup" in result.output
    assert "config" in result.output
    assert "model" in result.output
    assert "doctor" in result.output


@pytest.mark.parametrize("command_group", ["setup", "config", "model", "doctor"])
def test_phase_one_command_groups_are_listed_in_root_help(command_group: str) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["--help"], prog_name="aurora")

    assert result.exit_code == 0
    assert command_group in result.output


def test_setup_group_invokes_setup_wizard_entrypoint(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    setup_module = importlib.import_module("aurora.cli.setup")
    called = {"value": False}

    def fake_wizard() -> None:
        called["value"] = True
        typer.echo("setup wizard called")

    monkeypatch.setattr(setup_module, "run_first_run_wizard", fake_wizard)

    result = RUNNER.invoke(app_module.app, ["setup"], prog_name="aurora")

    assert result.exit_code == 0
    assert called["value"] is True
    assert "setup wizard called" in result.output


def test_config_group_shows_guidance_without_placeholder_message() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["config"], prog_name="aurora")

    assert result.exit_code == 1
    assert "aurora config show" in result.output.lower()
    assert "ainda nao implementado" not in result.output.lower()


def test_doctor_group_runs_runtime_checks_without_placeholder_message(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    monkeypatch.setattr(
        doctor_module,
        "validate_runtime",
        lambda *_: RuntimeValidationResult(
            endpoint_state="ready",
            model_id="Qwen3-8B-Q8_0",
            available_models=("Qwen3-8B-Q8_0",),
        ),
    )
    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 0
    assert "runtime local pronto" in result.output.lower()
    assert "ainda nao implementado" not in result.output.lower()


def test_model_group_exposes_set_command_in_help() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["model", "--help"], prog_name="aurora")

    assert result.exit_code == 0
    assert "set" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output
    assert "health" in result.output
