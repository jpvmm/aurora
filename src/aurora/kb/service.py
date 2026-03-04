from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from aurora.kb.contracts import (
    KBFileDiagnostic,
    KBOperationCounters,
    KBOperationSummary,
    KBPreparedNote,
    KBScopeConfig,
)
from aurora.kb.delta import KBDelta, KBScanFingerprint, classify_kb_delta
from aurora.kb.manifest import (
    KBManifest,
    KBManifestNoteRecord,
    KBManifestStateError,
    load_kb_manifest,
    save_kb_manifest,
)
from aurora.kb.preprocess import preprocess_markdown
from aurora.kb.qmd_adapter import QMDAdapter, QMDBackend
from aurora.kb.qmd_backend import QMDCliBackend
from aurora.kb.scanner import ScanResult, scan_markdown_files
from aurora.kb.scope import ScopeConfigurationError, ScopeRules
from aurora.runtime.settings import RuntimeSettings, load_settings

ProgressCallback = Callable[[str, KBOperationCounters], None]
NowProvider = Callable[[], datetime]


@dataclass(frozen=True)
class KBServiceError(Exception):
    """Typed KB lifecycle error consumed by CLI text/JSON renderers."""

    category: str
    message: str
    diagnostics: tuple[KBFileDiagnostic, ...] = ()
    recovery_commands: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.message


