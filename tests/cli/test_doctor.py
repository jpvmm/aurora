from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.errors import build_runtime_error
from aurora.runtime.llama_client import RuntimeValidationResult
from aurora.runtime.settings import RuntimeSettings, save_settings


RUNNER = CliRunner()


def test_doctor_reports_runtime_ready_when_checks_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")

    save_settings(
        RuntimeSettings(
            endpoint_url="http://user:secret@127.0.0.1:8080",
            model_id="Qwen3-8B-Q8_0",
            model_source="Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
            local_only=True,
            telemetry_enabled=False,
        )
    )
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
    assert "secret" not in result.output


def test_doctor_groups_actionable_runtime_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")

    save_settings(RuntimeSettings())
    monkeypatch.setattr(
        doctor_module,
        "validate_runtime",
        lambda *_: (_ for _ in ()).throw(
            build_runtime_error("model_missing", model_id="Qwen3-8B-Q8_0")
        ),
    )

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 1
    assert "problemas encontrados" in result.output.lower()
    assert "aurora model set --model Qwen3-8B-Q8_0" in result.output
    assert "aurora doctor" in result.output

