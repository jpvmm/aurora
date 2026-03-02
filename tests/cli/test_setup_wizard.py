from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.errors import build_runtime_error
from aurora.runtime.server_lifecycle import EnsureRuntimeResult, LifecycleHealth, LifecycleStatus
from aurora.runtime.settings import RuntimeSettings


RUNNER = CliRunner()


def test_setup_wizard_retries_until_runtime_validation_passes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    setup_module = importlib.import_module("aurora.cli.setup")

    validations: list[Exception | EnsureRuntimeResult] = [
        build_runtime_error("timeout", detail="Servidor ainda carregando"),
        EnsureRuntimeResult(
            settings=RuntimeSettings(),
            status=LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=2100,
                process_group_id=2100,
                uptime_seconds=2,
                ready=True,
            ),
            health=LifecycleHealth(
                ok=True,
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                ownership="managed",
                category=None,
                message="ok",
            ),
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

    def fake_ensure_runtime_for_inference(**_: object):
        value = validations.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(setup_module, "model_set_command", fake_model_set_command)
    monkeypatch.setattr(
        setup_module,
        "ensure_runtime_for_inference",
        fake_ensure_runtime_for_inference,
        raising=False,
    )
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
        "ensure_runtime_for_inference",
        lambda **_: (_ for _ in ()).throw(build_runtime_error("endpoint_offline")),
        raising=False,
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


def test_setup_wizard_auto_start_path_uses_inference_guard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    setup_module = importlib.import_module("aurora.cli.setup")
    calls: list[dict[str, object]] = []

    def fake_ensure_runtime_for_inference(**kwargs):
        calls.append(kwargs)
        return EnsureRuntimeResult(
            settings=RuntimeSettings(),
            status=LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=2000,
                process_group_id=2000,
                uptime_seconds=1,
                ready=True,
            ),
            health=LifecycleHealth(
                ok=True,
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                ownership="managed",
                category=None,
                message="ok",
            ),
        )

    monkeypatch.setattr(setup_module, "model_set_command", lambda **_: None)
    monkeypatch.setattr(
        setup_module,
        "ensure_runtime_for_inference",
        fake_ensure_runtime_for_inference,
        raising=False,
    )
    monkeypatch.setattr(setup_module, "load_settings", lambda: RuntimeSettings())

    result = RUNNER.invoke(
        setup_module.setup_app,
        [],
        input="http://127.0.0.1:8080\nQwen3-8B-Q8_0\n\n",
        prog_name="aurora setup",
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0]["non_interactive"] is False
    assert callable(calls[0]["model_bootstrap_callback"])


def test_setup_wizard_bootstrap_missing_model_persists_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    setup_module = importlib.import_module("aurora.cli.setup")
    persisted: list[tuple[str | None, str | None, str | None]] = []

    def fake_model_set_command(
        endpoint: str | None = None,
        model: str | None = None,
        source: str | None = None,
        **_: object,
    ) -> None:
        persisted.append((endpoint, model, source))

    def fake_ensure_runtime_for_inference(**kwargs):
        callback = kwargs["model_bootstrap_callback"]
        callback(
            RuntimeSettings(
                endpoint_url="http://127.0.0.1:8080",
                model_id="",
                model_source="",
                local_only=True,
                telemetry_enabled=False,
            )
        )
        return EnsureRuntimeResult(
            settings=RuntimeSettings(model_id="Qwen3-8B-Q8_0"),
            status=LifecycleStatus(
                lifecycle_state="running",
                ownership="managed",
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                pid=2200,
                process_group_id=2200,
                uptime_seconds=1,
                ready=True,
            ),
            health=LifecycleHealth(
                ok=True,
                endpoint_url="http://127.0.0.1:8080",
                port=8080,
                model_id="Qwen3-8B-Q8_0",
                ownership="managed",
                category=None,
                message="ok",
            ),
        )

    monkeypatch.setattr(setup_module, "model_set_command", fake_model_set_command)
    monkeypatch.setattr(
        setup_module,
        "ensure_runtime_for_inference",
        fake_ensure_runtime_for_inference,
        raising=False,
    )
    monkeypatch.setattr(setup_module, "load_settings", lambda: RuntimeSettings())

    result = RUNNER.invoke(
        setup_module.setup_app,
        [],
        input="http://127.0.0.1:8080\nQwen3-8B-Q8_0\n\nQwen3-8B-Q8_0\n",
        prog_name="aurora setup",
    )

    assert result.exit_code == 0
    assert persisted[0] == ("http://127.0.0.1:8080", "Qwen3-8B-Q8_0", None)
    assert persisted[1][1] == "Qwen3-8B-Q8_0"


def test_setup_wizard_auto_start_failure_surfaces_recovery_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    setup_module = importlib.import_module("aurora.cli.setup")

    monkeypatch.setattr(setup_module, "model_set_command", lambda **_: None)
    monkeypatch.setattr(
        setup_module,
        "ensure_runtime_for_inference",
        lambda **_: (_ for _ in ()).throw(build_runtime_error("startup_timeout")),
        raising=False,
    )

    result = RUNNER.invoke(
        setup_module.setup_app,
        [],
        input="http://127.0.0.1:8080\nQwen3-8B-Q8_0\n\nn\n",
        prog_name="aurora setup",
    )

    assert result.exit_code == 1
    assert "[startup_timeout]" in result.output
    assert "aurora model status" in result.output
    assert "aurora model start" in result.output
