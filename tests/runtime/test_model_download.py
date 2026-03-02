from __future__ import annotations

from pathlib import Path

import pytest

from aurora.runtime.model_download import (
    DownloadGuidanceError,
    DownloadRequest,
    DownloadResult,
    download_model,
)
from aurora.runtime.model_source import parse_hf_target


def test_download_model_uses_cache_and_skips_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    request = DownloadRequest(target=parse_hf_target("Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"))

    cached_path = (
        tmp_path / "config" / "models" / "Qwen--Qwen3-8B-GGUF" / "Qwen3-8B-Q8_0.gguf"
    )
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"gguf")

    def unexpected_download(**_: object) -> Path:
        raise AssertionError("Network download should not run when cache is available.")

    monkeypatch.setattr("aurora.runtime.model_download._download_from_hf", unexpected_download)

    result = download_model(request)

    assert isinstance(result, DownloadResult)
    assert result.source == "cache"
    assert result.local_path == cached_path
    assert result.downloaded is False


def test_large_download_requires_explicit_confirmation(monkeypatch) -> None:
    request = DownloadRequest(target=parse_hf_target("Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"))
    monkeypatch.setattr(
        "aurora.runtime.model_download._estimate_remote_size_bytes",
        lambda **_: 8 * 1024 * 1024 * 1024,
    )

    with pytest.raises(DownloadGuidanceError, match="confirma"):
        download_model(request, confirm_download=lambda *_: False)


def test_private_download_prompts_for_token_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    request = DownloadRequest(
        target=parse_hf_target("meta-llama/Llama-3-8B-GGUF:llama-3-8b.Q4_K_M.gguf"),
        private=True,
    )

    monkeypatch.setattr("aurora.runtime.model_download._estimate_remote_size_bytes", lambda **_: None)

    def fake_download_from_hf(**kwargs: object) -> Path:
        assert kwargs["token"] == "hf_secret_abc"
        return kwargs["destination_path"]

    monkeypatch.setattr("aurora.runtime.model_download._download_from_hf", fake_download_from_hf)

    prompted = {"count": 0}

    def ask_token() -> str:
        prompted["count"] += 1
        return "hf_secret_abc"

    result = download_model(
        request,
        prompt_token=ask_token,
        confirm_download=lambda *_: True,
    )

    assert prompted["count"] == 1
    assert result.used_token is True


def test_download_progress_reports_percent_size_and_eta(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    request = DownloadRequest(target=parse_hf_target("Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"))
    monkeypatch.setattr("aurora.runtime.model_download._estimate_remote_size_bytes", lambda **_: None)

    def fake_download_from_hf(**kwargs: object) -> Path:
        progress = kwargs["progress_callback"]
        progress(downloaded_bytes=50, total_bytes=100, eta_seconds=12)
        return kwargs["destination_path"]

    monkeypatch.setattr("aurora.runtime.model_download._download_from_hf", fake_download_from_hf)

    updates: list[str] = []
    result = download_model(request, progress_output=updates.append, confirm_download=lambda *_: True)

    assert result.source == "huggingface"
    assert updates
    assert "50.0%" in updates[0]
    assert "50 B / 100 B" in updates[0]
    assert "ETA 12s" in updates[0]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConnectionError("offline"), "sem conexão"),
        (PermissionError("401 unauthorized"), "token"),
        (RuntimeError("corrupted transfer"), "tente novamente"),
    ],
)
def test_download_errors_are_mapped_to_guided_retry_messages(
    monkeypatch,
    tmp_path: Path,
    error: Exception,
    expected: str,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    request = DownloadRequest(target=parse_hf_target("Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf"))
    monkeypatch.setattr("aurora.runtime.model_download._estimate_remote_size_bytes", lambda **_: None)
    monkeypatch.setattr(
        "aurora.runtime.model_download._download_from_hf",
        lambda **_: (_ for _ in ()).throw(error),
    )

    with pytest.raises(DownloadGuidanceError, match=expected):
        download_model(request, confirm_download=lambda *_: True)
