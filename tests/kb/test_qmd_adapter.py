from __future__ import annotations

from dataclasses import dataclass

from aurora.kb.contracts import (
    KBEmbeddingStageStatus,
    KBFileDiagnostic,
    KBOperationCounters,
    KBOperationSummary,
    KBPreparedNote,
    KBScopeConfig,
)
from aurora.kb.delta import KBDelta
from aurora.kb.manifest import KBManifest, KBManifestNoteRecord
from aurora.kb.qmd_adapter import (
    QMDAdapter,
    QMDAdapterResult,
    QMDBackendDiagnostic,
    QMDBackendResponse,
)


@dataclass
class FakeBackend:
    apply_response: QMDBackendResponse
    remove_response: QMDBackendResponse
    rebuild_response: QMDBackendResponse
    embed_response: QMDBackendResponse = QMDBackendResponse(ok=True)
    apply_raises: Exception | None = None
    remove_raises: Exception | None = None
    rebuild_raises: Exception | None = None
    embed_raises: Exception | None = None

    def __post_init__(self) -> None:
        self.apply_calls: list[tuple[KBPreparedNote, ...]] = []
        self.remove_calls: list[tuple[str, ...]] = []
        self.rebuild_calls: list[tuple[KBPreparedNote, ...]] = []
        self.embed_calls: int = 0

    def apply(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse:
        self.apply_calls.append(notes)
        if self.apply_raises is not None:
            raise self.apply_raises
        return self.apply_response

    def remove(self, paths: tuple[str, ...]) -> QMDBackendResponse:
        self.remove_calls.append(paths)
        if self.remove_raises is not None:
            raise self.remove_raises
        return self.remove_response

    def rebuild(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse:
        self.rebuild_calls.append(notes)
        if self.rebuild_raises is not None:
            raise self.rebuild_raises
        return self.rebuild_response

    def embed(self) -> QMDBackendResponse:
        self.embed_calls += 1
        if self.embed_raises is not None:
            raise self.embed_raises
        return self.embed_response


def _note(size: int, mtime_ns: int) -> KBManifestNoteRecord:
    return KBManifestNoteRecord(
        size=size,
        mtime_ns=mtime_ns,
        sha256=None,
        indexed_at="2026-03-03T23:10:00Z",
        cleaned_size=size,
        templater_tags_removed=0,
    )


def _ok() -> QMDBackendResponse:
    return QMDBackendResponse(ok=True)


def _prepared(path: str, cleaned_text: str) -> KBPreparedNote:
    return KBPreparedNote(
        relative_path=path,
        cleaned_text=cleaned_text,
        cleaned_size=len(cleaned_text.encode("utf-8")),
        templater_tags_removed=0,
    )


def test_apply_delta_mutates_manifest_only_after_backend_success() -> None:
    backend = FakeBackend(apply_response=_ok(), remove_response=_ok(), rebuild_response=_ok())
    saves: list[KBManifest] = []

    adapter = QMDAdapter(backend=backend, save_manifest=lambda manifest: saves.append(manifest) or manifest)

    manifest = KBManifest(
        vault_root="/vault",
        notes={
            "notes/keep.md": _note(10, 1),
            "notes/update.md": _note(10, 1),
            "notes/remove.md": _note(10, 1),
        },
    )
    delta = KBDelta(
        added=("notes/add.md",),
        updated=("notes/update.md",),
        removed=("notes/remove.md",),
        unchanged=("notes/keep.md",),
    )

    result = adapter.apply_delta(
        manifest=manifest,
        delta=delta,
        scan_records={
            "notes/add.md": _note(11, 2),
            "notes/update.md": _note(12, 3),
        },
        prepared_notes={
            "notes/add.md": _prepared("notes/add.md", "new note"),
            "notes/update.md": _prepared("notes/update.md", "updated note"),
        },
    )

    assert result == QMDAdapterResult(
        applied=("notes/add.md", "notes/update.md"),
        removed=("notes/remove.md",),
        diagnostics=(),
        state_mutated=True,
    )
    assert backend.apply_calls == [
        (
            _prepared("notes/add.md", "new note"),
            _prepared("notes/update.md", "updated note"),
        )
    ]
    assert backend.remove_calls == [("notes/remove.md",)]
    assert len(saves) == 1
    assert set(saves[0].notes.keys()) == {"notes/add.md", "notes/update.md", "notes/keep.md"}


def test_apply_delta_refuses_state_mutation_on_divergence() -> None:
    backend = FakeBackend(apply_response=_ok(), remove_response=_ok(), rebuild_response=_ok())
    saves: list[KBManifest] = []

    adapter = QMDAdapter(backend=backend, save_manifest=lambda manifest: saves.append(manifest) or manifest)

    result = adapter.apply_delta(
        manifest=KBManifest(vault_root="/vault", notes={}),
        delta=KBDelta(
            added=(),
            updated=(),
            removed=(),
            unchanged=(),
            divergence_reasons=("manifest path conflict",),
        ),
        scan_records={},
        prepared_notes={},
    )

    assert result.state_mutated is False
    assert result.applied == ()
    assert result.removed == ()
    assert result.diagnostics == (
        KBFileDiagnostic(
            path="<manifest>",
            category="state_divergence",
            recovery_hint="Execute `aurora kb rebuild` para reconciliar o indice.",
        ),
    )
    assert backend.apply_calls == []
    assert backend.remove_calls == []
    assert saves == []


def test_apply_delta_partial_backend_failure_keeps_manifest_unchanged() -> None:
    backend = FakeBackend(
        apply_response=_ok(),
        remove_response=QMDBackendResponse(
            ok=False,
            diagnostics=(
                QMDBackendDiagnostic(
                    path="notes/remove.md",
                    category="remove_failed",
                    recovery_hint="Tente novamente com `aurora kb update`.",
                ),
            ),
        ),
        rebuild_response=_ok(),
    )
    saves: list[KBManifest] = []
    adapter = QMDAdapter(backend=backend, save_manifest=lambda manifest: saves.append(manifest) or manifest)

    result = adapter.apply_delta(
        manifest=KBManifest(vault_root="/vault", notes={"notes/remove.md": _note(1, 1)}),
        delta=KBDelta(added=(), updated=(), removed=("notes/remove.md",), unchanged=()),
        scan_records={},
        prepared_notes={},
    )

    assert result.state_mutated is False
    assert result.diagnostics == (
        KBFileDiagnostic(
            path="notes/remove.md",
            category="remove_failed",
            recovery_hint="Tente novamente com `aurora kb update`.",
        ),
    )
    assert saves == []


def test_backend_exceptions_are_mapped_to_typed_diagnostics() -> None:
    backend = FakeBackend(
        apply_response=_ok(),
        remove_response=_ok(),
        rebuild_response=_ok(),
        apply_raises=RuntimeError("upstream traceback noise"),
    )
    adapter = QMDAdapter(backend=backend, save_manifest=lambda manifest: manifest)

    result = adapter.apply_delta(
        manifest=KBManifest(vault_root="/vault", notes={}),
        delta=KBDelta(added=("notes/a.md",), updated=(), removed=(), unchanged=()),
        scan_records={"notes/a.md": _note(1, 1)},
        prepared_notes={"notes/a.md": _prepared("notes/a.md", "A")},
    )

    assert result.state_mutated is False
    assert result.diagnostics == (
        KBFileDiagnostic(
            path="<index>",
            category="backend_error",
            recovery_hint="Falha no backend de indice. Execute `aurora kb rebuild`.",
        ),
    )


def test_delete_and_rebuild_entrypoints_commit_manifest_on_success() -> None:
    backend = FakeBackend(apply_response=_ok(), remove_response=_ok(), rebuild_response=_ok())
    saves: list[KBManifest] = []

    adapter = QMDAdapter(backend=backend, save_manifest=lambda manifest: saves.append(manifest) or manifest)

    initial = KBManifest(vault_root="/vault", notes={"notes/old.md": _note(1, 1)})

    delete_result = adapter.delete_paths(manifest=initial, paths=("notes/old.md",))
    assert delete_result.state_mutated is True
    assert delete_result.removed == ("notes/old.md",)

    rebuild_result = adapter.rebuild(
        manifest=initial,
        records={
            "notes/new.md": _note(2, 2),
            "notes/newer.md": _note(3, 3),
        },
        prepared_notes={
            "notes/new.md": _prepared("notes/new.md", "new"),
            "notes/newer.md": _prepared("notes/newer.md", "newer"),
        },
    )
    assert rebuild_result.state_mutated is True
    assert rebuild_result.applied == ("notes/new.md", "notes/newer.md")
    assert backend.rebuild_calls == [
        (
            _prepared("notes/new.md", "new"),
            _prepared("notes/newer.md", "newer"),
        )
    ]

    assert len(saves) == 2
    assert set(saves[0].notes.keys()) == set()
    assert set(saves[1].notes.keys()) == {"notes/new.md", "notes/newer.md"}


def test_embed_operation_maps_backend_diagnostics_with_typed_fields() -> None:
    backend = FakeBackend(
        apply_response=_ok(),
        remove_response=_ok(),
        rebuild_response=_ok(),
        embed_response=QMDBackendResponse(
            ok=False,
            diagnostics=(
                QMDBackendDiagnostic(
                    path="<index>",
                    category="backend_embed_failed",
                    recovery_hint="Execute `qmd --index aurora-test embed`.",
                ),
            ),
        ),
    )
    adapter = QMDAdapter(backend=backend, save_manifest=lambda manifest: manifest)

    diagnostics = adapter.embed()

    assert diagnostics == (
        KBFileDiagnostic(
            path="<index>",
            category="backend_embed_failed",
            recovery_hint="Execute `qmd --index aurora-test embed`.",
        ),
    )
    assert backend.embed_calls == 1


def test_operation_summary_embed_metadata_serialization_is_deterministic() -> None:
    summary = KBOperationSummary(
        operation="update",
        dry_run=False,
        duration_seconds=0.5,
        counters=KBOperationCounters(read=2, indexed=1, updated=1, removed=0, skipped=0, errors=0),
        scope=KBScopeConfig(vault_root="/vault"),
        diagnostics=(),
        embedding=KBEmbeddingStageStatus(
            attempted=True,
            ok=False,
            category="backend_embed_failed",
            recovery_command="aurora kb update",
        ),
    )

    payload = summary.model_dump()
    assert payload["embedding"] == {
        "attempted": True,
        "ok": False,
        "category": "backend_embed_failed",
        "recovery_command": "aurora kb update",
    }
    assert summary.to_json() == summary.to_json()
