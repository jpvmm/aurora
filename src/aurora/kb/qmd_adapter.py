from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from aurora.kb.contracts import KBFileDiagnostic, KBPreparedNote
from aurora.kb.delta import KBDelta
from aurora.kb.manifest import KBManifest, KBManifestNoteRecord


@dataclass(frozen=True)
class QMDBackendDiagnostic:
    """Backend diagnostic reduced to privacy-safe adapter fields."""

    path: str
    category: str
    recovery_hint: str


@dataclass(frozen=True)
class QMDBackendResponse:
    """Backend operation response normalized by the adapter boundary."""

    ok: bool
    diagnostics: tuple[QMDBackendDiagnostic, ...] = ()


@dataclass(frozen=True)
class QMDAdapterResult:
    """Adapter-level result consumed by KB lifecycle orchestration."""

    applied: tuple[str, ...]
    removed: tuple[str, ...]
    diagnostics: tuple[KBFileDiagnostic, ...]
    state_mutated: bool


class QMDBackend(Protocol):
    """Minimal backend protocol to isolate Aurora from QMD command drift."""

    def apply(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse: ...

    def remove(self, paths: tuple[str, ...]) -> QMDBackendResponse: ...

    def rebuild(self, notes: tuple[KBPreparedNote, ...]) -> QMDBackendResponse: ...


class QMDAdapter:
    """Aurora-owned adapter for apply/delete/rebuild index lifecycle calls."""

    def __init__(
        self,
        *,
        backend: QMDBackend,
        save_manifest: Callable[[KBManifest], KBManifest],
    ) -> None:
        self._backend = backend
        self._save_manifest = save_manifest

    def apply_delta(
        self,
        *,
        manifest: KBManifest,
        delta: KBDelta,
        scan_records: dict[str, KBManifestNoteRecord],
        prepared_notes: dict[str, KBPreparedNote],
    ) -> QMDAdapterResult:
        if delta.divergence_detected:
            return self._fail(
                diagnostics=(
                    KBFileDiagnostic(
                        path="<manifest>",
                        category="state_divergence",
                        recovery_hint="Execute `aurora kb rebuild` para reconciliar o indice.",
                    ),
                )
            )

        applied = tuple(sorted(set((*delta.added, *delta.updated))))
        removed = tuple(sorted(set(delta.removed)))

        missing_records = tuple(
            path for path in applied if path not in scan_records or path not in prepared_notes
        )
        if missing_records:
            return self._fail(
                diagnostics=(
                    KBFileDiagnostic(
                        path=missing_records[0],
                        category="state_mismatch",
                        recovery_hint="Estado incompleto para update. Execute `aurora kb rebuild`.",
                    ),
                )
            )

        apply_payload = tuple(prepared_notes[path] for path in applied)
        apply_diagnostics = self._invoke_backend(
            operation="apply",
            paths=applied,
            notes=apply_payload,
        )
        if apply_diagnostics:
            return self._fail(diagnostics=apply_diagnostics)

        remove_diagnostics = self._invoke_backend(operation="remove", paths=removed)
        if remove_diagnostics:
            return self._fail(diagnostics=remove_diagnostics)

        updated_notes = dict(manifest.notes)
        for path in removed:
            updated_notes.pop(path, None)
        for path in applied:
            updated_notes[path] = scan_records[path]

        self._commit_manifest(base=manifest, notes=updated_notes)
        return QMDAdapterResult(
            applied=applied,
            removed=removed,
            diagnostics=(),
            state_mutated=True,
        )

    def delete_paths(
        self,
        *,
        manifest: KBManifest,
        paths: tuple[str, ...],
    ) -> QMDAdapterResult:
        removed = tuple(sorted(set(paths)))
        diagnostics = self._invoke_backend(operation="remove", paths=removed)
        if diagnostics:
            return self._fail(diagnostics=diagnostics)

        updated_notes = dict(manifest.notes)
        for path in removed:
            updated_notes.pop(path, None)

        self._commit_manifest(base=manifest, notes=updated_notes)
        return QMDAdapterResult(
            applied=(),
            removed=removed,
            diagnostics=(),
            state_mutated=True,
        )

    def rebuild(
        self,
        *,
        manifest: KBManifest,
        records: dict[str, KBManifestNoteRecord],
        prepared_notes: dict[str, KBPreparedNote],
    ) -> QMDAdapterResult:
        applied = tuple(sorted(records.keys()))
        missing_records = tuple(path for path in applied if path not in prepared_notes)
        if missing_records:
            return self._fail(
                diagnostics=(
                    KBFileDiagnostic(
                        path=missing_records[0],
                        category="state_mismatch",
                        recovery_hint="Estado incompleto para rebuild. Execute `aurora kb rebuild`.",
                    ),
                )
            )

        diagnostics = self._invoke_backend(
            operation="rebuild",
            paths=applied,
            notes=tuple(prepared_notes[path] for path in applied),
        )
        if diagnostics:
            return self._fail(diagnostics=diagnostics)

        self._commit_manifest(base=manifest, notes=records)
        return QMDAdapterResult(
            applied=applied,
            removed=(),
            diagnostics=(),
            state_mutated=True,
        )

    def _invoke_backend(
        self,
        *,
        operation: str,
        paths: tuple[str, ...],
        notes: tuple[KBPreparedNote, ...] | None = None,
    ) -> tuple[KBFileDiagnostic, ...]:
        if not paths:
            return ()

        try:
            if operation == "apply":
                response = self._backend.apply(notes or ())
            elif operation == "remove":
                response = self._backend.remove(paths)
            elif operation == "rebuild":
                response = self._backend.rebuild(notes or ())
            else:
                raise ValueError(f"Operacao de backend desconhecida: {operation}")
        except Exception:
            return (
                KBFileDiagnostic(
                    path="<index>",
                    category="backend_error",
                    recovery_hint="Falha no backend de indice. Execute `aurora kb rebuild`.",
                ),
            )

        if response.ok and not response.diagnostics:
            return ()

        if response.diagnostics:
            return tuple(
                KBFileDiagnostic(
                    path=item.path,
                    category=item.category,
                    recovery_hint=item.recovery_hint,
                )
                for item in response.diagnostics
            )

        return (
            KBFileDiagnostic(
                path="<index>",
                category=f"{operation}_failed",
                recovery_hint="Falha no backend de indice. Execute `aurora kb rebuild`.",
            ),
        )

    def _commit_manifest(self, *, base: KBManifest, notes: dict[str, KBManifestNoteRecord]) -> None:
        ordered_notes = {path: notes[path] for path in sorted(notes.keys())}
        self._save_manifest(
            KBManifest(
                vault_root=base.vault_root,
                schema_version=base.schema_version,
                notes=ordered_notes,
            )
        )

    def _fail(self, *, diagnostics: tuple[KBFileDiagnostic, ...]) -> QMDAdapterResult:
        return QMDAdapterResult(
            applied=(),
            removed=(),
            diagnostics=diagnostics,
            state_mutated=False,
        )


__all__ = [
    "QMDAdapter",
    "QMDAdapterResult",
    "QMDBackend",
    "QMDBackendDiagnostic",
    "QMDBackendResponse",
]
