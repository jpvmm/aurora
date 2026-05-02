from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aurora.kb.contracts import DEFAULT_SCOPE_EXCLUDES
from aurora.privacy.policy import validate_local_endpoint
from aurora.runtime.paths import ensure_config_dir, get_settings_path

TELEMETRY_DEFAULTS = {
    "AGNO_TELEMETRY": "false",
    "GRAPHITI_TELEMETRY_ENABLED": "false",
}


class RuntimeSettingsLoadError(ValueError):
    """Raised when persisted runtime settings cannot be loaded safely."""


class RuntimeSettings(BaseSettings):
    """Runtime settings persisted globally per user."""

    endpoint_url: str = "http://127.0.0.1:8080"
    model_id: str = "Qwen3-8B-Q8_0"
    model_source: str = "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"
    local_only: bool = True
    telemetry_enabled: bool = False
    kb_vault_path: str = ""
    kb_include: tuple[str, ...] = ()
    kb_exclude: tuple[str, ...] = ()
    kb_default_excludes: tuple[str, ...] = DEFAULT_SCOPE_EXCLUDES
    kb_qmd_index_name: str = "aurora-kb"
    kb_qmd_collection_name: str = "aurora-kb-managed"
    kb_auto_embeddings_enabled: bool = True
    kb_scheduler_enabled: bool = False
    kb_scheduler_hour_local: int = 9
    retrieval_top_k: int = 15
    retrieval_min_score: float = 0.30
    chat_history_max_turns: int = 10
    memory_top_k: int = 5
    memory_min_score: float = 0.25
    iterative_retrieval_enabled: bool = True
    iterative_retrieval_judge: bool = False
    retrieval_min_top_score: float = 0.35
    retrieval_min_hits: int = 2
    retrieval_min_context_chars: int = 800
    iterative_retrieval_jaccard_threshold: float = 0.7

    model_config = SettingsConfigDict(extra="ignore")

    @field_validator("kb_include", "kb_exclude", mode="before")
    @classmethod
    def _normalize_kb_scope_rules(cls, value: object) -> tuple[str, ...]:
        return _normalize_scope_patterns(field_name="kb_include/exclude", value=value)

    @field_validator("kb_default_excludes", mode="before")
    @classmethod
    def _normalize_kb_default_excludes(cls, value: object) -> tuple[str, ...]:
        normalized = _normalize_scope_patterns(field_name="kb_default_excludes", value=value)
        return normalized or DEFAULT_SCOPE_EXCLUDES

    @field_validator("kb_qmd_index_name", "kb_qmd_collection_name", mode="before")
    @classmethod
    def _normalize_qmd_identifier(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Identificador QMD deve ser texto.")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Identificador QMD nao pode ser vazio.")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("Identificador QMD nao pode conter separadores de caminho.")
        return normalized

    @field_validator("kb_scheduler_hour_local")
    @classmethod
    def _validate_scheduler_hour(cls, value: int) -> int:
        if value < 0 or value > 23:
            raise ValueError("kb_scheduler_hour_local deve estar entre 0 e 23.")
        return value

    @field_validator("retrieval_top_k")
    @classmethod
    def _validate_retrieval_top_k(cls, value: int) -> int:
        if value < 5 or value > 30:
            raise ValueError("retrieval_top_k deve estar entre 5 e 30.")
        return value

    @field_validator("memory_top_k")
    @classmethod
    def _validate_memory_top_k(cls, value: int) -> int:
        if value < 3 or value > 10:
            raise ValueError("memory_top_k deve estar entre 3 e 10.")
        return value

    @field_validator("retrieval_min_top_score")
    @classmethod
    def _validate_min_top_score(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("retrieval_min_top_score deve estar entre 0.0 e 1.0.")
        return value

    @field_validator("retrieval_min_hits")
    @classmethod
    def _validate_min_hits(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("retrieval_min_hits deve estar entre 1 e 10.")
        return value

    @field_validator("retrieval_min_context_chars")
    @classmethod
    def _validate_min_context_chars(cls, value: int) -> int:
        if value < 100 or value > 24_000:
            raise ValueError("retrieval_min_context_chars deve estar entre 100 e 24000.")
        return value

    @field_validator("iterative_retrieval_jaccard_threshold")
    @classmethod
    def _validate_jaccard_threshold(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("iterative_retrieval_jaccard_threshold deve estar entre 0.0 e 1.0.")
        return value


def load_settings() -> RuntimeSettings:
    """Load persisted runtime settings or return privacy-first defaults."""
    settings_path = get_settings_path()
    if not settings_path.exists():
        default_settings = RuntimeSettings()
        _validate_policy(default_settings)
        return default_settings

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        settings = RuntimeSettings.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, OSError) as error:
        raise RuntimeSettingsLoadError(_build_load_error_message(settings_path, error)) from error
    _validate_policy(settings)
    return settings


def save_settings(settings: RuntimeSettings) -> RuntimeSettings:
    """Persist runtime settings and return normalized values."""
    ensure_config_dir()
    settings_path = get_settings_path()
    normalized = RuntimeSettings.model_validate(settings.model_dump())
    _validate_policy(normalized)
    _write_settings_file(settings_path, normalized)
    return normalized


def telemetry_defaults_env() -> dict[str, str]:
    """Expose canonical telemetry defaults for Phase 1 commands."""
    return dict(TELEMETRY_DEFAULTS)


def _validate_policy(settings: RuntimeSettings) -> None:
    validate_local_endpoint(settings.endpoint_url, local_only=settings.local_only)


def _write_settings_file(path: Path, settings: RuntimeSettings) -> None:
    serialized = json.dumps(
        settings.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(f"{serialized}\n", encoding="utf-8")


def _normalize_scope_patterns(*, field_name: str, value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise ValueError(f"{field_name} deve ser uma lista de padrões.")
    if not isinstance(value, (list, tuple, set)):
        raise ValueError(f"{field_name} deve ser uma lista de padrões.")

    normalized: set[str] = set()
    for item in value:
        text = str(item).strip()
        if text:
            normalized.add(text)
    return tuple(sorted(normalized))


def _build_load_error_message(path: Path, error: Exception) -> str:
    return (
        f"Falha ao carregar configuracao global em {path}. "
        f"Detalhe: {error}. "
        "Recuperacao: ajuste o JSON manualmente ou recrie o arquivo com valores validos "
        "e execute `aurora config show` para validar."
    )
