from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from aurora.runtime.paths import ensure_config_dir, get_kb_manifest_path

KB_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class KBManifestNoteRecord:
    """Persistent fingerprint and indexing trace for one vault note."""

    size: int
    mtime_ns: int
    sha256: str | None
    indexed_at: str
    cleaned_size: int
    templater_tags_removed: int


@dataclass(frozen=True)
class KBManifest:
    """Persistent KB manifest keyed by vault-relative note path."""

    vault_root: str
    notes: dict[str, KBManifestNoteRecord]
    schema_version: int = KB_MANIFEST_SCHEMA_VERSION


@dataclass(frozen=True)
class KBManifestStateError(Exception):
    """Typed KB manifest diagnostic with actionable recovery commands."""

    message: str
    recovery_commands: tuple[str, ...]

    def __str__(self) -> str:
        commands = "\n".join(f"- {command}" for command in self.recovery_commands)
        return f"{self.message}\nComandos de recuperacao:\n{commands}"


def load_kb_manifest() -> KBManifest | None:
    """Load persisted KB manifest or return None when absent."""
    path = get_kb_manifest_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise _build_manifest_error(path=str(path), detail=f"JSON invalido ({error.msg}).") from error
    except OSError as error:
        raise _build_manifest_error(path=str(path), detail=str(error)) from error

    if not isinstance(payload, dict):
        raise _build_manifest_error(path=str(path), detail="Esperado objeto JSON no manifesto.")

    try:
        return _manifest_from_payload(payload)
    except ValueError as error:
        raise _build_manifest_error(path=str(path), detail=str(error)) from error


def save_kb_manifest(manifest: KBManifest) -> KBManifest:
    """Persist KB manifest with deterministic, validated JSON."""
    ensure_config_dir()
    normalized = _manifest_from_payload(asdict(manifest))
    serialized = json.dumps(_manifest_to_payload(normalized), ensure_ascii=False, indent=2, sort_keys=True)
    get_kb_manifest_path().write_text(f"{serialized}\n", encoding="utf-8")
    return normalized


def _manifest_to_payload(manifest: KBManifest) -> dict[str, Any]:
    notes = {
        path: asdict(record)
        for path, record in sorted(manifest.notes.items(), key=lambda item: item[0])
    }
    return {
        "schema_version": manifest.schema_version,
        "vault_root": manifest.vault_root,
        "notes": notes,
    }


def _manifest_from_payload(payload: dict[str, Any]) -> KBManifest:
    _validate_object_keys(
        payload,
        expected={"schema_version", "vault_root", "notes"},
        context="manifesto",
    )

    schema_version = _validate_schema_version(payload.get("schema_version"))
    vault_root = _validate_non_empty_string(payload.get("vault_root"), field="vault_root")
    notes = _validate_notes(payload.get("notes"))

    return KBManifest(
        vault_root=vault_root,
        notes=notes,
        schema_version=schema_version,
    )


def _validate_notes(value: Any) -> dict[str, KBManifestNoteRecord]:
    if not isinstance(value, dict):
        raise ValueError("Campo 'notes' deve ser objeto com registros por caminho relativo.")

    normalized: dict[str, KBManifestNoteRecord] = {}
    for raw_path in sorted(value.keys()):
        path = _validate_relative_note_path(raw_path)
        note_payload = value[raw_path]
        if not isinstance(note_payload, dict):
            raise ValueError(f"Registro de nota '{path}' deve ser objeto JSON.")

        _validate_object_keys(
            note_payload,
            expected={
                "size",
                "mtime_ns",
                "sha256",
                "indexed_at",
                "cleaned_size",
                "templater_tags_removed",
            },
            context=f"notes['{path}']",
        )

        size = _validate_non_negative_int(note_payload.get("size"), field=f"notes['{path}'].size")
        mtime_ns = _validate_positive_int(note_payload.get("mtime_ns"), field=f"notes['{path}'].mtime_ns")
        sha256 = _validate_optional_non_empty_string(
            note_payload.get("sha256"),
            field=f"notes['{path}'].sha256",
        )
        indexed_at = _validate_non_empty_string(
            note_payload.get("indexed_at"),
            field=f"notes['{path}'].indexed_at",
        )
        cleaned_size = _validate_non_negative_int(
            note_payload.get("cleaned_size"),
            field=f"notes['{path}'].cleaned_size",
        )
        if cleaned_size > size:
            raise ValueError(
                f"Campo 'notes['{path}'].cleaned_size' nao pode exceder o tamanho original da nota."
            )
        templater_tags_removed = _validate_non_negative_int(
            note_payload.get("templater_tags_removed"),
            field=f"notes['{path}'].templater_tags_removed",
        )

        normalized[path] = KBManifestNoteRecord(
            size=size,
            mtime_ns=mtime_ns,
            sha256=sha256,
            indexed_at=indexed_at,
            cleaned_size=cleaned_size,
            templater_tags_removed=templater_tags_removed,
        )

    return normalized


def _validate_schema_version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Campo 'schema_version' deve ser inteiro.")
    if value != KB_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Campo 'schema_version' incompatível com esta versao do Aurora. "
            f"Esperado {KB_MANIFEST_SCHEMA_VERSION}, recebido {value}."
        )
    return value


def _validate_relative_note_path(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Chave de nota em 'notes' deve ser texto vault-relative.")

    path = value.strip()
    if not path:
        raise ValueError("Chave de nota em 'notes' deve ser texto vault-relative nao vazio.")
    if "\\" in path:
        raise ValueError(f"Caminho '{path}' deve usar '/' e permanecer vault-relative.")

    pure = PurePosixPath(path)
    if pure.is_absolute() or path.startswith("/"):
        raise ValueError(f"Caminho '{path}' deve ser vault-relative, nao absoluto.")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"Caminho '{path}' deve ser vault-relative sem segmentos de escape.")

    return pure.as_posix()


def _validate_non_empty_string(value: Any, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"Campo '{field}' deve ser texto nao vazio.")


def _validate_optional_non_empty_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"Campo '{field}' deve ser texto nao vazio ou null.")


def _validate_positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Campo '{field}' deve ser inteiro positivo.")
    return value


def _validate_non_negative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Campo '{field}' deve ser inteiro maior ou igual a zero.")
    return value


def _validate_object_keys(payload: dict[str, Any], *, expected: set[str], context: str) -> None:
    received = set(payload.keys())
    if received != expected:
        missing = sorted(expected - received)
        extra = sorted(received - expected)
        details: list[str] = []
        if missing:
            details.append(f"faltando={missing}")
        if extra:
            details.append(f"extras={extra}")
        joined = "; ".join(details) or "sem detalhes"
        raise ValueError(f"Campos invalidos em {context}: {joined}.")


def _build_manifest_error(*, path: str, detail: str) -> KBManifestStateError:
    return KBManifestStateError(
        message=(
            "Manifesto da base de conhecimento corrompido ou desatualizado. "
            f"Arquivo: {path}. Detalhe: {detail} "
            "Execute os comandos abaixo para reconstruir o estado."
        ),
        recovery_commands=(
            "aurora kb rebuild",
            f"rm \"{path}\"",
        ),
    )


__all__ = [
    "KB_MANIFEST_SCHEMA_VERSION",
    "KBManifest",
    "KBManifestNoteRecord",
    "KBManifestStateError",
    "load_kb_manifest",
    "save_kb_manifest",
]
