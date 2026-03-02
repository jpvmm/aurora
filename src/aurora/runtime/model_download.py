from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from aurora.runtime.model_registry import resolve_cached_model
from aurora.runtime.model_source import HuggingFaceTarget


LARGE_DOWNLOAD_THRESHOLD_BYTES = 5 * 1024 * 1024 * 1024


class DownloadGuidanceError(RuntimeError):
    """Download failed with user-facing recovery instructions."""


@dataclass(frozen=True)
class DownloadRequest:
    target: HuggingFaceTarget
    private: bool = False
    token: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    source: str
    local_path: Path
    downloaded: bool
    used_token: bool


def download_model(
    request: DownloadRequest,
    *,
    confirm_download: Callable[[int, str], bool] | None = None,
    prompt_token: Callable[[], str | None] | None = None,
    progress_output: Callable[[str], None] | None = None,
) -> DownloadResult:
    """Resolve local model file path, downloading from HF only when required."""
    resolution = resolve_cached_model(request.target)
    if resolution.cached:
        return DownloadResult(
            source="cache",
            local_path=resolution.local_path,
            downloaded=False,
            used_token=False,
        )

    token = _resolve_token(request, prompt_token)
    remote_size = _estimate_remote_size_bytes(
        repo_id=request.target.repo_id,
        filename=request.target.filename,
        token=token,
    )

    if (
        remote_size is not None
        and remote_size >= LARGE_DOWNLOAD_THRESHOLD_BYTES
        and not _confirm_large_download(confirm_download, remote_size, request.target.filename)
    ):
        raise DownloadGuidanceError(
            "Download grande detectado. Reexecute e forneça confirmação para continuar."
        )

    try:
        local_path = _download_from_hf(
            repo_id=request.target.repo_id,
            filename=request.target.filename,
            destination_path=resolution.local_path,
            token=token,
            progress_callback=lambda **event: _emit_progress(progress_output, **event),
        )
    except ConnectionError as error:
        raise DownloadGuidanceError(
            "Falha de download: sem conexão com a internet. Verifique sua rede e tente novamente."
        ) from error
    except PermissionError as error:
        raise DownloadGuidanceError(
            "Falha de autenticação no Hugging Face. Forneça um token válido e tente novamente."
        ) from error
    except DownloadGuidanceError:
        raise
    except Exception as error:  # pragma: no cover - defensive path
        raise DownloadGuidanceError(
            "Falha ao baixar o modelo. Revise o source informado e tente novamente."
        ) from error

    return DownloadResult(
        source="huggingface",
        local_path=local_path,
        downloaded=True,
        used_token=bool(token),
    )


def _resolve_token(
    request: DownloadRequest,
    prompt_token: Callable[[], str | None] | None,
) -> str | None:
    token = request.token
    if token:
        return token

    if not request.private:
        return None

    if prompt_token is None:
        raise DownloadGuidanceError(
            "Este modelo exige token do Hugging Face. Informe um token e tente novamente."
        )

    prompted = (prompt_token() or "").strip()
    if not prompted:
        raise DownloadGuidanceError(
            "Token vazio. Gere um token no Hugging Face e execute o comando novamente."
        )
    return prompted


def _confirm_large_download(
    confirm_download: Callable[[int, str], bool] | None,
    size_bytes: int,
    filename: str,
) -> bool:
    if confirm_download is None:
        return False
    return bool(confirm_download(size_bytes, filename))


def _emit_progress(
    progress_output: Callable[[str], None] | None,
    *,
    downloaded_bytes: int,
    total_bytes: int,
    eta_seconds: int | None,
) -> None:
    if progress_output is None:
        return
    progress_output(_format_progress(downloaded_bytes, total_bytes, eta_seconds))


def _format_progress(downloaded_bytes: int, total_bytes: int, eta_seconds: int | None) -> str:
    safe_total = max(total_bytes, 1)
    percent = min(downloaded_bytes / safe_total * 100, 100)
    eta = "ETA --" if eta_seconds is None else f"ETA {eta_seconds}s"
    return (
        f"{percent:.1f}% - {_format_bytes(downloaded_bytes)} / {_format_bytes(total_bytes)} - {eta}"
    )


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    return f"{value / (1024 * 1024 * 1024):.1f} GB"


def _estimate_remote_size_bytes(*, repo_id: str, filename: str, token: str | None) -> int | None:
    try:
        from huggingface_hub import HfApi
    except ImportError:  # pragma: no cover - tested through mocked function
        return None

    try:
        model_info = HfApi().model_info(repo_id=repo_id, token=token)
    except Exception:  # pragma: no cover - defensive path
        return None

    for sibling in model_info.siblings or []:
        if sibling.rfilename == filename:
            return sibling.size
    return None


def _download_from_hf(
    *,
    repo_id: str,
    filename: str,
    destination_path: Path,
    token: str | None,
    progress_callback: Callable[..., None],
) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as error:  # pragma: no cover - tested through mocked function
        raise DownloadGuidanceError(
            "Dependência ausente para download Hugging Face. Instale `huggingface_hub`."
        ) from error

    destination_path.parent.mkdir(parents=True, exist_ok=True)

    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        token=token,
        local_dir=str(destination_path.parent),
        local_dir_use_symlinks=False,
        force_download=False,
    )
    downloaded_path = Path(downloaded)
    file_size = downloaded_path.stat().st_size
    progress_callback(downloaded_bytes=file_size, total_bytes=file_size, eta_seconds=0)
    return downloaded_path
