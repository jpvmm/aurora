from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from aurora.kb.contracts import KBPreparedNote
from aurora.kb.manifest import KBManifest, KBManifestNoteRecord, load_kb_manifest, save_kb_manifest
from aurora.kb.qmd_backend import QMDCliBackend
from aurora.kb.qmd_adapter import QMDBackendDiagnostic, QMDBackendResponse
from aurora.kb.service import KBService, KBServiceError
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings


def _write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@dataclass
class FakeBackend:
    apply_response: QMDBackendResponse = QMDBackendResponse(ok=True)
    remove_response: QMDBackendResponse = QMDBackendResponse(ok=True)
    rebuild_response: QMDBackendResponse = QMDBackendResponse(ok=True)
    embed_response: QMDBackendResponse = QMDBackendResponse(ok=True)

    def __post_init__(self) -> None:
        self.apply_calls: list[tuple[KBPreparedNote, ...]] = []
        self.remove_calls: list[tuple[str, ...]] = []
        self.rebuild_calls: list[tuple[KBPreparedNote, ...]] = []
        self.embed_calls: int = 0

    def apply(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse:
        self.apply_calls.append(notes)
        return self.apply_response

    def remove(self, paths: tuple[str, ...]) -> QMDBackendResponse:
        self.remove_calls.append(paths)
        return self.remove_response

    def rebuild(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse:
        self.rebuild_calls.append(notes)
        return self.rebuild_response

    def embed(self) -> QMDBackendResponse:
        self.embed_calls += 1
        return self.embed_response


def _configure_settings(*, config_dir: Path, vault_path: Path, auto_embeddings: bool = True) -> None:
    save_settings(
        RuntimeSettings(
            kb_vault_path=str(vault_path),
            kb_include=("notes/*.md",),
            kb_exclude=("notes/private.md",),
            kb_default_excludes=(".obsidian/**",),
            kb_auto_embeddings_enabled=auto_embeddings,
        )
    )


def test_ingest_runs_scan_scope_preprocess_and_manifest_commit(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    _write_note(vault_path / "notes" / "public.md", "## Header\n<% tp.date.now() %>\n")
    _write_note(vault_path / "notes" / "private.md", "# segredo\n")
    _write_note(vault_path / "notes" / "todo.txt", "out\n")
    _write_note(vault_path / ".obsidian" / "workspace.md", "hidden\n")

    backend = FakeBackend()
    service = KBService(backend=backend)

    summary = service.run_ingest(vault_path=str(vault_path), dry_run=False)

    assert tuple(note.relative_path for note in backend.apply_calls[0]) == ("notes/public.md",)
    assert backend.apply_calls[0][0].cleaned_text == "## Header\n\n"
    assert backend.remove_calls == []
    assert summary.counters.read == 1
    assert summary.counters.indexed == 1
    assert summary.counters.updated == 0
    assert summary.counters.removed == 0
    assert summary.counters.skipped == 3
    assert summary.counters.errors == 0
    manifest = load_kb_manifest()
    assert manifest is not None
    assert tuple(manifest.notes.keys()) == ("notes/public.md",)
    assert manifest.notes["notes/public.md"].templater_tags_removed == 1


def test_update_applies_only_changed_and_removed_notes(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)
    _write_note(vault_path / "notes" / "a.md", "alpha\n")
    _write_note(vault_path / "notes" / "b.md", "beta\n")

    backend = FakeBackend()
    service = KBService(backend=backend)
    service.run_ingest(vault_path=str(vault_path), dry_run=False)

    _write_note(vault_path / "notes" / "a.md", "alpha changed\n")
    (vault_path / "notes" / "b.md").unlink()
    _write_note(vault_path / "notes" / "c.md", "charlie\n")

    summary = service.run_update()

    assert tuple(note.relative_path for note in backend.apply_calls[-1]) == ("notes/a.md", "notes/c.md")
    assert backend.remove_calls[-1] == ("notes/b.md",)
    assert summary.counters.read == 2
    assert summary.counters.indexed == 1
    assert summary.counters.updated == 1
    assert summary.counters.removed == 1
    assert summary.counters.errors == 0
    manifest = load_kb_manifest()
    assert manifest is not None
    assert tuple(manifest.notes.keys()) == ("notes/a.md", "notes/c.md")


def test_rebuild_reprocesses_scope_and_resets_stale_state(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)

    _write_note(vault_path / "notes" / "only.md", "content\n")
    save_kb_manifest(
        KBManifest(
            vault_root=str(vault_path),
            notes={
                "notes/stale.md": KBManifestNoteRecord(
                    size=1,
                    mtime_ns=1,
                    sha256="old",
                    indexed_at="2026-03-03T23:00:00Z",
                    cleaned_size=1,
                    templater_tags_removed=0,
                )
            },
        )
    )

    backend = FakeBackend()
    service = KBService(backend=backend)
    summary = service.run_rebuild()

    assert tuple(note.relative_path for note in backend.rebuild_calls[0]) == ("notes/only.md",)
    assert summary.counters.indexed == 1
    assert summary.counters.removed == 1
    manifest = load_kb_manifest()
    assert manifest is not None
    assert tuple(manifest.notes.keys()) == ("notes/only.md",)


def test_update_fails_fast_on_manifest_divergence(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)
    _write_note(vault_path / "notes" / "a.md", "alpha\n")

    save_kb_manifest(
        KBManifest(
            vault_root=str(tmp_path / "other-vault"),
            notes={
                "notes/a.md": KBManifestNoteRecord(
                    size=1,
                    mtime_ns=1,
                    sha256=None,
                    indexed_at="2026-03-03T23:00:00Z",
                    cleaned_size=1,
                    templater_tags_removed=0,
                )
            },
        )
    )

    service = KBService(backend=FakeBackend())

    with pytest.raises(KBServiceError) as error:
        service.run_update()

    assert error.value.category == "state_divergence"
    assert any("aurora kb rebuild" in hint for hint in error.value.recovery_commands)


def test_adapter_diagnostics_surface_as_service_error(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)
    _write_note(vault_path / "notes" / "a.md", "alpha\n")

    service = KBService(
        backend=FakeBackend(
            apply_response=QMDBackendResponse(
                ok=False,
                diagnostics=(
                    QMDBackendDiagnostic(
                        path="notes/a.md",
                        category="backend_apply_failed",
                        recovery_hint="Execute `aurora kb rebuild`.",
                    ),
                ),
            )
        )
    )

    with pytest.raises(KBServiceError) as error:
        service.run_ingest(vault_path=str(vault_path))

    assert error.value.category == "backend_apply_failed"
    assert error.value.diagnostics[0].path == "notes/a.md"


def test_update_keeps_manifest_entry_when_note_has_noncritical_read_error(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path)
    note_path = vault_path / "notes" / "protected.md"
    _write_note(note_path, "conteudo original\n")

    service = KBService(backend=FakeBackend())
    service.run_ingest(vault_path=str(vault_path), dry_run=False)

    note_path.write_bytes(b"\xff\xfe\xfa")
    summary = service.run_update()

    assert summary.counters.errors == 1
    assert summary.counters.removed == 0
    assert summary.diagnostics[0].path == "notes/protected.md"
    assert summary.diagnostics[0].category == "file_read_error"
    manifest = load_kb_manifest()
    assert manifest is not None
    assert "notes/protected.md" in manifest.notes


def test_service_uses_qmd_cli_backend_by_default() -> None:
    service = KBService()

    assert isinstance(service._adapter._backend, QMDCliBackend)


def test_service_threads_command_target_overrides_without_persisting_settings(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    save_settings(
        RuntimeSettings(
            kb_vault_path=str(vault_path),
            kb_qmd_index_name="global-index",
            kb_qmd_collection_name="global-collection",
        )
    )

    service = KBService(index_name="tmp-index", collection_name="tmp-collection")

    backend = service._adapter._backend
    assert isinstance(backend, QMDCliBackend)
    assert backend.index_name == "tmp-index"
    assert backend.collection_name == "tmp-collection"
    persisted = load_settings()
    assert persisted.kb_qmd_index_name == "global-index"
    assert persisted.kb_qmd_collection_name == "global-collection"


def test_update_auto_embed_runs_only_when_state_mutates(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path, auto_embeddings=False)
    _write_note(vault_path / "notes" / "a.md", "alpha\n")

    backend = FakeBackend()
    service = KBService(backend=backend)
    service.run_ingest(vault_path=str(vault_path), dry_run=False)

    save_settings(load_settings().model_copy(update={"kb_auto_embeddings_enabled": True}))
    _write_note(vault_path / "notes" / "a.md", "alpha changed\n")
    summary_changed = service.run_update()
    assert summary_changed.embedding is not None
    assert summary_changed.embedding.attempted is True
    assert summary_changed.embedding.ok is True
    assert backend.embed_calls == 1

    summary_unchanged = service.run_update()
    assert summary_unchanged.embedding is not None
    assert summary_unchanged.embedding.attempted is False
    assert backend.embed_calls == 1


def test_update_dry_run_skips_embed_even_when_delta_exists(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path, auto_embeddings=False)
    _write_note(vault_path / "notes" / "a.md", "alpha\n")

    backend = FakeBackend()
    service = KBService(backend=backend)
    service.run_ingest(vault_path=str(vault_path), dry_run=False)

    save_settings(load_settings().model_copy(update={"kb_auto_embeddings_enabled": True}))
    _write_note(vault_path / "notes" / "a.md", "alpha changed\n")
    summary = service.run_update(dry_run=True)

    assert summary.embedding is not None
    assert summary.embedding.attempted is False
    assert backend.embed_calls == 0


def test_update_embed_failure_is_reported_as_partial_failure(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    vault_path = tmp_path / "vault"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))
    _configure_settings(config_dir=config_dir, vault_path=vault_path, auto_embeddings=False)
    _write_note(vault_path / "notes" / "a.md", "alpha\n")

    backend = FakeBackend(
        embed_response=QMDBackendResponse(
            ok=False,
            diagnostics=(
                QMDBackendDiagnostic(
                    path="<index>",
                    category="backend_embed_failed",
                    recovery_hint="Execute `qmd --index aurora-test-index embed`.",
                ),
            ),
        )
    )
    service = KBService(backend=backend)
    service.run_ingest(vault_path=str(vault_path), dry_run=False)

    save_settings(load_settings().model_copy(update={"kb_auto_embeddings_enabled": True}))
    _write_note(vault_path / "notes" / "a.md", "alpha changed\n")
    summary = service.run_update()

    assert summary.embedding is not None
    assert summary.embedding.attempted is True
    assert summary.embedding.ok is False
    assert summary.embedding.category == "backend_embed_failed"
    assert summary.embedding.recovery_command == "aurora kb update"
    assert summary.diagnostics[0].category == "backend_embed_failed"