class KBService:
    """Service-layer orchestration for ingest/update/delete/rebuild lifecycle commands."""

    def __init__(
        self,
        *,
        backend: QMDBackend | None = None,
        load_settings_fn: Callable[[], RuntimeSettings] = load_settings,
        load_manifest_fn: Callable[[], KBManifest | None] = load_kb_manifest,
        save_manifest_fn: Callable[[KBManifest], KBManifest] = save_kb_manifest,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._load_settings = load_settings_fn
        self._load_manifest = load_manifest_fn
        self._save_manifest = save_manifest_fn
        self._now_provider = now_provider or (lambda: datetime.now(tz=timezone.utc))
        self._adapter = QMDAdapter(
            backend=backend or QMDCliBackend(),
            save_manifest=save_manifest_fn,
        )

    def run_ingest(
        self,
        *,
        vault_path: str,
        dry_run: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> KBOperationSummary:
        started = time.perf_counter()
        settings = self._load_settings()
        scope, scope_rules = self._build_scope(settings=settings, vault_path=vault_path)
        manifest = self._load_manifest_for_operation(
            vault_root=scope_rules.vault_root,
            allow_mismatch=False,
        )
        scan = self._scan(scope_rules=scope_rules, scope=scope)
        self._emit_progress(
            on_progress,
            "scan",
            read=len(scan.indexed),
            indexed=0,
            updated=0,
            removed=0,
            skipped=len(scan.skipped),
            errors=0,
        )

        fingerprints, records, prepared_notes, diagnostics, errored_paths = self._prepare_scan_records(
            vault_root=scope_rules.vault_root,
            indexed_paths=scan.indexed,
            recovery_command="aurora kb ingest <vault_path>",
        )
        scoped_paths = self._resolve_scoped_paths(
            scan_paths=scan.indexed,
            manifest=manifest,
            scope_rules=scope_rules,
        )
        delta = classify_kb_delta(
            scan_notes=fingerprints,
            manifest=manifest,
            strict_hash=False,
            scoped_paths=scoped_paths,
        )
        self._raise_on_divergence(delta=delta)
        effective_delta = self._drop_errored_paths(delta=delta, errored_paths=errored_paths)
        self._emit_progress(
            on_progress,
            "preprocess",
            read=len(scan.indexed),
            indexed=0,
            updated=0,
            removed=0,
            skipped=len(scan.skipped) + len(effective_delta.unchanged) + len(errored_paths),
            errors=len(diagnostics),
        )

        removed_count = len(effective_delta.removed)
        indexed_count = len(effective_delta.added) + len(effective_delta.updated)
        if not dry_run:
            adapter_result = self._adapter.apply_delta(
                manifest=manifest,
                delta=effective_delta,
                scan_records=records,
                prepared_notes=prepared_notes,
            )
            self._raise_on_adapter_diagnostics(adapter_result.diagnostics)
            removed_count = len(adapter_result.removed)
            indexed_count = len(adapter_result.applied)

        self._emit_progress(
            on_progress,
            "done",
            read=len(scan.indexed),
            indexed=indexed_count,
            updated=0,
            removed=removed_count,
            skipped=len(scan.skipped) + len(effective_delta.unchanged) + len(errored_paths),
            errors=len(diagnostics),
        )
        return self._build_summary(
            operation="ingest",
            dry_run=dry_run,
            scope=scope,
            started=started,
            read=len(scan.indexed),
            indexed=indexed_count,
            updated=0,
            removed=removed_count,
            skipped=len(scan.skipped) + len(effective_delta.unchanged) + len(errored_paths),
            diagnostics=diagnostics,
        )

    def run_update(
        self,
        *,
        dry_run: bool = False,
        verify_hash: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> KBOperationSummary:
        started = time.perf_counter()
        settings = self._load_settings()
        scope, scope_rules = self._build_scope(settings=settings)
        manifest = self._load_manifest_for_operation(
            vault_root=scope_rules.vault_root,
            allow_mismatch=False,
        )
        scan = self._scan(scope_rules=scope_rules, scope=scope)
        self._emit_progress(
            on_progress,
            "scan",
            read=len(scan.indexed),
            indexed=0,
            updated=0,
            removed=0,
            skipped=len(scan.skipped),
            errors=0,
        )
        fingerprints, records, prepared_notes, diagnostics, errored_paths = self._prepare_scan_records(
            vault_root=scope_rules.vault_root,
            indexed_paths=scan.indexed,
            recovery_command="aurora kb update",
        )
        scoped_paths = self._resolve_scoped_paths(
            scan_paths=scan.indexed,
            manifest=manifest,
            scope_rules=scope_rules,
        )
        delta = classify_kb_delta(
            scan_notes=fingerprints,
            manifest=manifest,
            strict_hash=verify_hash,
            scoped_paths=scoped_paths,
        )
        self._raise_on_divergence(delta=delta)
        effective_delta = self._drop_errored_paths(delta=delta, errored_paths=errored_paths)
        self._emit_progress(
            on_progress,
            "preprocess",
            read=len(scan.indexed),
            indexed=0,
            updated=0,
            removed=0,
            skipped=len(scan.skipped) + len(effective_delta.unchanged) + len(errored_paths),
            errors=len(diagnostics),
        )

        indexed_count = len(effective_delta.added)
        updated_count = len(effective_delta.updated)
        removed_count = len(effective_delta.removed)
        if not dry_run:
            adapter_result = self._adapter.apply_delta(
                manifest=manifest,
                delta=effective_delta,
                scan_records=records,
                prepared_notes=prepared_notes,
            )
            self._raise_on_adapter_diagnostics(adapter_result.diagnostics)
            applied_set = set(adapter_result.applied)
            indexed_count = len(applied_set.intersection(effective_delta.added))
            updated_count = len(applied_set.intersection(effective_delta.updated))
            removed_count = len(adapter_result.removed)

        self._emit_progress(
            on_progress,
            "done",
            read=len(scan.indexed),
            indexed=indexed_count,
            updated=updated_count,
            removed=removed_count,
            skipped=len(scan.skipped) + len(effective_delta.unchanged) + len(errored_paths),
            errors=len(diagnostics),
        )
        return self._build_summary(
            operation="update",
            dry_run=dry_run,
            scope=scope,
            started=started,
            read=len(scan.indexed),
            indexed=indexed_count,
            updated=updated_count,
            removed=removed_count,
            skipped=len(scan.skipped) + len(effective_delta.unchanged) + len(errored_paths),
            diagnostics=diagnostics,
        )

    def run_delete(
        self,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> KBOperationSummary:
        started = time.perf_counter()
        settings = self._load_settings()
        scope, scope_rules = self._build_scope(settings=settings)
        manifest = self._load_manifest_for_operation(
            vault_root=scope_rules.vault_root,
            allow_mismatch=False,
        )
        paths_to_remove = self._manifest_paths_in_scope(manifest=manifest, scope_rules=scope_rules)
        self._emit_progress(
            on_progress,
            "scan",
            read=0,
            indexed=0,
            updated=0,
            removed=0,
            skipped=0,
            errors=0,
        )
        if not paths_to_remove:
            return self._build_summary(
                operation="delete",
                dry_run=False,
                scope=scope,
                started=started,
                read=0,
                indexed=0,
                updated=0,
                removed=0,
                skipped=0,
                diagnostics=(),
            )

        adapter_result = self._adapter.delete_paths(
            manifest=manifest,
            paths=paths_to_remove,
        )
        self._raise_on_adapter_diagnostics(adapter_result.diagnostics)
        self._emit_progress(
            on_progress,
            "done",
            read=0,
            indexed=0,
            updated=0,
            removed=len(adapter_result.removed),
            skipped=0,
            errors=0,
        )
        return self._build_summary(
            operation="delete",
            dry_run=False,
            scope=scope,
            started=started,
            read=0,
            indexed=0,
            updated=0,
            removed=len(adapter_result.removed),
            skipped=0,
            diagnostics=(),
        )

    def run_rebuild(
        self,
        *,
        dry_run: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> KBOperationSummary:
        started = time.perf_counter()
        settings = self._load_settings()
        scope, scope_rules = self._build_scope(settings=settings)
        manifest = self._load_manifest_for_operation(
            vault_root=scope_rules.vault_root,
            allow_mismatch=True,
        )
        scan = self._scan(scope_rules=scope_rules, scope=scope)
        self._emit_progress(
            on_progress,
            "scan",
            read=len(scan.indexed),
            indexed=0,
            updated=0,
            removed=0,
            skipped=len(scan.skipped),
            errors=0,
        )
        _, records, prepared_notes, diagnostics, errored_paths = self._prepare_scan_records(
            vault_root=scope_rules.vault_root,
            indexed_paths=scan.indexed,
            recovery_command="aurora kb rebuild",
        )
        stale_before = set(self._manifest_paths_in_scope(manifest=manifest, scope_rules=scope_rules))
        stale_removed = len(stale_before - set(records.keys()))
        self._emit_progress(
            on_progress,
            "preprocess",
            read=len(scan.indexed),
            indexed=0,
            updated=0,
            removed=0,
            skipped=len(scan.skipped) + len(errored_paths),
            errors=len(diagnostics),
        )
        indexed_count = len(records)
        if not dry_run:
            adapter_result = self._adapter.rebuild(
                manifest=KBManifest(
                    vault_root=scope_rules.vault_root.as_posix(),
                    notes=dict(manifest.notes),
                    schema_version=manifest.schema_version,
                ),
                records=records,
                prepared_notes=prepared_notes,
            )
            self._raise_on_adapter_diagnostics(adapter_result.diagnostics)
            indexed_count = len(adapter_result.applied)

        self._emit_progress(
            on_progress,
            "done",
            read=len(scan.indexed),
            indexed=indexed_count,
            updated=0,
            removed=stale_removed,
            skipped=len(scan.skipped) + len(errored_paths),
            errors=len(diagnostics),
        )
        return self._build_summary(
            operation="rebuild",
            dry_run=dry_run,
            scope=scope,
            started=started,
            read=len(scan.indexed),
            indexed=indexed_count,
            updated=0,
            removed=stale_removed,
            skipped=len(scan.skipped) + len(errored_paths),
            diagnostics=diagnostics,
        )

    def _build_scope(
        self,
        *,
        settings: RuntimeSettings,
        vault_path: str | None = None,
    ) -> tuple[KBScopeConfig, ScopeRules]:
        effective_vault = (vault_path or settings.kb_vault_path).strip()
        if not effective_vault:
            raise KBServiceError(
                category="vault_not_configured",
                message="Vault path nao configurado para operacoes KB.",
                recovery_commands=(
                    "aurora kb ingest <vault_path>",
                    "aurora config show",
                ),
            )

        scope = KBScopeConfig(
            vault_root=effective_vault,
            include=settings.kb_include,
            exclude=settings.kb_exclude,
            default_excludes=settings.kb_default_excludes,
        )
        try:
            scope_rules = ScopeRules.from_config(scope)
        except ScopeConfigurationError as error:
            raise KBServiceError(
                category="scope_invalid",
                message=str(error),
                diagnostics=(
                    KBFileDiagnostic(
                        path="<scope>",
                        category="scope_invalid",
                        recovery_hint="Revise include/exclude e execute `aurora kb ingest <vault_path> --dry-run`.",
                    ),
                ),
                recovery_commands=("aurora kb ingest <vault_path> --dry-run",),
            ) from error
        return scope, scope_rules

    def _load_manifest_for_operation(self, *, vault_root: Path, allow_mismatch: bool) -> KBManifest:
        try:
            loaded_manifest = self._load_manifest()
        except KBManifestStateError as error:
            raise KBServiceError(
                category="state_corruption",
                message=str(error),
                diagnostics=(
                    KBFileDiagnostic(
                        path="<manifest>",
                        category="state_corruption",
                        recovery_hint="Execute `aurora kb rebuild` para restaurar estado.",
                    ),
                ),
                recovery_commands=error.recovery_commands,
            ) from error

        if loaded_manifest is None:
            return KBManifest(vault_root=vault_root.as_posix(), notes={})

        if loaded_manifest.vault_root == vault_root.as_posix():
            return loaded_manifest

        if allow_mismatch:
            return KBManifest(
                vault_root=vault_root.as_posix(),
                notes=dict(loaded_manifest.notes),
                schema_version=loaded_manifest.schema_version,
            )

        raise KBServiceError(
            category="state_divergence",
            message=(
                "Manifesto KB aponta para outro vault. "
                "Execute rebuild para reconciliar o estado antes de continuar."
            ),
            diagnostics=(
                KBFileDiagnostic(
                    path="<manifest>",
                    category="state_divergence",
                    recovery_hint="Execute `aurora kb rebuild` para reconciliar o indice.",
                ),
            ),
            recovery_commands=("aurora kb rebuild",),
        )

    def _scan(self, *, scope_rules: ScopeRules, scope: KBScopeConfig) -> ScanResult:
        scan = scan_markdown_files(vault_root=scope_rules.vault_root, scope=scope_rules)
        if scope.include and not scan.indexed:
            raise KBServiceError(
                category="scope_no_matches",
                message=(
                    "Nenhum arquivo correspondeu aos includes configurados. "
                    "Revise os padroes e valide com `aurora kb ingest <vault_path> --dry-run`."
                ),
                diagnostics=(
                    KBFileDiagnostic(
                        path="<scope>",
                        category="scope_no_matches",
                        recovery_hint="Ajuste os includes e execute `aurora kb ingest <vault_path> --dry-run`.",
                    ),
                ),
                recovery_commands=("aurora kb ingest <vault_path> --dry-run",),
            )
        return scan

    def _prepare_scan_records(
        self,
        *,
        vault_root: Path,
        indexed_paths: tuple[str, ...],
        recovery_command: str,
    ) -> tuple[
        list[KBScanFingerprint],
        dict[str, KBManifestNoteRecord],
        dict[str, KBPreparedNote],
        tuple[KBFileDiagnostic, ...],
        set[str],
    ]:
        fingerprints: list[KBScanFingerprint] = []
        records: dict[str, KBManifestNoteRecord] = {}
        prepared_notes: dict[str, KBPreparedNote] = {}
        diagnostics: list[KBFileDiagnostic] = []
        errored_paths: set[str] = set()
        indexed_at = self._now_provider().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        for relative_path in indexed_paths:
            absolute_path = (vault_root / relative_path).resolve()
            try:
                stat = absolute_path.stat()
                markdown_text = absolute_path.read_text(encoding="utf-8")
                cleaned = preprocess_markdown(
                    relative_path=relative_path,
                    markdown_text=markdown_text,
                )
            except (OSError, UnicodeError):
                diagnostics.append(
                    KBFileDiagnostic(
                        path=relative_path,
                        category="file_read_error",
                        recovery_hint=f"Corrija permissao/encoding e execute `{recovery_command}`.",
                    )
                )
                errored_paths.add(relative_path)
                continue

            cleaned_bytes = cleaned.cleaned_text.encode("utf-8")
            digest = hashlib.sha256(cleaned_bytes).hexdigest()
            fingerprints.append(
                KBScanFingerprint(
                    path=relative_path,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=digest,
                )
            )
            records[relative_path] = KBManifestNoteRecord(
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=digest,
                indexed_at=indexed_at,
                cleaned_size=len(cleaned_bytes),
                templater_tags_removed=cleaned.cleaned_snippet_count,
            )
            prepared_notes[relative_path] = KBPreparedNote(
                relative_path=relative_path,
                cleaned_text=cleaned.cleaned_text,
                cleaned_size=len(cleaned_bytes),
                templater_tags_removed=cleaned.cleaned_snippet_count,
            )

        return fingerprints, records, prepared_notes, tuple(diagnostics), errored_paths

    def _resolve_scoped_paths(
        self,
        *,
        scan_paths: tuple[str, ...],
        manifest: KBManifest,
        scope_rules: ScopeRules,
    ) -> tuple[str, ...]:
        scoped = set(scan_paths)
        scoped.update(self._manifest_paths_in_scope(manifest=manifest, scope_rules=scope_rules))
        return tuple(sorted(scoped))

    def _manifest_paths_in_scope(
        self,
        *,
        manifest: KBManifest,
        scope_rules: ScopeRules,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(path for path in manifest.notes.keys() if scope_rules.should_index(path))
        )

    def _drop_errored_paths(self, *, delta: KBDelta, errored_paths: set[str]) -> KBDelta:
        if not errored_paths:
            return delta
        return KBDelta(
            added=tuple(path for path in delta.added if path not in errored_paths),
            updated=tuple(path for path in delta.updated if path not in errored_paths),
            removed=tuple(path for path in delta.removed if path not in errored_paths),
            unchanged=tuple(path for path in delta.unchanged if path not in errored_paths),
            divergence_reasons=delta.divergence_reasons,
        )

    def _raise_on_divergence(self, *, delta: KBDelta) -> None:
        if not delta.divergence_detected:
            return
        raise KBServiceError(
            category="state_divergence",
            message=(
                "Estado KB divergente detectado. "
                f"{delta.divergence_reasons[0]} "
                "Execute `aurora kb rebuild` para reconciliar."
            ),
            diagnostics=(
                KBFileDiagnostic(
                    path="<manifest>",
                    category="state_divergence",
                    recovery_hint="Execute `aurora kb rebuild` para reconciliar o indice.",
                ),
            ),
            recovery_commands=("aurora kb rebuild",),
        )

    def _raise_on_adapter_diagnostics(self, diagnostics: tuple[KBFileDiagnostic, ...]) -> None:
        if not diagnostics:
            return
        unique_hints = tuple(dict.fromkeys(diagnostic.recovery_hint for diagnostic in diagnostics))
        raise KBServiceError(
            category=diagnostics[0].category,
            message="Falha ao aplicar alteracoes no indice da base de conhecimento.",
            diagnostics=diagnostics,
            recovery_commands=unique_hints,
        )

    def _build_summary(
        self,
        *,
        operation: str,
        dry_run: bool,
        scope: KBScopeConfig,
        started: float,
        read: int,
        indexed: int,
        updated: int,
        removed: int,
        skipped: int,
        diagnostics: tuple[KBFileDiagnostic, ...],
    ) -> KBOperationSummary:
        return KBOperationSummary(
            operation=operation,
            dry_run=dry_run,
            duration_seconds=max(time.perf_counter() - started, 0.0),
            counters=KBOperationCounters(
                read=read,
                indexed=indexed,
                updated=updated,
                removed=removed,
                skipped=skipped,
                errors=len(diagnostics),
            ),
            scope=scope,
            diagnostics=diagnostics,
        )

    def _emit_progress(
        self,
        callback: ProgressCallback | None,
        stage: str,
        *,
        read: int,
        indexed: int,
        updated: int,
        removed: int,
        skipped: int,
        errors: int,
    ) -> None:
        if callback is None:
            return
        callback(
            stage,
            KBOperationCounters(
                read=read,
                indexed=indexed,
                updated=updated,
                removed=removed,
                skipped=skipped,
                errors=errors,
            ),
        )


__all__ = ["KBService", "KBServiceError", "ProgressCallback"]
