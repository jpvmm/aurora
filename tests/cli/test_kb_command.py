from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from typer.testing import CliRunner

from aurora.kb.contracts import KBFileDiagnostic, KBOperationCounters, KBOperationSummary, KBScopeConfig
from aurora.kb.service import KBService
from aurora.kb.service import KBServiceError
from aurora.runtime.settings import RuntimeSettings, save_settings


RUNNER = CliRunner()


def _summary(*, operation: str, dry_run: bool = False) -> KBOperationSummary:
    return KBOperationSummary(
        operation=operation,  # type: ignore[arg-type]
        dry_run=dry_run,
        duration_seconds=1.234,
        counters=KBOperationCounters(
            read=4,
            indexed=2,
            updated=1,
            removed=1,
            skipped=1,
            errors=0,
        ),
        scope=KBScopeConfig(
            vault_root="/tmp/vault",
            include=("notes/*.md",),
            exclude=("notes/private.md",),
            default_excludes=(".obsidian/**",),
        ),
        diagnostics=(),
    )


def _write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@dataclass
class FakeKBService:
    ingest_calls: list[dict[str, object]] = field(default_factory=list)
    update_calls: list[dict[str, object]] = field(default_factory=list)
    delete_calls: list[dict[str, object]] = field(default_factory=list)
    rebuild_calls: list[dict[str, object]] = field(default_factory=list)

    def run_ingest(self, *, vault_path: str, dry_run: bool, on_progress):
        self.ingest_calls.append({"vault_path": vault_path, "dry_run": dry_run})
        if on_progress is not None:
            on_progress(
                "scan",
                KBOperationCounters(read=4, indexed=0, updated=0, removed=0, skipped=0, errors=0),
            )
        return _summary(operation="ingest", dry_run=dry_run)

    def run_update(self, *, dry_run: bool, verify_hash: bool, on_progress):
        self.update_calls.append({"dry_run": dry_run, "verify_hash": verify_hash})
        if on_progress is not None:
            on_progress(
                "delta",
                KBOperationCounters(read=4, indexed=1, updated=1, removed=1, skipped=1, errors=0),
            )
        return _summary(operation="update", dry_run=dry_run)

    def run_delete(self, *, on_progress):
        self.delete_calls.append({})
        if on_progress is not None:
            on_progress(
                "delete",
                KBOperationCounters(read=0, indexed=0, updated=0, removed=2, skipped=0, errors=0),
            )
        return _summary(operation="delete")

    def run_rebuild(self, *, dry_run: bool, on_progress):
        self.rebuild_calls.append({"dry_run": dry_run})
        if on_progress is not None:
            on_progress(
                "rebuild",
                KBOperationCounters(read=4, indexed=4, updated=0, removed=2, skipped=0, errors=0),
            )
        return _summary(operation="rebuild", dry_run=dry_run)


def test_ingest_command_delegates_to_service_and_renders_text_progress(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)

    result = RUNNER.invoke(app_module.app, ["kb", "ingest", "/tmp/vault"], prog_name="aurora")

    assert result.exit_code == 0
    assert fake_service.ingest_calls == [{"vault_path": "/tmp/vault", "dry_run": False}]
    output = result.output.lower()
    assert "etapa: scan" in output
    assert "operacao: ingest" in output
    assert "read=4 indexed=2 updated=1 removed=1 skipped=1 errors=0" in output


def test_update_json_output_is_stable_and_supports_verify_hash(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)

    result = RUNNER.invoke(
        app_module.app,
        ["kb", "update", "--verify-hash", "--json"],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    assert fake_service.update_calls == [{"dry_run": False, "verify_hash": True}]
    payload = json.loads(result.output)
    assert payload["operation"] == "update"
    assert payload["counters"] == {
        "read": 4,
        "indexed": 2,
        "updated": 1,
        "removed": 1,
        "skipped": 1,
        "errors": 0,
    }
    assert payload["scope"]["vault_root"] == "/tmp/vault"


def test_delete_command_is_index_only_and_uses_service(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)

    result = RUNNER.invoke(app_module.app, ["kb", "delete"], prog_name="aurora")

    assert result.exit_code == 0
    assert fake_service.delete_calls == [{}]
    assert "index-only" in result.output.lower()


def test_rebuild_error_output_includes_path_category_and_recovery_without_content(
    monkeypatch,
) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    class RaisingService:
        def run_rebuild(self, *, dry_run: bool, on_progress):
            raise KBServiceError(
                category="state_divergence",
                message="Divergencia de manifesto.",
                diagnostics=(
                    KBFileDiagnostic(
                        path="notes/private.md",
                        category="state_divergence",
                        recovery_hint="Execute `aurora kb rebuild`.",
                    ),
                ),
                recovery_commands=("aurora kb rebuild",),
            )

    monkeypatch.setattr(kb_module, "KBService", RaisingService)

    result = RUNNER.invoke(app_module.app, ["kb", "rebuild"], prog_name="aurora")

    assert result.exit_code == 1
    assert "notes/private.md" in result.output
    assert "state_divergence" in result.output
    assert "aurora kb rebuild" in result.output
    assert "conteudo sigiloso da nota" not in result.output.lower()


def test_update_reports_privacy_safe_read_errors_without_forcing_delete(tmp_path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    note_path = vault_path / "notes" / "protected.md"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))

    save_settings(
        RuntimeSettings(
            kb_vault_path=str(vault_path),
            kb_include=("notes/*.md",),
            kb_exclude=(),
            kb_default_excludes=(),
        )
    )
    _write_note(note_path, "conteudo sigiloso da nota\n")
    KBService().run_ingest(vault_path=str(vault_path), dry_run=False)
    note_path.write_bytes(b"\xff\xfe\xfa")

    result = RUNNER.invoke(app_module.app, ["kb", "update"], prog_name="aurora")

    assert result.exit_code == 0
    output = result.output.lower()
    assert "path=notes/protected.md" in output
    assert "category=file_read_error" in output
    assert "aurora kb update" in output
    assert "removed=0" in output
    assert "conteudo sigiloso da nota" not in output
