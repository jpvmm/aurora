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
            kb_vault_path="/vault",
            kb_qmd_index_name="aurora-index",
            kb_qmd_collection_name="aurora-collection",
            kb_auto_embeddings_enabled=False,
        )
    )

    result = RUNNER.invoke(app_module.app, ["config", "show"], prog_name="aurora")

    assert result.exit_code == 0
    assert "http://user:***@127.0.0.1:8080" in result.output
    assert "secret" not in result.output
    assert "local-only: ativado" in result.output.lower()
    assert "telemetria: desativada" in result.output.lower()
    assert "kb:" in result.output.lower()
    assert "vault: /vault" in result.output.lower()
    assert "index: aurora-index" in result.output.lower()
    assert "collection: aurora-collection" in result.output.lower()
    assert "auto-embeddings: desativado" in result.output.lower()


def test_config_show_renders_iterative_retrieval_section(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")

    save_settings(RuntimeSettings())  # all defaults

    result = RUNNER.invoke(app_module.app, ["config", "show"], prog_name="aurora")

    assert result.exit_code == 0
    assert "Iterative retrieval:" in result.output
    assert "- loop: ativado" in result.output
    assert "- judge LLM: desativado" in result.output
    assert "- min top score: 0.35" in result.output
    assert "- min hits: 2" in result.output
    assert "- min context chars: 800" in result.output
    assert "- jaccard threshold: 0.70" in result.output
