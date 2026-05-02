from __future__ import annotations

import os
import json

import pytest

from aurora.runtime.paths import (
    get_config_dir,
    get_kb_manifest_path,
    get_kb_state_path,
    get_settings_path,
)
from aurora.runtime.settings import (
    RuntimeSettings,
    RuntimeSettingsLoadError,
    load_settings,
    save_settings,
    telemetry_defaults_env,
)


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
    assert settings.kb_vault_path == ""
    assert settings.kb_include == ()
    assert settings.kb_exclude == ()
    assert ".obsidian/**" in settings.kb_default_excludes
    assert settings.kb_qmd_index_name == "aurora-kb"
    assert settings.kb_qmd_collection_name == "aurora-kb-managed"
    assert settings.kb_auto_embeddings_enabled is True


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
        kb_vault_path="/vault",
        kb_include=("notes/**", "daily/**"),
        kb_exclude=(".obsidian/**", "notes/private/**"),
        kb_default_excludes=(".obsidian/**", ".DS_Store"),
        kb_qmd_index_name="aurora-index",
        kb_qmd_collection_name="aurora-collection",
        kb_auto_embeddings_enabled=False,
    )
    save_settings(updated)

    reloaded = load_settings()
    assert reloaded == updated

    serialized = get_settings_path().read_text(encoding="utf-8")
    payload = json.loads(serialized)
    assert list(payload.keys()) == sorted(payload.keys())
    assert payload["kb_vault_path"] == "/vault"
    assert payload["kb_include"] == ["daily/**", "notes/**"]
    assert payload["kb_exclude"] == [".obsidian/**", "notes/private/**"]
    assert payload["kb_qmd_index_name"] == "aurora-index"
    assert payload["kb_qmd_collection_name"] == "aurora-collection"
    assert payload["kb_auto_embeddings_enabled"] is False


def test_kb_paths_use_global_config_directory(tmp_path, monkeypatch):
    config_dir = tmp_path / "global-config"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))

    assert get_kb_manifest_path() == config_dir / "kb-manifest.json"
    assert get_kb_state_path() == config_dir / "kb-state.json"


def test_load_settings_raises_actionable_error_on_invalid_kb_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    get_settings_path().write_text(
        json.dumps(
            {
                "endpoint_url": "http://127.0.0.1:8080",
                "model_id": "Qwen3-8B-Q8_0",
                "model_source": "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
                "local_only": True,
                "telemetry_enabled": False,
                "kb_vault_path": "/vault",
                "kb_include": "notes/**",
                "kb_exclude": [],
                "kb_default_excludes": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeSettingsLoadError) as error:
        load_settings()

    message = str(error.value)
    assert "kb_include" in message
    assert "aurora config show" in message


def test_telemetry_defaults_for_phase1_are_disabled():
    assert telemetry_defaults_env() == {
        "AGNO_TELEMETRY": "false",
        "GRAPHITI_TELEMETRY_ENABLED": "false",
    }


# ---------------------------------------------------------------------------
# Iterative retrieval settings (Phase 7-01)
# ---------------------------------------------------------------------------


def test_iterative_retrieval_defaults_match_research():
    s = RuntimeSettings()
    assert s.iterative_retrieval_enabled is True
    assert s.iterative_retrieval_judge is False
    assert s.retrieval_min_top_score == 0.35
    assert s.retrieval_min_hits == 2
    assert s.retrieval_min_context_chars == 800
    assert s.iterative_retrieval_jaccard_threshold == 0.7


def test_retrieval_min_top_score_validator_pt_br_error():
    from pydantic import ValidationError

    # boundary valid
    assert RuntimeSettings(retrieval_min_top_score=0.0).retrieval_min_top_score == 0.0
    assert RuntimeSettings(retrieval_min_top_score=1.0).retrieval_min_top_score == 1.0
    # invalid
    with pytest.raises(ValidationError) as exc:
        RuntimeSettings(retrieval_min_top_score=1.01)
    assert "retrieval_min_top_score deve estar entre 0.0 e 1.0." in str(exc.value)
    with pytest.raises(ValidationError) as exc2:
        RuntimeSettings(retrieval_min_top_score=-0.01)
    assert "retrieval_min_top_score deve estar entre 0.0 e 1.0." in str(exc2.value)


def test_retrieval_min_hits_validator_pt_br_error():
    from pydantic import ValidationError

    assert RuntimeSettings(retrieval_min_hits=1).retrieval_min_hits == 1
    assert RuntimeSettings(retrieval_min_hits=10).retrieval_min_hits == 10
    with pytest.raises(ValidationError) as exc:
        RuntimeSettings(retrieval_min_hits=0)
    assert "retrieval_min_hits deve estar entre 1 e 10." in str(exc.value)
    with pytest.raises(ValidationError) as exc2:
        RuntimeSettings(retrieval_min_hits=11)
    assert "retrieval_min_hits deve estar entre 1 e 10." in str(exc2.value)


def test_retrieval_min_context_chars_validator_pt_br_error():
    from pydantic import ValidationError

    assert RuntimeSettings(retrieval_min_context_chars=100).retrieval_min_context_chars == 100
    assert RuntimeSettings(retrieval_min_context_chars=24_000).retrieval_min_context_chars == 24_000
    with pytest.raises(ValidationError) as exc:
        RuntimeSettings(retrieval_min_context_chars=99)
    assert "retrieval_min_context_chars deve estar entre 100 e 24000." in str(exc.value)
    with pytest.raises(ValidationError) as exc2:
        RuntimeSettings(retrieval_min_context_chars=24_001)
    assert "retrieval_min_context_chars deve estar entre 100 e 24000." in str(exc2.value)


def test_iterative_retrieval_jaccard_threshold_validator_pt_br_error():
    from pydantic import ValidationError

    assert RuntimeSettings(iterative_retrieval_jaccard_threshold=0.0).iterative_retrieval_jaccard_threshold == 0.0
    assert RuntimeSettings(iterative_retrieval_jaccard_threshold=1.0).iterative_retrieval_jaccard_threshold == 1.0
    with pytest.raises(ValidationError) as exc:
        RuntimeSettings(iterative_retrieval_jaccard_threshold=1.01)
    assert "iterative_retrieval_jaccard_threshold deve estar entre 0.0 e 1.0." in str(exc.value)
    with pytest.raises(ValidationError) as exc2:
        RuntimeSettings(iterative_retrieval_jaccard_threshold=-0.01)
    assert "iterative_retrieval_jaccard_threshold deve estar entre 0.0 e 1.0." in str(exc2.value)


def test_iterative_retrieval_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    original = RuntimeSettings(
        iterative_retrieval_enabled=False,
        iterative_retrieval_judge=True,
        retrieval_min_top_score=0.5,
        retrieval_min_hits=3,
        retrieval_min_context_chars=1200,
        iterative_retrieval_jaccard_threshold=0.65,
    )
    save_settings(original)
    reloaded = load_settings()
    assert reloaded.iterative_retrieval_enabled is False
    assert reloaded.iterative_retrieval_judge is True
    assert reloaded.retrieval_min_top_score == 0.5
    assert reloaded.retrieval_min_hits == 3
    assert reloaded.retrieval_min_context_chars == 1200
    assert reloaded.iterative_retrieval_jaccard_threshold == 0.65
