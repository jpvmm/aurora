from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir


APP_NAME = "aurora"
APP_AUTHOR = "aurora"
SETTINGS_FILENAME = "settings.json"
SERVER_STATE_FILENAME = "server-state.json"
SERVER_LOCK_FILENAME = "server.lock"
KB_MANIFEST_FILENAME = "kb-manifest.json"
KB_STATE_FILENAME = "kb-state.json"
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


def get_kb_manifest_path() -> Path:
    """Return the absolute path for persisted KB manifest metadata."""
    return get_config_dir() / KB_MANIFEST_FILENAME


def get_kb_state_path() -> Path:
    """Return the absolute path for persisted KB operation state."""
    return get_config_dir() / KB_STATE_FILENAME


def ensure_config_dir() -> Path:
    """Create the config directory when missing and return it."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir
