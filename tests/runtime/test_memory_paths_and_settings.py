"""Tests for memory path helpers, settings fields, and source field on RetrievedNote."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_get_memory_dir_returns_config_dir_slash_memory(tmp_path, monkeypatch):
    """get_memory_dir() returns get_config_dir() / 'memory'."""
    config_dir = tmp_path / "global-config"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))

    from aurora.runtime.paths import get_config_dir, get_memory_dir

    assert get_memory_dir() == get_config_dir() / "memory"


def test_get_preferences_path_returns_config_dir_slash_preferences_md(tmp_path, monkeypatch):
    """get_preferences_path() returns get_config_dir() / 'preferences.md'."""
    config_dir = tmp_path / "global-config"
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(config_dir))

    from aurora.runtime.paths import get_config_dir, get_preferences_path

    assert get_preferences_path() == get_config_dir() / "preferences.md"


# ---------------------------------------------------------------------------
# RetrievedNote source field
# ---------------------------------------------------------------------------


def test_retrieved_note_source_defaults_to_vault():
    """RetrievedNote(path, score, content) has source='vault' by default."""
    from aurora.retrieval.contracts import RetrievedNote

    note = RetrievedNote(path="x", score=0.9, content="c")
    assert note.source == "vault"


def test_retrieved_note_source_can_be_set_to_memory():
    """RetrievedNote accepts source='memory'."""
    from aurora.retrieval.contracts import RetrievedNote

    note = RetrievedNote(path="x", score=0.9, content="c", source="memory")
    assert note.source == "memory"


# ---------------------------------------------------------------------------
# RuntimeSettings memory fields
# ---------------------------------------------------------------------------


def test_runtime_settings_memory_top_k_defaults_to_5():
    """RuntimeSettings().memory_top_k must default to 5."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings()
    assert s.memory_top_k == 5


def test_runtime_settings_memory_min_score_defaults_to_0_25():
    """RuntimeSettings().memory_min_score must default to 0.25."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings()
    assert s.memory_min_score == 0.25


def test_runtime_settings_memory_top_k_below_minimum_raises():
    """RuntimeSettings(memory_top_k=2) must raise ValidationError (below 3)."""
    from aurora.runtime.settings import RuntimeSettings

    with pytest.raises(ValidationError):
        RuntimeSettings(memory_top_k=2)


def test_runtime_settings_memory_top_k_above_maximum_raises():
    """RuntimeSettings(memory_top_k=11) must raise ValidationError (above 10)."""
    from aurora.runtime.settings import RuntimeSettings

    with pytest.raises(ValidationError):
        RuntimeSettings(memory_top_k=11)
