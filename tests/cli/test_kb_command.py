from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aurora.kb.contracts import (
    KBEmbeddingStageStatus,
    KBFileDiagnostic,
    KBOperationCounters,
    KBOperationSummary,
    KBScopeConfig,
)
from aurora.kb.manifest import (
    KBManifest,
    KBManifestNoteRecord,
    KBManifestStateError,
)
from aurora.kb.service import KBService
from aurora.kb.service import KBServiceError
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings


RUNNER = CliRunner()
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\].*?\x07")


def _summary(
    *,
    operation: str,
    dry_run: bool = False,
    embedding: KBEmbeddingStageStatus | None = None,
) -> KBOperationSummary:
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
        embedding=embedding,
    )


def _write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _normalized_output(output: str) -> str:
    return ANSI_ESCAPE_RE.sub("", output).lower()


@dataclass
class FakeKBService:
    ingest_calls: list[dict[str, object]] = field(default_factory=list)
    update_calls: list[dict[str, object]] = field(default_factory=list)
    delete_calls: list[dict[str, object]] = field(default_factory=list)
    rebuild_calls: list[dict[str, object]] = field(default_factory=list)

    @staticmethod
    def _emit_standard_progress(
        on_progress,
        *,
        read: int,
        indexed: int,
        updated: int,
        removed: int,
        skipped: int,
        errors: int,
    ) -> None:
        if on_progress is None:
            return
        on_progress(
            "scan",
            KBOperationCounters(read=read, indexed=0, updated=0, removed=0, skipped=skipped, errors=0),
        )
        on_progress(
            "preprocess",
            KBOperationCounters(read=read, indexed=0, updated=0, removed=0, skipped=skipped, errors=errors),
        )
        on_progress(
            "done",
            KBOperationCounters(
                read=read,
                indexed=indexed,
                updated=updated,
                removed=removed,
                skipped=skipped,
                errors=errors,
            ),
        )

    def run_ingest(self, *, vault_path: str, dry_run: bool, on_progress):
        self.ingest_calls.append({"vault_path": vault_path, "dry_run": dry_run})
        self._emit_standard_progress(
            on_progress,
            read=4,
            indexed=2,
            updated=0,
            removed=1,
            skipped=1,
            errors=0,
        )
        return _summary(operation="ingest", dry_run=dry_run)

    def run_update(self, *, dry_run: bool, verify_hash: bool, on_progress):
        self.update_calls.append({"dry_run": dry_run, "verify_hash": verify_hash})
        self._emit_standard_progress(
            on_progress,
            read=4,
            indexed=2,
            updated=1,
            removed=1,
            skipped=1,
            errors=0,
        )
        return _summary(operation="update", dry_run=dry_run)

    def run_delete(self, *, on_progress):
        self.delete_calls.append({})
        self._emit_standard_progress(
            on_progress,
            read=0,
            indexed=0,
            updated=0,
            removed=1,
            skipped=0,
            errors=0,
        )
        return _summary(operation="delete")

    def run_rebuild(self, *, dry_run: bool, on_progress):
        self.rebuild_calls.append({"dry_run": dry_run})
        self._emit_standard_progress(
            on_progress,
            read=4,
            indexed=2,
            updated=0,
            removed=1,
            skipped=1,
            errors=0,
        )
        return _summary(operation="rebuild", dry_run=dry_run)


def test_ingest_command_delegates_to_service_and_renders_text_progress(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)

    result = RUNNER.invoke(app_module.app, ["config", "kb", "ingest", "/tmp/vault"], prog_name="aurora")

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
        ["config", "kb", "update", "--verify-hash", "--json"],
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

    result = RUNNER.invoke(app_module.app, ["config", "kb", "delete", "--yes"], prog_name="aurora")

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

    result = RUNNER.invoke(app_module.app, ["config", "kb", "rebuild"], prog_name="aurora")

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

    result = RUNNER.invoke(app_module.app, ["config", "kb", "update"], prog_name="aurora")

    assert result.exit_code == 0
    output = result.output.lower()
    assert "path=notes/protected.md" in output
    assert "category=file_read_error" in output
    assert "aurora kb update" in output
    assert "totais: read=1 indexed=0 updated=0 removed=0 skipped=1 errors=1" in output
    assert "conteudo sigiloso da nota" not in output


