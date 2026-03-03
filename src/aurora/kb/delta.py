from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from aurora.kb.manifest import KBManifest, KBManifestNoteRecord


@dataclass(frozen=True)
class KBScanFingerprint:
    """Fingerprint collected from scanner state for one note."""

    path: str
    size: int
    mtime_ns: int
    sha256: str | None = None


@dataclass(frozen=True)
class KBDelta:
    """Deterministic operation sets for KB update/delete/rebuild flows."""

    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]
    divergence_reasons: tuple[str, ...] = ()

    @property
    def divergence_detected(self) -> bool:
        return bool(self.divergence_reasons)


def classify_kb_delta(
    *,
    scan_notes: Iterable[KBScanFingerprint],
    manifest: KBManifest | None,
    strict_hash: bool = False,
    scoped_paths: Iterable[str] | None = None,
) -> KBDelta:
    """Classify deterministic KB deltas from scan and manifest snapshots."""
    divergence_reasons: list[str] = []
    scope = _normalize_scope(scoped_paths)

    normalized_scan: dict[str, KBScanFingerprint] = {}
    for raw_scan_note in scan_notes:
        try:
            normalized_path = _normalize_relative_path(raw_scan_note.path)
        except ValueError as error:
            divergence_reasons.append(str(error))
            continue

        if scope is not None and normalized_path not in scope:
            continue

        scan_note = _normalize_scan_note(raw_scan_note, path=normalized_path)
        previous_scan = normalized_scan.get(normalized_path)
        if previous_scan is not None and previous_scan != scan_note:
            divergence_reasons.append(
                f"Conflito de scanner para '{normalized_path}' com fingerprints diferentes."
            )
            continue

        normalized_scan[normalized_path] = scan_note

    manifest_notes: dict[str, KBManifestNoteRecord] = {}
    if manifest is not None:
        for raw_manifest_path, record in manifest.notes.items():
            try:
                manifest_path = _normalize_relative_path(raw_manifest_path)
            except ValueError:
                divergence_reasons.append(
                    f"Manifesto contem caminho invalido: '{raw_manifest_path}'."
                )
                continue

            if scope is not None and manifest_path not in scope:
                continue

            previous_manifest_record = manifest_notes.get(manifest_path)
            if previous_manifest_record is not None and previous_manifest_record != record:
                divergence_reasons.append(
                    f"Conflito de manifesto para '{manifest_path}' com registros divergentes."
                )
                continue

            manifest_notes[manifest_path] = record

    scan_paths = set(normalized_scan)
    manifest_paths = set(manifest_notes)

    added = tuple(sorted(scan_paths - manifest_paths))
    removed = tuple(sorted(manifest_paths - scan_paths))

    unchanged: list[str] = []
    updated: list[str] = []
    for path in sorted(scan_paths & manifest_paths):
        if _is_unchanged(
            current=normalized_scan[path],
            previous=manifest_notes[path],
            strict_hash=strict_hash,
        ):
            unchanged.append(path)
        else:
            updated.append(path)

    return KBDelta(
        added=added,
        updated=tuple(updated),
        removed=removed,
        unchanged=tuple(unchanged),
        divergence_reasons=tuple(divergence_reasons),
    )


def _normalize_scope(scoped_paths: Iterable[str] | None) -> set[str] | None:
    if scoped_paths is None:
        return None

    scope: set[str] = set()
    for raw_path in scoped_paths:
        scope.add(_normalize_relative_path(raw_path))

    return scope


def _normalize_scan_note(note: KBScanFingerprint, *, path: str) -> KBScanFingerprint:
    size = _validate_non_negative_int(note.size, field=f"scan['{path}'].size")
    mtime_ns = _validate_positive_int(note.mtime_ns, field=f"scan['{path}'].mtime_ns")
    sha256 = _validate_optional_non_empty_string(note.sha256, field=f"scan['{path}'].sha256")

    return KBScanFingerprint(path=path, size=size, mtime_ns=mtime_ns, sha256=sha256)


def _is_unchanged(*, current: KBScanFingerprint, previous: KBManifestNoteRecord, strict_hash: bool) -> bool:
    if current.size == previous.size and current.mtime_ns == previous.mtime_ns:
        return True

    if not strict_hash:
        return False

    if current.sha256 and previous.sha256 and current.sha256 == previous.sha256:
        return True

    return False


def _normalize_relative_path(value: str) -> str:
    path = value.strip()
    if not path:
        raise ValueError("Caminho de nota deve ser vault-relative nao vazio.")
    if "\\" in path:
        raise ValueError(f"Caminho '{value}' deve usar '/' e permanecer vault-relative.")

    pure = PurePosixPath(path)
    if pure.is_absolute() or path.startswith("/"):
        raise ValueError(f"Caminho '{value}' deve ser vault-relative, nao absoluto.")
    if any(part == ".." for part in pure.parts):
        raise ValueError(f"Caminho '{value}' deve ser vault-relative sem segmentos de escape.")

    normalized = pure.as_posix()
    if normalized in {"", "."}:
        raise ValueError("Caminho de nota deve ser vault-relative nao vazio.")
    return normalized


def _validate_non_negative_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Campo '{field}' deve ser inteiro maior ou igual a zero.")
    return value


def _validate_positive_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Campo '{field}' deve ser inteiro positivo.")
    return value


def _validate_optional_non_empty_string(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"Campo '{field}' deve ser texto nao vazio ou null.")


__all__ = [
    "KBDelta",
    "KBScanFingerprint",
    "classify_kb_delta",
]
