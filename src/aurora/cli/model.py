from __future__ import annotations

import json
import sys
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
from aurora.runtime.server_lifecycle import LifecycleHealth, LifecycleStatus, ServerLifecycleService
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


@model_app.command("start")
def model_start_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Reutiliza runtime externo sem prompt interativo.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Nao reutiliza runtime externo e tenta iniciar runtime gerenciado.",
    ),
) -> None:
    if yes and force:
        typer.echo("Use apenas uma opcao: --yes ou --force.", err=True)
        raise typer.Exit(code=1)

    service = ServerLifecycleService()
    interactive = _is_interactive_terminal()
    allow_external_reuse = True if yes else (False if force else None)
    decision_callback = None
    if interactive and allow_external_reuse is None:
        decision_callback = _confirm_external_reuse

    try:
        status = service.start_server(
            external_reuse_decision=decision_callback,
            allow_external_reuse=allow_external_reuse,
            non_interactive=not interactive,
            reason="manual_start",
        )
    except Exception as error:
        _render_lifecycle_error(error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_status(status, json_output=json_output)
    if json_output:
        return

    if status.ownership == "managed":
        typer.echo("Aviso: o servidor permanece ativo em background.")
        typer.echo("Para encerrar: aurora model stop")
    else:
        typer.echo("Runtime externo em uso.")
        typer.echo("Para manter comportamento atual: aurora model status")


@model_app.command("stop")
def model_stop_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Forca interrupcao mesmo em runtime externo registrado.",
    ),
) -> None:
    service = ServerLifecycleService()
    try:
        status = service.stop_server(force=force)
    except Exception as error:
        _render_lifecycle_error(error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_status(status, json_output=json_output)
    if json_output:
        raise typer.Exit(code=0 if status.lifecycle_state == "stopped" else 1)

    if status.ownership == "external":
        typer.echo("Servidor externo detectado; nao foi encerrado sem confirmacao explicita.")
        typer.echo("Se voce controla esse processo, execute: aurora model stop --force")
        raise typer.Exit(code=0)
    if status.lifecycle_state == "stopped":
        typer.echo("Runtime gerenciado encerrado com sucesso.")
        raise typer.Exit(code=0)
    raise typer.Exit(code=1)


@model_app.command("status")
def model_status_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    service = ServerLifecycleService()
    status = service.get_status()
    _render_status(status, json_output=json_output)


@model_app.command("health")
def model_health_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    service = ServerLifecycleService()
    health = service.check_health()
    _render_health(health, json_output=json_output)
    if not health.ok:
        raise typer.Exit(code=1)


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


def _render_status(status: LifecycleStatus, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(status.to_dict(), ensure_ascii=False, sort_keys=True))
        return

    typer.echo("Status do runtime")
    typer.echo(f"- estado: {status.lifecycle_state}")
    typer.echo(f"- ownership: {status.ownership or 'none'}")
    typer.echo(f"- endpoint: {status.endpoint_url}")
    typer.echo(f"- porta: {status.port}")
    typer.echo(f"- modelo: {status.model_id}")
    typer.echo(f"- pid: {status.pid or '-'}")
    typer.echo(f"- pgid: {status.process_group_id or '-'}")
    typer.echo(f"- uptime(s): {status.uptime_seconds if status.uptime_seconds is not None else '-'}")
    typer.echo(f"- pronto: {'sim' if status.ready else 'nao'}")
    if status.message:
        typer.echo(f"- detalhe: {status.message}")
    if status.error_category:
        typer.echo(f"- categoria: {status.error_category}")
    for command in status.recovery_commands:
        typer.echo(f"- recuperacao: {command}")


def _render_health(health: LifecycleHealth, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(health.to_dict(), ensure_ascii=False, sort_keys=True))
        return

    typer.echo("Saude do runtime")
    typer.echo(f"- ok: {'sim' if health.ok else 'nao'}")
    typer.echo(f"- endpoint: {health.endpoint_url}")
    typer.echo(f"- porta: {health.port}")
    typer.echo(f"- modelo: {health.model_id}")
    typer.echo(f"- ownership: {health.ownership or 'none'}")
    if health.category:
        typer.echo(f"- categoria: {health.category}")
    typer.echo(f"- mensagem: {health.message}")
    for command in health.recovery_commands:
        typer.echo(f"- recuperacao: {command}")


def _render_lifecycle_error(error: Exception, *, json_output: bool) -> None:
    category = getattr(error, "category", "endpoint_offline")
    message = str(error)
    recovery_commands = tuple(getattr(error, "recovery_commands", ()))
    if json_output:
        payload = {
            "ok": False,
            "category": category,
            "message": message,
            "recovery_commands": list(recovery_commands),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    typer.echo(f"[{category}] {message}", err=True)
    for command in recovery_commands:
        typer.echo(f"- {command}", err=True)


def _confirm_external_reuse(status: LifecycleStatus) -> bool:
    typer.echo(
        "Servidor externo detectado em "
        f"{status.endpoint_url} para o modelo {status.model_id}."
    )
    return typer.confirm("Deseja reutilizar este runtime externo?", default=True)


def _is_interactive_terminal() -> bool:
    stdin = getattr(sys, "stdin", None)
    stdout = getattr(sys, "stdout", None)
    return bool(stdin and stdout and stdin.isatty() and stdout.isatty())


__all__ = [
    "model_app",
    "model_health_command",
    "model_set_command",
    "model_start_command",
    "model_status_command",
    "model_stop_command",
]
