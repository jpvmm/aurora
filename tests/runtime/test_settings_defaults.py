from __future__ import annotations

import os

from aurora.runtime.paths import get_config_dir, get_settings_path
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings


def test_settings_path_is_global_and_cwd_independent(tmp_path, monkeypatch):
    config_dir = tmp_path / "global-config"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))

    cwd_a = tmp_path / "cwd-a"
    cwd_b = tmp_path / "cwd-b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    previous_cwd = os.getcwd()
    try:
        os.chdir(cwd_a)
        first = get_settings_path()
        os.chdir(cwd_b)
        second = get_settings_path()
    finally:
        os.chdir(previous_cwd)

    assert get_config_dir() == config_dir
    assert first == config_dir / "settings.json"
    assert second == config_dir / "settings.json"


def test_defaults_are_privacy_first(tmp_path, monkeypatch):
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    settings = load_settings()

    assert settings.endpoint_url == "http://127.0.0.1:8080"
    assert settings.model_id == "Qwen3-8B-Q8_0"
    assert settings.model_source == "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"
    assert settings.local_only is True
    assert settings.telemetry_enabled is False


def test_settings_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    initial = load_settings()
    save_settings(initial)

    loaded = load_settings()
    assert loaded == initial

    updated = RuntimeSettings(
        endpoint_url="http://localhost:8081",
        model_id="Qwen3-8B-Q8_0",
        model_source="Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
        local_only=True,
        telemetry_enabled=False,
    )
    save_settings(updated)

    reloaded = load_settings()
    assert reloaded == updated
