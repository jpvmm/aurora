from __future__ import annotations

from typing import Callable

import typer

from aurora.privacy.policy import Phase1PolicyError
from aurora.runtime.model_download import (
    DownloadGuidanceError,
    DownloadRequest,
    DownloadResult,
    download_model,
)
from aurora.runtime.model_source import ModelSourceValidationError, parse_hf_target
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings


model_app = typer.Typer(
    no_args_is_help=True,
    help="Comandos de configuração de modelos locais.",
)


@model_app.command("set")
def model_set_command(
    endpoint: str | None = typer.Option(None, "--endpoint", help="Endpoint local llama.cpp."),
    model: str | None = typer.Option(None, "--model", help="Identificador padrão do modelo."),
    source: str | None = typer.Option(
        None,
        "--source",
        help="Fonte Hugging Face no formato repo/model:arquivo.gguf.",
    ),
    private: bool = typer.Option(
        False,
        "--private",
        help="Indica que o modelo exige token privado do Hugging Face.",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Token do Hugging Face para modelos privados.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Aceita confirmação de download grande sem prompt interativo.",
    ),
) -> None:
    """Persist global model runtime config with optional HF source resolution."""
    current = load_settings()
    model_source = source or current.model_source
    model_id = model or current.model_id
    endpoint_url = endpoint or current.endpoint_url

    download_result: DownloadResult | None = None

    if source is not None:
        try:
            target = parse_hf_target(source)
        except ModelSourceValidationError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1)

        confirm_download = _build_confirm_callback(yes)
        prompt_token = _build_token_prompt(private=private, token=token)

        try:
            download_result = download_model(
                DownloadRequest(target=target, private=private, token=token),
                confirm_download=confirm_download,
                prompt_token=prompt_token,
                progress_output=lambda line: typer.echo(f"[download] {line}"),
            )
        except DownloadGuidanceError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1)

        if model is None:
            model_id = target.filename

    try:
        save_settings(
            RuntimeSettings(
                endpoint_url=endpoint_url,
                model_id=model_id,
                model_source=model_source,
                local_only=current.local_only,
                telemetry_enabled=current.telemetry_enabled,
            )
        )
    except Phase1PolicyError as error:
        typer.echo(str(error), err=True)
        typer.echo(
            "Recuperação: aurora model set --endpoint http://127.0.0.1:8080",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo("Configuração de modelo atualizada com sucesso.")
    if download_result is not None:
        typer.echo(f"Modelo disponível em: {download_result.local_path}")
    typer.echo("Próximo passo: execute `aurora doctor` para validar o runtime local.")


def _build_confirm_callback(force_yes: bool) -> Callable[[int, str], bool]:
    if force_yes:
        return lambda *_: True

    def _confirm(size_bytes: int, filename: str) -> bool:
        size_gb = size_bytes / (1024 * 1024 * 1024)
        return typer.confirm(
            f"O arquivo {filename} tem aproximadamente {size_gb:.2f} GB. Deseja continuar?"
        )

    return _confirm


def _build_token_prompt(
    *,
    private: bool,
    token: str | None,
) -> Callable[[], str | None] | None:
    if not private or token:
        return None

    def _prompt() -> str:
        return typer.prompt("Token Hugging Face", hide_input=True)

    return _prompt


__all__ = ["model_app", "model_set_command"]
