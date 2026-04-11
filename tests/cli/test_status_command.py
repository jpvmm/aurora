"""Tests for `aurora status` — unified dashboard (plan 05-02 task 1).

Covers D-05, D-06, D-07, D-11, D-16:
- Text dashboard with model, KB, memory, config sections
- --json output with structured keys
- Graceful degradation when services raise
- Report-only: does NOT call ServerLifecycleService.check_health
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from typer.testing import CliRunner

from aurora.runtime.server_lifecycle import LifecycleStatus
from aurora.runtime.settings import RuntimeSettings, save_settings


RUNNER = CliRunner()


def _fake_lifecycle_status(**overrides: object) -> LifecycleStatus:
    defaults: dict[str, object] = {
        "lifecycle_state": "stopped",
        "ownership": None,
        "endpoint_url": "http://127.0.0.1:8080",
        "port": 8080,
        "model_id": "test-model",
        "pid": None,
        "process_group_id": None,
        "uptime_seconds": None,
        "ready": False,
        "message": None,
        "error_category": None,
        "recovery_commands": (),
    }
    defaults.update(overrides)
    return LifecycleStatus(**defaults)  # type: ignore[arg-type]


def _install_happy_path_monkeypatches(monkeypatch, status_module) -> None:
    """Install monkeypatches that make all status sub-sections succeed with empty/default values."""

    class _FakeLifecycleService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_status(self) -> LifecycleStatus:
            return _fake_lifecycle_status()

    # Patch ServerLifecycleService as imported inside _run_status via lazy import — we need
    # to patch it in the runtime module since status.py imports it lazily.
    import aurora.runtime.server_lifecycle as lifecycle_mod

    monkeypatch.setattr(lifecycle_mod, "ServerLifecycleService", _FakeLifecycleService)

    import aurora.kb.manifest as kb_manifest_mod

    monkeypatch.setattr(kb_manifest_mod, "load_kb_manifest", lambda: None)

    import aurora.memory.store as memory_store_mod

    class _FakeMemoryStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_memories(self) -> list[dict]:
            return []

    monkeypatch.setattr(memory_store_mod, "EpisodicMemoryStore", _FakeMemoryStore)


def test_status_renders_text_dashboard(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    status_module = importlib.import_module("aurora.cli.status")

    save_settings(RuntimeSettings())
    _install_happy_path_monkeypatches(monkeypatch, status_module)

    result = RUNNER.invoke(app_module.app, ["status"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    # Model section header
    assert "Modelo" in result.output or "modelo" in result.output
    # Stopped state rendered
    assert "stopped" in result.output.lower() or "desconhecido" in result.output.lower()
    # KB section present
    assert "Base de Conhecimento" in result.output or "notas indexadas" in result.output
    # Memory section present
    assert "Memoria" in result.output or "memorias" in result.output
    # Config section present
    assert "Configuracao" in result.output or "local-only" in result.output
    # Version header present
    assert "Aurora" in result.output


def test_status_json_returns_structured_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    status_module = importlib.import_module("aurora.cli.status")

    save_settings(RuntimeSettings())
    _install_happy_path_monkeypatches(monkeypatch, status_module)

    result = RUNNER.invoke(app_module.app, ["status", "--json"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert "version" in parsed
    assert "model" in parsed
    assert "kb" in parsed
    assert "memory" in parsed
    assert "config" in parsed
    assert isinstance(parsed["model"]["state"], str)
    assert isinstance(parsed["kb"]["note_count"], int)
    assert isinstance(parsed["memory"]["memory_count"], int)
    assert isinstance(parsed["config"]["local_only"], bool)


def test_status_gracefully_handles_missing_services(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    importlib.import_module("aurora.cli.status")
    save_settings(RuntimeSettings())

    # All services raise on access — status must not crash
    import aurora.runtime.server_lifecycle as lifecycle_mod

    class _ExplodingService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_status(self) -> LifecycleStatus:
            raise RuntimeError("lifecycle connection failed")

    monkeypatch.setattr(lifecycle_mod, "ServerLifecycleService", _ExplodingService)

    import aurora.kb.manifest as kb_manifest_mod

    def _raise_manifest() -> None:
        raise RuntimeError("manifest broken")

    monkeypatch.setattr(kb_manifest_mod, "load_kb_manifest", _raise_manifest)

    import aurora.memory.store as memory_store_mod

    class _ExplodingMemoryStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_memories(self) -> list[dict]:
            raise RuntimeError("no memory dir")

    monkeypatch.setattr(memory_store_mod, "EpisodicMemoryStore", _ExplodingMemoryStore)

    result = RUNNER.invoke(app_module.app, ["status"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    # Partial dashboard — at least section headers still render
    assert "Modelo" in result.output or "modelo" in result.output
    assert "Base de Conhecimento" in result.output or "notas indexadas" in result.output
    assert "Memoria" in result.output or "memorias" in result.output


def test_status_does_not_call_check_health(tmp_path: Path, monkeypatch) -> None:
    """Per D-06: status must be report-only. Must NOT trigger network probes."""
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    importlib.import_module("aurora.cli.status")
    save_settings(RuntimeSettings())

    check_health_called: dict[str, bool] = {"called": False}

    class _TrackingService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_status(self) -> LifecycleStatus:
            return _fake_lifecycle_status()

        def check_health(self):
            check_health_called["called"] = True
            raise AssertionError(
                "check_health must not be called from aurora status (D-06)"
            )

    import aurora.runtime.server_lifecycle as lifecycle_mod

    monkeypatch.setattr(lifecycle_mod, "ServerLifecycleService", _TrackingService)

    import aurora.kb.manifest as kb_manifest_mod

    monkeypatch.setattr(kb_manifest_mod, "load_kb_manifest", lambda: None)

    import aurora.memory.store as memory_store_mod

    class _FakeMemoryStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_memories(self) -> list[dict]:
            return []

    monkeypatch.setattr(memory_store_mod, "EpisodicMemoryStore", _FakeMemoryStore)

    result = RUNNER.invoke(app_module.app, ["status"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    assert check_health_called["called"] is False, (
        "aurora status triggered a network probe via check_health — violates D-06"
    )
