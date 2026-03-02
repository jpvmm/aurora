from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from aurora.runtime.paths import ensure_config_dir, get_settings_path


class RuntimeSettings(BaseSettings):
    """Runtime settings persisted globally per user."""

    endpoint_url: str = "http://127.0.0.1:8080"
    model_id: str = "Qwen3-8B-Q8_0"
    model_source: str = "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"
    local_only: bool = True
    telemetry_enabled: bool = False

    model_config = SettingsConfigDict(extra="ignore")


def load_settings() -> RuntimeSettings:
    """Load persisted runtime settings or return privacy-first defaults."""
    settings_path = get_settings_path()
    if not settings_path.exists():
        return RuntimeSettings()

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    return RuntimeSettings.model_validate(payload)


def save_settings(settings: RuntimeSettings) -> RuntimeSettings:
    """Persist runtime settings and return normalized values."""
    ensure_config_dir()
    settings_path = get_settings_path()
    normalized = RuntimeSettings.model_validate(settings.model_dump())
    _write_settings_file(settings_path, normalized)
    return normalized


def _write_settings_file(path: Path, settings: RuntimeSettings) -> None:
    serialized = json.dumps(
        settings.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(f"{serialized}\n", encoding="utf-8")

