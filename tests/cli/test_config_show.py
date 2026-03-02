from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.settings import RuntimeSettings, save_settings


RUNNER = CliRunner()


def test_config_show_displays_runtime_and_privacy_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")

    save_settings(
        RuntimeSettings(
            endpoint_url="http://user:secret@127.0.0.1:8080",
            model_id="Qwen3-8B-Q8_0",
            model_source="Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
            local_only=True,
            telemetry_enabled=False,
        )
    )

    result = RUNNER.invoke(app_module.app, ["config", "show"], prog_name="aurora")

    assert result.exit_code == 0
    assert "http://user:***@127.0.0.1:8080" in result.output
    assert "secret" not in result.output
    assert "local-only: ativado" in result.output.lower()
    assert "telemetria: desativada" in result.output.lower()

