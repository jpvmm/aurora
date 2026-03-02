from __future__ import annotations

from pathlib import Path

import pytest

from aurora.runtime.model_registry import resolve_cached_model
from aurora.runtime.model_source import (
    ModelSourceValidationError,
    parse_hf_target,
)


def test_parse_hf_target_extracts_repo_and_filename() -> None:
    target = parse_hf_target("Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf")

    assert target.repo_id == "Qwen/Qwen3-8B-GGUF"
    assert target.filename == "Qwen3-8B-Q8_0.gguf"


@pytest.mark.parametrize(
    ("source", "expected_error"),
    [
        ("Qwen/Qwen3-8B-GGUF", "Use o formato"),
        ("Qwen/Qwen3-8B-GGUF:model.bin", ".gguf"),
        ("Qwen/Qwen3-8B-GGUF:subdir/model.gguf", "somente o nome do arquivo"),
        ("Qwen::model.gguf", "repo no formato"),
    ],
)
def test_parse_hf_target_returns_actionable_pt_br_errors(
    source: str,
    expected_error: str,
) -> None:
    with pytest.raises(ModelSourceValidationError) as error:
        parse_hf_target(source)

    assert expected_error in str(error.value)
    assert "aurora model set --source" in str(error.value)


def test_cached_model_is_preferred_when_file_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    source = "Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"

    parsed = parse_hf_target(source)
    cached_path = tmp_path / "config" / "models" / "Qwen--Qwen3-8B-GGUF" / parsed.filename
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"gguf")

    resolution = resolve_cached_model(parsed)

    assert resolution.cached is True
    assert resolution.preferred_source == "cache"
    assert resolution.local_path == cached_path


def test_cache_resolution_returns_deterministic_global_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "aurora-config"))
    parsed = parse_hf_target("TheBloke/Mistral-7B-v0.1-GGUF:mistral-7b.q4_k_m.gguf")

    resolution = resolve_cached_model(parsed)

    assert resolution.cached is False
    assert resolution.preferred_source == "huggingface"
    assert resolution.local_path == (
        tmp_path
        / "aurora-config"
        / "models"
        / "TheBloke--Mistral-7B-v0.1-GGUF"
        / "mistral-7b.q4_k_m.gguf"
    )
