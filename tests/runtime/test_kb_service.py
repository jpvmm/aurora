from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from aurora.kb.contracts import KBPreparedNote
from aurora.kb.manifest import KBManifest, KBManifestNoteRecord, load_kb_manifest, save_kb_manifest
from aurora.kb.qmd_backend import QMDCliBackend
from aurora.kb.qmd_adapter import QMDBackendDiagnostic, QMDBackendResponse
from aurora.kb.service import KBService, KBServiceError
from aurora.runtime.settings import RuntimeSettings, save_settings


def _write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@dataclass
class FakeBackend:
    apply_response: QMDBackendResponse = QMDBackendResponse(ok=True)
    remove_response: QMDBackendResponse = QMDBackendResponse(ok=True)
    rebuild_response: QMDBackendResponse = QMDBackendResponse(ok=True)

    def __post_init__(self) -> None:
        self.apply_calls: list[tuple[KBPreparedNote, ...]] = []
        self.remove_calls: list[tuple[str, ...]] = []
        self.rebuild_calls: list[tuple[KBPreparedNote, ...]] = []

    def apply(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse:
        self.apply_calls.append(notes)
        return self.apply_response

    def remove(self, paths: tuple[str, ...]) -> QMDBackendResponse:
        self.remove_calls.append(paths)
        return self.remove_response

    def rebuild(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse:
        self.rebuild_calls.append(notes)
        return self.rebuild_response


def _configure_settings(*, config_dir: Path, vault_path: Path) -> None:
    save_settings(
        RuntimeSettings(
            kb_vault_path=str(vault_path),
            kb_include=("notes/*.md",),
            kb_exclude=("notes/private.md",),
            kb_default_excludes=(".obsidian/**",),
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
