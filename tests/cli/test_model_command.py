from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.model_download import DownloadResult
from aurora.runtime.settings import load_settings


RUNNER = CliRunner()


def test_model_set_updates_settings_and_keeps_existing_cached_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")

    cached_file = (
        tmp_path / "config" / "models" / "Qwen--Qwen3-8B-GGUF" / "Qwen3-8B-Q8_0.gguf"
    )
    cached_file.parent.mkdir(parents=True, exist_ok=True)
    cached_file.write_bytes(b"cached")

    monkeypatch.setattr(
        "aurora.cli.model.download_model",
        lambda *_, **__: DownloadResult(
            source="cache",
            local_path=cached_file,
            downloaded=False,
            used_token=False,
        ),
    )

    result = RUNNER.invoke(
        app_module.app,
        [
            "model",
            "set",
            "--endpoint",
            "http://127.0.0.1:8081",
            "--model",
            "Qwen3-8B-Q8_0",
            "--source",
            "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
            "--yes",
        ],
        prog_name="aurora",
    )

    settings = load_settings()

    assert result.exit_code == 0
    assert settings.endpoint_url == "http://127.0.0.1:8081"
    assert settings.model_id == "Qwen3-8B-Q8_0"
    assert settings.model_source == "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"
    assert cached_file.exists()
    assert "Próximo passo" in result.output


def test_model_set_blocks_non_local_endpoint_with_recovery_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")

    result = RUNNER.invoke(
        app_module.app,
        [
            "model",
            "set",
            "--endpoint",
            "https://api.openai.com/v1",
        ],
        prog_name="aurora",
    )

    assert result.exit_code == 1
    assert "Somente endpoints locais" in result.output
    assert "aurora model set --endpoint http://127.0.0.1:8080" in result.output


def test_model_set_runs_hf_download_pipeline_when_source_is_provided(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")

    expected_path = tmp_path / "config" / "models" / "model.gguf"
    captured: dict[str, object] = {}

    def fake_download(request, **kwargs):
        captured["repo"] = request.target.repo_id
        captured["private"] = request.private
        captured["token"] = request.token
        captured["confirm_download"] = kwargs["confirm_download"]
        return DownloadResult(
            source="huggingface",
            local_path=expected_path,
            downloaded=True,
            used_token=True,
        )

    monkeypatch.setattr("aurora.cli.model.download_model", fake_download)

    result = RUNNER.invoke(
        app_module.app,
        [
            "model",
            "set",
            "--source",
            "meta-llama/Llama-3-8B-GGUF:llama-3-8b.Q4_K_M.gguf",
            "--private",
            "--token",
            "hf_test_token",
            "--yes",
        ],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    assert captured["repo"] == "meta-llama/Llama-3-8B-GGUF"
    assert captured["private"] is True
    assert captured["token"] == "hf_test_token"
    assert "Modelo disponível em" in result.output
