"""Tests for `aurora doctor` — runtime + privacy + full-stack diagnostics.

Covers plan 05-02 task 2: extended doctor with QMD, KB, memory, disk, Python,
and package checks plus --json output (D-08, D-09, D-10, D-11, D-12).
"""
from __future__ import annotations

import importlib
import json
import types
from pathlib import Path

from typer.testing import CliRunner

from aurora.kb.manifest import KBManifest
from aurora.runtime.errors import build_runtime_error
from aurora.runtime.llama_client import RuntimeValidationResult
from aurora.runtime.settings import RuntimeSettings, save_settings


RUNNER = CliRunner()


def _install_all_passing_monkeypatches(monkeypatch, doctor_module) -> None:
    """Install monkeypatches that make every doctor check pass.

    Used by tests that want to start from a clean 'everything green' state and
    then flip one specific check to failure mode.
    """
    # Runtime validation (existing): succeed
    monkeypatch.setattr(
        doctor_module,
        "validate_runtime",
        lambda *_: RuntimeValidationResult(
            endpoint_state="ready",
            model_id="Qwen3-8B-Q8_0",
            available_models=("Qwen3-8B-Q8_0",),
        ),
    )

    # Python version: sys.version_info is already >=3.13 in CI; no patch needed.

    # QMD binary + version: shutil.which returns a fake path, subprocess succeeds
    monkeypatch.setattr(
        doctor_module.shutil, "which", lambda name: "/usr/bin/qmd"
    )

    def _fake_subprocess_run(args, **kwargs):
        # Return a dummy CompletedProcess with stdout mentioning the collection name
        # so both _check_qmd_version and _check_kb_embeddings see success.
        # Second positional arg [1] is the qmd subcommand group (--version or --index).
        return types.SimpleNamespace(
            returncode=0,
            stdout="aurora-kb-managed\naurora-memory",
            stderr="",
        )

    monkeypatch.setattr(doctor_module.subprocess, "run", _fake_subprocess_run)

    # KB manifest: return a non-empty manifest
    monkeypatch.setattr(
        doctor_module,
        "load_kb_manifest",
        lambda: KBManifest(vault_root="/tmp/vault", notes={"note.md": _dummy_note()}),
    )

    # Memory store: return empty list (valid — no memory issue)
    import aurora.memory.store as memory_store_mod

    class _EmptyMemoryStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_memories(self) -> list[dict]:
            return []

    monkeypatch.setattr(memory_store_mod, "EpisodicMemoryStore", _EmptyMemoryStore)

    # Disk space: return plenty free
    monkeypatch.setattr(
        doctor_module.shutil,
        "disk_usage",
        lambda _path: types.SimpleNamespace(
            total=100 * 1024 * 1024 * 1024,
            used=1 * 1024 * 1024 * 1024,
            free=50 * 1024 * 1024 * 1024,
        ),
    )


def _dummy_note():
    from aurora.kb.manifest import KBManifestNoteRecord

    return KBManifestNoteRecord(
        size=10,
        mtime_ns=1,
        sha256=None,
        indexed_at="2026-04-11T00:00:00Z",
        cleaned_size=10,
        templater_tags_removed=0,
    )


# ---------------------------------------------------------------------------
# Existing tests (kept, but happy-path now monkeypatches all new checks)
# ---------------------------------------------------------------------------


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
    _install_all_passing_monkeypatches(monkeypatch, doctor_module)

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 0, result.output
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
    _install_all_passing_monkeypatches(monkeypatch, doctor_module)

    # Flip runtime validation to raise the model-missing diagnostic
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


# ---------------------------------------------------------------------------
# New tests for extended checks (plan 05-02 task 2)
# ---------------------------------------------------------------------------


def test_doctor_reports_qmd_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)
    # Override: shutil.which returns None for qmd
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: None)

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 1, result.output
    assert "qmd" in result.output.lower()
    assert "pip install qmd" in result.output


def test_doctor_reports_kb_no_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)
    # Override: manifest returns None (no KB manifest on disk yet)
    monkeypatch.setattr(doctor_module, "load_kb_manifest", lambda: None)

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 1, result.output
    lower = result.output.lower()
    assert "manifesto kb" in lower or "indexacao" in lower


def test_doctor_reports_python_version_ok(tmp_path: Path, monkeypatch) -> None:
    """Python 3.13+ should not produce a python_version issue in a normal run."""
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    assert "python 3." not in result.output.lower()  # No python version complaint
    assert "requer python" not in result.output.lower()


def test_doctor_json_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)
    # Force an issue: qmd missing
    monkeypatch.setattr(doctor_module.shutil, "which", lambda name: None)

    result = RUNNER.invoke(app_module.app, ["doctor", "--json"], prog_name="aurora")

    assert result.exit_code == 1, result.output
    parsed = json.loads(result.output)
    assert parsed["ok"] is False
    assert isinstance(parsed["issues"], list)
    assert len(parsed["issues"]) >= 1
    first = parsed["issues"][0]
    assert "category" in first
    assert "message" in first
    assert "recovery_commands" in first


def test_doctor_json_all_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)

    result = RUNNER.invoke(app_module.app, ["doctor", "--json"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["ok"] is True
    assert parsed["issues"] == []
    assert "checks" in parsed
    assert "endpoint" in parsed["checks"]
    assert "model" in parsed["checks"]
    assert "local_only" in parsed["checks"]
    assert "telemetry_enabled" in parsed["checks"]


def test_doctor_checks_disk_space(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)
    # Override: disk_usage returns low free space (100 MB — below 500 MB threshold)
    monkeypatch.setattr(
        doctor_module.shutil,
        "disk_usage",
        lambda _path: types.SimpleNamespace(
            total=10 * 1024 * 1024 * 1024,
            used=9 * 1024 * 1024 * 1024,
            free=100 * 1024 * 1024,
        ),
    )

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 1, result.output
    lower = result.output.lower()
    assert "espaco" in lower or "disco" in lower


def test_doctor_reports_kb_embeddings_missing(tmp_path: Path, monkeypatch) -> None:
    """QMD exists but the managed collection is missing from its output."""
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")
    save_settings(RuntimeSettings())

    _install_all_passing_monkeypatches(monkeypatch, doctor_module)
    # Override subprocess.run to return stdout WITHOUT the aurora collection names
    monkeypatch.setattr(
        doctor_module.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0, stdout="other-collection\n", stderr=""
        ),
    )

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 1, result.output
    lower = result.output.lower()
    assert "embeddings" in lower or "colecao" in lower
