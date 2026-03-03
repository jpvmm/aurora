from __future__ import annotations

import importlib
import json
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.model_download import DownloadResult
from aurora.runtime.server_lifecycle import LifecycleHealth, LifecycleStatus
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


def test_model_start_prints_persistent_server_guidance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def start_server(self, **kwargs):
            _ = kwargs
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=4242,
                process_group_id=4242,
                uptime_seconds=1,
                ready=True,
                message="runtime ok",
            )

    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(app_module.app, ["model", "start"], prog_name="aurora")

    assert result.exit_code == 0
    assert "permanece ativo" in result.output.lower()
    assert "aurora model stop" in result.output


def test_model_stop_reports_external_runtime_without_termination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def stop_server(self, **kwargs):
            _ = kwargs
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="external",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=None,
                process_group_id=None,
                uptime_seconds=None,
                ready=True,
                message="Servidor externo detectado.",
            )

    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(app_module.app, ["model", "stop"], prog_name="aurora")

    assert result.exit_code == 0
    assert "servidor externo" in result.output.lower()
    assert "nao foi encerrado" in result.output.lower()


def test_model_status_supports_json_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def get_status(self):
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=1111,
                process_group_id=1111,
                uptime_seconds=30,
                ready=True,
            )

    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(app_module.app, ["model", "status", "--json"], prog_name="aurora")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["lifecycle_state"] == "running"
    assert payload["ownership"] == "managed"
    assert payload["pid"] == 1111
    assert payload["ready"] is True


def test_model_health_supports_json_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def check_health(self):
            return LifecycleHealth(
                ok=False,
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                ownership="managed",
                pid=4_242,
                uptime_seconds=5,
                category="endpoint_offline",
                message="offline",
                recovery_commands=("aurora model start",),
            )

    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(app_module.app, ["model", "health", "--json"], prog_name="aurora")

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["category"] == "endpoint_offline"
    assert payload["pid"] == 4_242
    assert payload["uptime_seconds"] == 5
    assert payload["recovery_commands"] == ["aurora model start"]


def test_model_health_text_output_displays_pid_and_uptime_lines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def check_health(self):
            return LifecycleHealth(
                ok=True,
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                ownership="managed",
                pid=7_001,
                uptime_seconds=42,
                category=None,
                message="runtime ok",
                recovery_commands=(),
            )

    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(app_module.app, ["model", "health"], prog_name="aurora")

    assert result.exit_code == 0
    assert "- pid: 7001" in result.output
    assert "- uptime(s): 42" in result.output


def test_model_start_non_interactive_requires_override_for_external_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def start_server(self, **kwargs):
            callback = kwargs.get("external_reuse_decision")
            if callback is not None:
                callback(
                    LifecycleStatus(
                        lifecycle_state="running",
                        ownership="external",
                        endpoint_url="http://127.0.0.1:8080",
                        port=8080,
                        model_id="Qwen3-8B-Q8_0",
                        pid=None,
                        process_group_id=None,
                        uptime_seconds=None,
                        ready=True,
                        message="external",
                    )
                )
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="external",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=None,
                process_group_id=None,
                uptime_seconds=None,
                ready=True,
            )

    monkeypatch.setattr(model_module, "_is_interactive_terminal", lambda: False, raising=False)
    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(app_module.app, ["model", "start"], prog_name="aurora")

    assert result.exit_code == 1
    assert "--yes" in result.output
    assert "--force" in result.output


def test_model_set_blocks_restart_without_override_in_non_interactive_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")

    class FakeService:
        def get_status(self):
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=9100,
                process_group_id=9100,
                uptime_seconds=100,
                ready=True,
            )

    monkeypatch.setattr(model_module, "_is_interactive_terminal", lambda: False, raising=False)
    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(
        app_module.app,
        ["model", "set", "--model", "Qwen3-8B-Q4_0"],
        prog_name="aurora",
    )

    assert result.exit_code == 1
    assert "runtime ativo" in result.output.lower()
    assert "--yes" in result.output


def test_model_set_yes_restarts_managed_runtime_after_model_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    model_module = importlib.import_module("aurora.cli.model")
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeService:
        def get_status(self):
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=9100,
                process_group_id=9100,
                uptime_seconds=100,
                ready=True,
            )

        def stop_server(self, **kwargs):
            calls.append(("stop", kwargs))
            return LifecycleStatus(
                lifecycle_state="stopped",
                ownership=None,
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q4_0",
                pid=None,
                process_group_id=None,
                uptime_seconds=None,
                ready=False,
            )

        def start_server(self, **kwargs):
            calls.append(("start", kwargs))
            return LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q4_0",
                pid=9200,
                process_group_id=9200,
                uptime_seconds=1,
                ready=True,
            )

    monkeypatch.setattr(model_module, "_is_interactive_terminal", lambda: False, raising=False)
    monkeypatch.setattr(model_module, "ServerLifecycleService", lambda: FakeService(), raising=False)

    result = RUNNER.invoke(
        app_module.app,
        ["model", "set", "--model", "Qwen3-8B-Q4_0", "--yes"],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    assert calls == [
        ("stop", {"force": True}),
        (
            "start",
            {
                "allow_external_reuse": False,
                "non_interactive": True,
                "reason": "model_change_restart",
            },
        ),
    ]
