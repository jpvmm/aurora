from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.errors import build_runtime_error
from aurora.runtime.llama_client import RuntimeValidationResult
from aurora.runtime.settings import RuntimeSettings


RUNNER = CliRunner()


def test_setup_wizard_retries_until_runtime_validation_passes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    setup_module = importlib.import_module("aurora.cli.setup")

    validations = [
        build_runtime_error("timeout", detail="Servidor ainda carregando"),
        RuntimeValidationResult(
            endpoint_state="ready",
            model_id="Qwen3-8B-Q8_0",
            available_models=("Qwen3-8B-Q8_0",),
        ),
    ]
    persisted: list[tuple[str | None, str | None, str | None]] = []

    def fake_model_set_command(
        endpoint: str | None = None,
        model: str | None = None,
        source: str | None = None,
        **_: object,
    ) -> None:
        persisted.append((endpoint, model, source))

    def fake_validate_runtime(endpoint_url: str, model_id: str):
        value = validations.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(setup_module, "model_set_command", fake_model_set_command)
    monkeypatch.setattr(setup_module, "validate_runtime", fake_validate_runtime)
    monkeypatch.setattr(
        setup_module,
        "load_settings",
        lambda: RuntimeSettings(
            endpoint_url="http://127.0.0.1:8080",
            model_id="Qwen3-8B-Q8_0",
            model_source="Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
            local_only=True,
            telemetry_enabled=False,
        ),
    )

    result = RUNNER.invoke(
        setup_module.setup_app,
        [],
        input=(
            "http://127.0.0.1:8080\n"
            "Qwen3-8B-Q8_0\n"
            "\n"
            "y\n"
            "http://127.0.0.1:8080\n"
            "Qwen3-8B-Q8_0\n"
            "\n"
        ),
        prog_name="aurora setup",
    )

    assert result.exit_code == 0
    assert len(persisted) == 2
    assert "aurora ask" in result.output
    assert "aurora config set language <codigo>" in result.output
    assert "telemetria: desativada" in result.output.lower()


def test_setup_wizard_blocks_completion_when_user_aborts_after_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    setup_module = importlib.import_module("aurora.cli.setup")

    monkeypatch.setattr(setup_module, "model_set_command", lambda **_: None)
    monkeypatch.setattr(
        setup_module,
        "validate_runtime",
        lambda *_: (_ for _ in ()).throw(build_runtime_error("endpoint_offline")),
    )

    result = RUNNER.invoke(
        setup_module.setup_app,
        [],
        input="http://127.0.0.1:8080\nQwen3-8B-Q8_0\n\nn\n",
        prog_name="aurora setup",
    )

    assert result.exit_code == 1
    assert "aurora doctor" in result.output


def test_root_command_runs_first_run_wizard_when_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")

    called = {"value": False}
    monkeypatch.setattr(app_module, "should_run_first_run_wizard", lambda: True)
    monkeypatch.setattr(
        app_module,
        "run_first_run_wizard",
        lambda: called.__setitem__("value", True),
    )

    result = RUNNER.invoke(app_module.app, [], prog_name="aurora")

    assert result.exit_code == 0
    assert called["value"] is True
