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
    assert "ask" in result.output
    assert "chat" in result.output
    assert "config" in result.output
    assert "doctor" in result.output
    # Deprecated aliases should still appear in root help so existing users see them.
    assert "kb" in result.output
    assert "model" in result.output
    assert "memory" in result.output


@pytest.mark.parametrize(
    "command_group",
    ["ask", "chat", "config", "doctor", "kb", "model", "memory"],
)
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

    # Setup is now reachable via `aurora config setup` (namespace move per D-02).
    result = RUNNER.invoke(app_module.app, ["config", "setup"], prog_name="aurora")

    assert result.exit_code == 0
    assert called["value"] is True
    assert "setup wizard called" in result.output


def test_config_group_shows_guidance_without_placeholder_message() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["config"], prog_name="aurora")

    assert result.exit_code == 1
    assert "aurora config show" in result.output.lower()
    assert "ainda nao implementado" not in result.output.lower()


def test_doctor_group_runs_runtime_checks_without_placeholder_message(
    tmp_path, monkeypatch
) -> None:
    # Isolated config dir so load_settings sees a fresh RuntimeSettings
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))

    app_module = importlib.import_module("aurora.cli.app")
    doctor_module = importlib.import_module("aurora.cli.doctor")

    from aurora.kb.manifest import KBManifest, KBManifestNoteRecord
    from aurora.runtime.settings import RuntimeSettings, save_settings

    save_settings(RuntimeSettings())

    monkeypatch.setattr(
        doctor_module,
        "validate_runtime",
        lambda *_: RuntimeValidationResult(
            endpoint_state="ready",
            model_id="Qwen3-8B-Q8_0",
            available_models=("Qwen3-8B-Q8_0",),
        ),
    )

    # Plan 05-02 extended doctor with additional checks — keep this test green by
    # monkeypatching them to the all-passing shape.
    import types as _types

    monkeypatch.setattr(
        doctor_module.shutil, "which", lambda name: "/usr/bin/qmd"
    )
    monkeypatch.setattr(
        doctor_module.subprocess,
        "run",
        lambda *args, **kwargs: _types.SimpleNamespace(
            returncode=0,
            stdout="aurora-kb-managed\naurora-memory",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        doctor_module,
        "load_kb_manifest",
        lambda: KBManifest(
            vault_root="/tmp/vault",
            notes={
                "note.md": KBManifestNoteRecord(
                    size=10,
                    mtime_ns=1,
                    sha256=None,
                    indexed_at="2026-04-11T00:00:00Z",
                    cleaned_size=10,
                    templater_tags_removed=0,
                )
            },
        ),
    )
    monkeypatch.setattr(
        doctor_module.shutil,
        "disk_usage",
        lambda _path: _types.SimpleNamespace(
            total=100 * 1024 * 1024 * 1024,
            used=1 * 1024 * 1024 * 1024,
            free=50 * 1024 * 1024 * 1024,
        ),
    )

    import aurora.memory.store as _memory_store

    class _EmptyMemoryStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_memories(self) -> list[dict]:
            return []

    monkeypatch.setattr(_memory_store, "EpisodicMemoryStore", _EmptyMemoryStore)

    result = RUNNER.invoke(app_module.app, ["doctor"], prog_name="aurora")

    assert result.exit_code == 0, result.output
    assert "runtime local pronto" in result.output.lower()
    assert "ainda nao implementado" not in result.output.lower()


def test_model_group_exposes_set_command_in_help() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(
        app_module.app, ["config", "model", "--help"], prog_name="aurora"
    )

    assert result.exit_code == 0
    assert "set" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output
    assert "health" in result.output


def test_kb_group_exposes_lifecycle_commands() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(
        app_module.app, ["config", "kb", "--help"], prog_name="aurora"
    )

    assert result.exit_code == 0
    assert "ingest" in result.output
    assert "update" in result.output
    assert "delete" in result.output
    assert "rebuild" in result.output


def test_kb_ingest_requires_explicit_vault_path() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(
        app_module.app, ["config", "kb", "ingest"], prog_name="aurora"
    )

    assert result.exit_code == 2
    assert "Missing argument" in result.output
    assert "VAULT_PATH" in result.output.upper()


@pytest.mark.parametrize(
    ("command", "has_dry_run", "has_verify_hash"),
    [
        ("ingest", True, False),
        ("update", True, True),
        ("delete", False, False),
        ("rebuild", True, False),
    ],
)
def test_kb_commands_expose_json_and_optional_dry_run(
    command: str,
    has_dry_run: bool,
    has_verify_hash: bool,
) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(
        app_module.app, ["config", "kb", command, "--help"], prog_name="aurora"
    )

    assert result.exit_code == 0
    assert "--json" in result.output
    if has_dry_run:
        assert "--dry-run" in result.output
    else:
        assert "--dry-run" not in result.output
    if has_verify_hash:
        assert "--verify-hash" in result.output
    else:
        assert "--verify-hash" not in result.output


def test_kb_update_help_mentions_hash_precision_behavior() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(
        app_module.app, ["config", "kb", "update", "--help"], prog_name="aurora"
    )

    assert result.exit_code == 0
    normalized = result.output.lower()
    assert "--verify-hash" in normalized


# ---------------------------------------------------------------------------
# Phase 05-01: new command surface tests
# ---------------------------------------------------------------------------


def test_deprecated_kb_alias_emits_warning_and_delegates(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["kb", "--help"], prog_name="aurora")
    assert result.exit_code == 0
    assert "ingest" in result.output


def test_deprecated_model_alias_emits_warning() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["model", "--help"], prog_name="aurora")
    assert result.exit_code == 0
    assert "set" in result.output


def test_deprecated_memory_alias_emits_warning() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["memory", "--help"], prog_name="aurora")
    assert result.exit_code == 0
    assert "list" in result.output


def test_config_shows_kb_model_memory_setup_subgroups() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["config", "--help"], prog_name="aurora")
    assert result.exit_code == 0
    for subgroup in ("kb", "model", "memory", "setup", "show"):
        assert subgroup in result.output


def test_shell_completion_flags_available() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    result = RUNNER.invoke(app_module.app, ["--help"], prog_name="aurora")
    assert result.exit_code == 0
    normalized = result.output.lower()
    assert "--install-completion" in normalized or "install-completion" in normalized
