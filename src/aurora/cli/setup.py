from __future__ import annotations

import typer

from aurora.cli.model import model_set_command
from aurora.runtime.errors import RuntimeDiagnosticError
from aurora.runtime.llama_client import validate_runtime
from aurora.runtime.paths import get_settings_path
from aurora.runtime.settings import load_settings


setup_app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Assistente guiado de configuracao inicial.",
)


@setup_app.callback()
def setup_command(ctx: typer.Context) -> None:
    """Run guided setup wizard."""
    if ctx.invoked_subcommand is not None:
        return
    run_first_run_wizard()


def should_run_first_run_wizard() -> bool:
    return not get_settings_path().exists()


def run_first_run_wizard() -> None:
    typer.echo("Assistente de configuracao inicial do Aurora")

    while True:
        endpoint = typer.prompt(
            "Endpoint local llama.cpp",
            default="http://127.0.0.1:8080",
        )
        model_id = typer.prompt("Modelo padrao", default="Qwen3-8B-Q8_0")
        source = typer.prompt(
            "Fonte Hugging Face (opcional)",
            default="",
            show_default=False,
        ).strip()
        selected_source = source or None

        try:
            model_set_command(
                endpoint=endpoint,
                model=model_id,
                source=selected_source,
                yes=True,
            )
            validate_runtime(endpoint, model_id)
            break
        except RuntimeDiagnosticError as error:
            _print_runtime_error(error)
        except typer.Exit as error:
            if error.exit_code == 0:
                break
            typer.echo("Nao foi possivel validar a configuracao informada.", err=True)

        if not typer.confirm("Deseja corrigir e tentar novamente agora?", default=True):
            raise typer.Exit(code=1)

    _print_setup_summary()


def _print_runtime_error(error: RuntimeDiagnosticError) -> None:
    typer.echo(f"[{error.category}] {error.message}", err=True)
    typer.echo("Comandos de recuperacao:", err=True)
    for command in error.recovery_commands:
        typer.echo(f"- {command}", err=True)


def _print_setup_summary() -> None:
    settings = load_settings()

    typer.echo("")
    typer.echo("Resumo da configuracao:")
    typer.echo(f"- Endpoint: {settings.endpoint_url}")
    typer.echo(f"- Modelo: {settings.model_id}")
    typer.echo(f"- Fonte: {settings.model_source}")
    typer.echo(f"- Modo local-only: {'ativado' if settings.local_only else 'desativado'}")
    typer.echo(f"- Telemetria: {'ativada' if settings.telemetry_enabled else 'desativada'}")
    typer.echo("Para alterar o idioma: aurora config set language <codigo>")
    typer.echo("Proximo comando: aurora ask \"Ola\"")


__all__ = ["run_first_run_wizard", "setup_app", "setup_command", "should_run_first_run_wizard"]
