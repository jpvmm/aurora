from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aurora.runtime.model_source import HuggingFaceTarget
from aurora.runtime.paths import get_config_dir


MODELS_DIRNAME = "models"


@dataclass(frozen=True)
class ModelResolution:
    """Deterministic metadata for choosing local cache vs remote download."""

    repo_id: str
    filename: str
    local_path: Path
    cached: bool
    preferred_source: str


def get_models_dir() -> Path:
    """Return Aurora global model directory path."""
    return get_config_dir() / MODELS_DIRNAME


def resolve_cached_model(target: HuggingFaceTarget) -> ModelResolution:
    """Resolve cache metadata for an HF target using global Aurora model directory."""
    repo_dir = _to_cache_dir(target.repo_id)
    local_path = get_models_dir() / repo_dir / target.filename
    cached = local_path.exists()
    preferred_source = "cache" if cached else "huggingface"
    return ModelResolution(
        repo_id=target.repo_id,
        filename=target.filename,
        local_path=local_path,
        cached=cached,
        preferred_source=preferred_source,
    )


def _to_cache_dir(repo_id: str) -> str:
    return repo_id.replace("/", "--")