@pytest.mark.parametrize(
    ("command", "expected_operation"),
    [
        (["config", "kb", "ingest", "/tmp/vault"], "ingest"),
        (["config", "kb", "update"], "update"),
        (["config", "kb", "delete", "--yes"], "delete"),
        (["config", "kb", "rebuild"], "rebuild"),
    ],
)
def test_kb_readability_progress_stage_order_and_summary_tokens_for_each_operation(
    monkeypatch,
    command: list[str],
    expected_operation: str,
) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)

    result = RUNNER.invoke(app_module.app, command, prog_name="aurora")

    assert result.exit_code == 0
    output = _normalized_output(result.output)
    scan_idx = output.find("etapa: scan")
    preprocess_idx = output.find("etapa: preprocess")
    done_idx = output.find("etapa: done")
    assert scan_idx != -1
    assert preprocess_idx != -1
    assert done_idx != -1
    assert scan_idx < preprocess_idx < done_idx
    assert f"operacao: {expected_operation}" in output
    assert "duracao_s:" in output
    assert "effective_scope:" in output
    assert "totais:" in output
    assert "conteudo sigiloso da nota" not in output


@pytest.mark.parametrize(
    ("command", "expected_operation"),
    [
        (["config", "kb", "ingest", "/tmp/vault", "--json"], "ingest"),
        (["config", "kb", "update", "--json"], "update"),
        (["config", "kb", "delete", "--json", "--yes"], "delete"),
        (["config", "kb", "rebuild", "--json"], "rebuild"),
    ],
)
def test_kb_json_summary_readability_contract_excludes_transient_progress_lines(
    monkeypatch,
    command: list[str],
    expected_operation: str,
) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)

    result = RUNNER.invoke(app_module.app, command, prog_name="aurora")

    assert result.exit_code == 0
    output = _normalized_output(result.output)
    assert "etapa:" not in output
    payload = json.loads(result.output)
    assert payload["operation"] == expected_operation
    assert "duration_seconds" in payload
    assert "scope" in payload
    assert "counters" in payload
    assert "conteudo sigiloso da nota" not in output


def test_kb_config_show_displays_detailed_settings(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        RuntimeSettings(
            kb_vault_path="/vault",
            kb_include=("notes/*.md", "daily/*.md"),
            kb_exclude=("notes/private.md",),
            kb_qmd_index_name="aurora-index",
            kb_qmd_collection_name="aurora-collection",
            kb_auto_embeddings_enabled=False,
        )
    )

    result = RUNNER.invoke(app_module.app, ["config", "kb", "config", "show"], prog_name="aurora")

    assert result.exit_code == 0
    output = result.output.lower()
    assert "configuracao kb atual" in output
    assert "vault: /vault" in output
    assert "include: ['daily/*.md', 'notes/*.md']" in output
    assert "exclude: ['notes/private.md']" in output
    assert "index: aurora-index" in output
    assert "collection: aurora-collection" in output
    assert "auto-embeddings: desativado" in output


