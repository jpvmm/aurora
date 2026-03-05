from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir


APP_NAME = "aurora"
APP_AUTHOR = "aurora"
SETTINGS_FILENAME = "settings.json"
SERVER_STATE_FILENAME = "server-state.json"
SERVER_LOCK_FILENAME = "server.lock"
KB_LOCK_FILENAME = "kb.lock"
KB_MANIFEST_FILENAME = "kb-manifest.json"
KB_STATE_FILENAME = "kb-state.json"
KB_QMD_CORPUS_DIRNAME = "kb-qmd-corpus"
CONFIG_DIR_ENV = "AURORA_CONFIG_DIR"


def get_config_dir() -> Path:
    """Return the global per-user config directory for Aurora."""
    override = os.getenv(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()

    return Path(user_config_dir(APP_NAME, appauthor=APP_AUTHOR, roaming=False))


def get_settings_path() -> Path:
    """Return the absolute path for the persisted runtime settings file."""
    return get_config_dir() / SETTINGS_FILENAME


def get_server_state_path() -> Path:
    """Return the absolute path for persisted global lifecycle state."""
    return get_config_dir() / SERVER_STATE_FILENAME


def get_server_lock_path() -> Path:
    """Return the absolute path for lifecycle transition lock file."""
    return get_config_dir() / SERVER_LOCK_FILENAME


def get_kb_lock_path() -> Path:
    """Return the absolute path for KB mutation lock file."""
    return get_config_dir() / KB_LOCK_FILENAME


def get_kb_manifest_path() -> Path:
    """Return the absolute path for persisted KB manifest metadata."""
    return get_config_dir() / KB_MANIFEST_FILENAME


def get_kb_state_path() -> Path:
    """Return the absolute path for persisted KB operation state."""
    return get_config_dir() / KB_STATE_FILENAME


def get_kb_qmd_corpus_root_path() -> Path:
    """Return the root directory for Aurora-managed QMD corpus files."""
    return get_config_dir() / KB_QMD_CORPUS_DIRNAME


def get_kb_qmd_corpus_path(collection_name: str = "aurora-kb-managed") -> Path:
    """Return deterministic corpus path scoped by managed QMD collection name."""
    safe_collection = _normalize_collection_name(collection_name)
    return get_kb_qmd_corpus_root_path() / safe_collection


def ensure_config_dir() -> Path:
    """Create the config directory when missing and return it."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _normalize_collection_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip())
    normalized = normalized.strip(".-_")
    return normalized or "default"
