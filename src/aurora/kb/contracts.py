from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_SCOPE_EXCLUDES: tuple[str, ...] = (
    ".DS_Store",
    ".Spotlight-V100/**",
    ".TemporaryItems/**",
    ".Trash/**",
    ".obsidian/**",
    "**/.DS_Store",
    "**/Thumbs.db",
)


def _normalize_patterns(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = [value]
    else:
        candidates = list(value)

    normalized: set[str] = set()
    for candidate in candidates:
        text = str(candidate).strip()
        if text:
            normalized.add(text)
    return tuple(sorted(normalized))


class KBScopeConfig(BaseModel):
    """Canonical vault scope configuration for KB operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vault_root: str
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    default_excludes: tuple[str, ...] = DEFAULT_SCOPE_EXCLUDES

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def _normalize_rule_lists(cls, value: object) -> tuple[str, ...]:
        return _normalize_patterns(value)

    @field_validator("default_excludes", mode="before")
    @classmethod
    def _normalize_default_excludes(cls, value: object) -> tuple[str, ...]:
        normalized = _normalize_patterns(value)
        return normalized or DEFAULT_SCOPE_EXCLUDES


class KBOperationCounters(BaseModel):
    """Counters shared by ingest/update/delete/rebuild lifecycle operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    read: int = Field(ge=0)
    indexed: int = Field(ge=0)
    updated: int = Field(ge=0)
    removed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)


class KBFileDiagnostic(BaseModel):
    """Structured per-file diagnostic without note content leakage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    category: str
    recovery_hint: str


class KBPreparedNote(BaseModel):
    """Prepared markdown payload forwarded from service into backend operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    cleaned_text: str
    cleaned_size: int = Field(ge=0)
    templater_tags_removed: int = Field(ge=0)

    @field_validator("relative_path", mode="before")
    @classmethod
    def _normalize_relative_path(cls, value: object) -> str:
        text = str(value).replace("\\", "/").strip()
        while text.startswith("./"):
            text = text[2:]
        if not text or text.startswith("/"):
            raise ValueError("relative_path deve ser vault-relative.")
        if ".." in text.split("/"):
            raise ValueError("relative_path deve permanecer dentro do vault.")
        return text


class KBOperationSummary(BaseModel):
    """Single operation contract for text and JSON renderers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["ingest", "update", "delete", "rebuild"]
    dry_run: bool = False
    duration_seconds: float = Field(ge=0)
    counters: KBOperationCounters
    scope: KBScopeConfig
    diagnostics: tuple[KBFileDiagnostic, ...] = ()
    embedding: KBEmbeddingStageStatus | None = None

    @field_validator("diagnostics", mode="before")
    @classmethod
    def _normalize_diagnostics(cls, value: object) -> tuple[KBFileDiagnostic, ...]:
        if value is None:
            return ()
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        return (value,)  # type: ignore[return-value]

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)

    def to_json(self) -> str:
        """Serialize deterministically for machine output snapshots."""
        payload = self.model_dump(mode="json", exclude_none=True)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class KBEmbeddingStageStatus(BaseModel):
    """Embedding stage outcome for operation-level summary rendering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempted: bool
    ok: bool
    category: str | None = None
    recovery_command: str | None = None