def test_kb_config_set_updates_active_target_and_settings(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    save_settings(RuntimeSettings())

    result = RUNNER.invoke(
        app_module.app,
        [
            "kb",
            "config",
            "set",
            "--vault",
            str(vault_dir),
            "--include",
            "notes/*.md",
            "--include",
            "daily/*.md",
            "--exclude",
            "notes/private.md",
            "--index",
            "team-index",
            "--collection",
            "team-collection",
            "--no-auto-embeddings",
        ],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    settings = load_settings()
    assert settings.kb_vault_path == str(vault_dir)
    assert settings.kb_include == ("daily/*.md", "notes/*.md")
    assert settings.kb_exclude == ("notes/private.md",)
    assert settings.kb_qmd_index_name == "team-index"
    assert settings.kb_qmd_collection_name == "team-collection"
    assert settings.kb_auto_embeddings_enabled is False


def test_kb_help_and_root_help_expose_kb_config_surface(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings())

    kb_help = RUNNER.invoke(app_module.app, ["config", "kb", "--help"], prog_name="aurora")
    kb_config_help = RUNNER.invoke(app_module.app, ["config", "kb", "config", "--help"], prog_name="aurora")
    root_help = RUNNER.invoke(app_module.app, ["--help"], prog_name="aurora")

    assert kb_help.exit_code == 0
    assert kb_config_help.exit_code == 0
    assert root_help.exit_code == 0
    assert "config" in kb_help.output.lower()
    assert "show" in kb_config_help.output.lower()
    assert "set" in kb_config_help.output.lower()
    assert "kb" in root_help.output.lower()


@pytest.mark.parametrize(
    ("command", "call_attr"),
    [
        (["config", "kb", "update", "--index", "tmp-index", "--collection", "tmp-collection"], "update_calls"),
        (
            ["config", "kb", "delete", "--yes", "--index", "tmp-index", "--collection", "tmp-collection"],
            "delete_calls",
        ),
        (["config", "kb", "rebuild", "--index", "tmp-index", "--collection", "tmp-collection"], "rebuild_calls"),
    ],
)
def test_kb_command_target_overrides_are_command_scoped(
    tmp_path: Path,
    monkeypatch,
    command: list[str],
    call_attr: str,
) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        RuntimeSettings(
            kb_vault_path="/vault",
            kb_qmd_index_name="global-index",
            kb_qmd_collection_name="global-collection",
        )
    )
    fake_service = FakeKBService()
    constructor_calls: list[dict[str, object]] = []

    def factory(*, index_name: str | None = None, collection_name: str | None = None):
        constructor_calls.append({"index_name": index_name, "collection_name": collection_name})
        return fake_service

    monkeypatch.setattr(kb_module, "KBService", factory)
    result = RUNNER.invoke(app_module.app, command, prog_name="aurora")

    assert result.exit_code == 0
    assert constructor_calls == [{"index_name": "tmp-index", "collection_name": "tmp-collection"}]
    assert getattr(fake_service, call_attr) != []
    persisted = load_settings()
    assert persisted.kb_qmd_index_name == "global-index"
    assert persisted.kb_qmd_collection_name == "global-collection"


def test_kb_delete_requires_yes_when_non_interactive(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings(kb_vault_path="/vault"))
    fake_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: fake_service)
    monkeypatch.setattr(kb_module, "_is_interactive_terminal", lambda: False)

    result = RUNNER.invoke(app_module.app, ["config", "kb", "delete"], prog_name="aurora")

    assert result.exit_code == 1
    output = result.output.lower()
    assert "confirmacao explicita" in output
    assert "aurora kb delete --yes" in output
    assert fake_service.delete_calls == []


def test_kb_delete_interactive_confirmation_controls_execution(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings(kb_vault_path="/vault"))
    monkeypatch.setattr(kb_module, "_is_interactive_terminal", lambda: True)

    decline_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: decline_service)
    decline = RUNNER.invoke(app_module.app, ["config", "kb", "delete"], input="n\n", prog_name="aurora")
    assert decline.exit_code == 1
    assert decline_service.delete_calls == []

    confirm_service = FakeKBService()
    monkeypatch.setattr(kb_module, "KBService", lambda: confirm_service)
    confirm = RUNNER.invoke(app_module.app, ["config", "kb", "delete"], input="y\n", prog_name="aurora")
    assert confirm.exit_code == 0
    assert confirm_service.delete_calls == [{}]


def test_update_text_output_reports_embed_partial_failure_warning_and_exit_policy(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    class PartialFailureService(FakeKBService):
        def run_update(self, *, dry_run: bool, verify_hash: bool, on_progress):
            return _summary(
                operation="update",
                dry_run=dry_run,
                embedding=KBEmbeddingStageStatus(
                    attempted=True,
                    ok=False,
                    category="backend_embed_failed",
                    recovery_command="aurora kb update",
                ),
            )

    monkeypatch.setattr(kb_module, "KBService", lambda: PartialFailureService())
    result = RUNNER.invoke(app_module.app, ["config", "kb", "update"], prog_name="aurora")

    assert result.exit_code == 2
    output = result.output.lower()
    assert "warning: embeddings desatualizados" in output
    assert "aurora kb update" in output


def test_update_text_output_reports_embed_success(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    class EmbedSuccessService(FakeKBService):
        def run_update(self, *, dry_run: bool, verify_hash: bool, on_progress):
            return _summary(
                operation="update",
                dry_run=dry_run,
                embedding=KBEmbeddingStageStatus(attempted=True, ok=True),
            )

    monkeypatch.setattr(kb_module, "KBService", lambda: EmbedSuccessService())
    result = RUNNER.invoke(app_module.app, ["config", "kb", "update"], prog_name="aurora")

    assert result.exit_code == 0
    assert "embedding: atualizado" in result.output.lower()


def test_update_json_output_includes_embedding_stage_fields(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    class JsonEmbedService(FakeKBService):
        def run_update(self, *, dry_run: bool, verify_hash: bool, on_progress):
            return _summary(
                operation="update",
                dry_run=dry_run,
                embedding=KBEmbeddingStageStatus(
                    attempted=True,
                    ok=False,
                    category="backend_embed_failed",
                    recovery_command="aurora kb update",
                ),
            )

    monkeypatch.setattr(kb_module, "KBService", lambda: JsonEmbedService())
    result = RUNNER.invoke(app_module.app, ["config", "kb", "update", "--json"], prog_name="aurora")

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["embedding"] == {
        "attempted": True,
        "ok": False,
        "category": "backend_embed_failed",
        "recovery_command": "aurora kb update",
    }


@dataclass
class FakeSchedulerStatus:
    enabled: bool
    local_hour: int
    timezone_name: str
    next_due_at: datetime | None
    catch_up_eligible: bool
    last_planned_slot_at: datetime | None
    last_run_started_at: datetime | None
    last_run_completed_at: datetime | None
    last_run_ok: bool | None
    last_run_reason: str | None
    last_error_category: str | None


def test_kb_scheduler_status_json_contract(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    expected_status = FakeSchedulerStatus(
        enabled=True,
        local_hour=7,
        timezone_name="UTC",
        next_due_at=datetime(2026, 3, 6, 7, 0, tzinfo=UTC),
        catch_up_eligible=False,
        last_planned_slot_at=datetime(2026, 3, 5, 7, 0, tzinfo=UTC),
        last_run_started_at=datetime(2026, 3, 5, 7, 0, tzinfo=UTC),
        last_run_completed_at=datetime(2026, 3, 5, 7, 0, tzinfo=UTC),
        last_run_ok=True,
        last_run_reason="scheduled",
        last_error_category=None,
    )

    class FakeSchedulerService:
        def status(self, *, now=None):
            return expected_status

    monkeypatch.setattr(kb_module, "KBSchedulerService", FakeSchedulerService)
    result = RUNNER.invoke(app_module.app, ["config", "kb", "scheduler", "status", "--json"], prog_name="aurora")

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["enabled"] is True
    assert payload["local_hour"] == 7
    assert payload["timezone"] == "UTC"
    assert payload["next_due_at"] == "2026-03-06T07:00:00Z"
    assert payload["last_run_ok"] is True
    assert payload["last_run_reason"] == "scheduled"
    assert payload["catch_up_eligible"] is False


def test_kb_scheduler_enable_disable_status_text(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    class FakeSchedulerService:
        def __init__(self):
            self._enabled = False
            self._hour = 9

        def enable(self, *, hour_local=None, now=None):
            self._enabled = True
            if hour_local is not None:
                self._hour = hour_local
            return self.status()

        def disable(self, *, now=None):
            self._enabled = False
            return self.status()

        def status(self, *, now=None):
            return FakeSchedulerStatus(
                enabled=self._enabled,
                local_hour=self._hour,
                timezone_name="UTC",
                next_due_at=datetime(2026, 3, 6, self._hour, 0, tzinfo=UTC),
                catch_up_eligible=False,
                last_planned_slot_at=None,
                last_run_started_at=None,
                last_run_completed_at=None,
                last_run_ok=None,
                last_run_reason=None,
                last_error_category=None,
            )

    fake = FakeSchedulerService()
    monkeypatch.setattr(kb_module, "KBSchedulerService", lambda: fake)

    enabled = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "scheduler", "enable", "--hour", "7"],
        prog_name="aurora",
    )
    disabled = RUNNER.invoke(app_module.app, ["config", "kb", "scheduler", "disable"], prog_name="aurora")
    status = RUNNER.invoke(app_module.app, ["config", "kb", "scheduler", "status"], prog_name="aurora")

    assert enabled.exit_code == 0
    assert disabled.exit_code == 0
    assert status.exit_code == 0
    assert "scheduler: desativado" in status.output.lower()
    assert "hora_local: 7" in enabled.output.lower()
    assert "proxima_execucao" in status.output.lower()


def test_kb_scheduler_command_surfaces_actionable_recovery(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    class RaisingSchedulerService:
        def status(self, *, now=None):
            raise KBServiceError(
                category="vault_not_configured",
                message="Vault nao configurado para scheduler.",
                recovery_commands=("aurora kb config set --vault /meu/vault",),
            )

    monkeypatch.setattr(kb_module, "KBSchedulerService", RaisingSchedulerService)
    result = RUNNER.invoke(app_module.app, ["config", "kb", "scheduler", "status"], prog_name="aurora")

    assert result.exit_code == 1
    output = result.output.lower()
    assert "vault_not_configured" in output
    assert "aurora kb config set --vault /meu/vault" in output


def test_kb_scheduler_help_surface_is_discoverable() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_help = RUNNER.invoke(app_module.app, ["config", "kb", "--help"], prog_name="aurora")
    scheduler_help = RUNNER.invoke(app_module.app, ["config", "kb", "scheduler", "--help"], prog_name="aurora")

    assert kb_help.exit_code == 0
    assert scheduler_help.exit_code == 0
    assert "scheduler" in kb_help.output.lower()
    assert "enable" in scheduler_help.output.lower()
    assert "disable" in scheduler_help.output.lower()
    assert "status" in scheduler_help.output.lower()


def _note_record(*, indexed_at: str, size: int = 100, cleaned_size: int = 90) -> KBManifestNoteRecord:
    return KBManifestNoteRecord(
        size=size,
        mtime_ns=1_700_000_000_000_000_000,
        sha256="deadbeef",
        indexed_at=indexed_at,
        cleaned_size=cleaned_size,
        templater_tags_removed=0,
    )


def test_kb_recent_renders_notes_sorted_by_indexed_at_desc_with_limit(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    manifest = KBManifest(
        vault_root="/tmp/vault",
        notes={
            "notes/old.md": _note_record(indexed_at="2026-04-10T08:00:00Z"),
            "notes/new.md": _note_record(indexed_at="2026-04-20T15:00:00Z"),
            "notes/mid.md": _note_record(indexed_at="2026-04-15T12:00:00Z"),
        },
    )
    monkeypatch.setattr(kb_module, "load_kb_manifest", lambda: manifest)

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "recent", "--limit", "2"],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    output = result.output
    assert "vault: /tmp/vault" in output
    assert "notas recentes: 2 de 3" in output
    new_idx = output.find("notes/new.md")
    mid_idx = output.find("notes/mid.md")
    old_idx = output.find("notes/old.md")
    assert new_idx != -1
    assert mid_idx != -1
    assert old_idx == -1  # trimmed by limit
    assert new_idx < mid_idx


def test_kb_recent_json_output_schema_and_ordering(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    manifest = KBManifest(
        vault_root="/tmp/vault",
        notes={
            "a.md": _note_record(indexed_at="2026-04-01T00:00:00Z"),
            "b.md": _note_record(indexed_at="2026-04-02T00:00:00Z"),
        },
    )
    monkeypatch.setattr(kb_module, "load_kb_manifest", lambda: manifest)

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "recent", "--json"],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["vault_root"] == "/tmp/vault"
    assert payload["total"] == 2
    assert payload["count"] == 2
    paths = [item["path"] for item in payload["notes"]]
    assert paths == ["b.md", "a.md"]
    first = payload["notes"][0]
    assert set(first.keys()) == {
        "path",
        "indexed_at",
        "size",
        "cleaned_size",
        "mtime_ns",
        "sha256",
        "templater_tags_removed",
    }


def test_kb_recent_when_manifest_missing_suggests_ingest_recovery(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")
    monkeypatch.setattr(kb_module, "load_kb_manifest", lambda: None)

    result = RUNNER.invoke(app_module.app, ["config", "kb", "recent"], prog_name="aurora")

    assert result.exit_code == 0
    output = result.output.lower()
    assert "nenhum manifesto kb encontrado" in output
    assert "aurora config kb ingest" in output


def test_kb_recent_when_manifest_corrupted_surfaces_recovery_commands(monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_module = importlib.import_module("aurora.cli.kb")

    def _raise() -> KBManifest:
        raise KBManifestStateError(
            message="Manifesto corrompido.",
            recovery_commands=("aurora kb rebuild",),
        )

    monkeypatch.setattr(kb_module, "load_kb_manifest", _raise)

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "recent", "--json"],
        prog_name="aurora",
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["message"] == "Manifesto corrompido."
    assert payload["recovery_commands"] == ["aurora kb rebuild"]


def test_kb_config_set_rejects_vault_with_embedded_newline(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings())
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    pasted = f"{vault_dir.parent}\n  {vault_dir.name}"

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "config", "set", "--vault", pasted],
        prog_name="aurora",
    )

    assert result.exit_code == 1
    output = result.output.lower()
    assert "quebra de linha" in output
    assert not load_settings().kb_vault_path


def test_kb_config_set_rejects_nonexistent_vault(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings())
    ghost = tmp_path / "does-not-exist"

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "config", "set", "--vault", str(ghost)],
        prog_name="aurora",
    )

    assert result.exit_code == 1
    assert "nao existe" in result.output.lower()
    assert not load_settings().kb_vault_path


def test_kb_config_set_rejects_vault_pointing_at_file(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings())
    not_a_dir = tmp_path / "notes.md"
    not_a_dir.write_text("conteudo", encoding="utf-8")

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "config", "set", "--vault", str(not_a_dir)],
        prog_name="aurora",
    )

    assert result.exit_code == 1
    assert "nao e um diretorio" in result.output.lower()
    assert not load_settings().kb_vault_path


def test_kb_config_set_expands_tilde_and_persists_absolute_vault(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("aurora.cli.app")
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path))
    save_settings(RuntimeSettings())
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    result = RUNNER.invoke(
        app_module.app,
        ["config", "kb", "config", "set", "--vault", "~/vault"],
        prog_name="aurora",
    )

    assert result.exit_code == 0
    assert load_settings().kb_vault_path == str(vault_dir)


def test_kb_recent_is_discoverable_in_help() -> None:
    app_module = importlib.import_module("aurora.cli.app")
    kb_help = RUNNER.invoke(app_module.app, ["config", "kb", "--help"], prog_name="aurora")
    recent_help = RUNNER.invoke(app_module.app, ["config", "kb", "recent", "--help"], prog_name="aurora")

    assert kb_help.exit_code == 0
    assert recent_help.exit_code == 0
    assert "recent" in kb_help.output.lower()
    assert "--limit" in recent_help.output.lower()
    assert "--json" in recent_help.output.lower()
