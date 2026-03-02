from __future__ import annotations

from dataclasses import dataclass

import typer

from aurora.cli.config import mask_sensitive
from aurora.privacy.policy import Phase1PolicyError
from aurora.runtime.errors import RuntimeDiagnosticError
from aurora.runtime.llama_client import validate_runtime
from aurora.runtime.settings import load_settings


@dataclass(frozen=True)
class DoctorIssue:
    category: str
    message: str
    commands: tuple[str, ...]


doctor_app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Diagnostico de runtime local e privacidade.",
)


@doctor_app.callback()
def doctor_command(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    run_doctor_checks()


def run_doctor_checks() -> None:
    try:
        settings = load_settings()
    except Phase1PolicyError:
        _print_issues(
            [
                DoctorIssue(
                    category="policy_mismatch",
                    message="Endpoint configurado viola a politica local-only.",
                    commands=(
                        "aurora model set --endpoint http://127.0.0.1:8080",
                        "aurora config show",
                    ),
                )
            ]
        )
        raise typer.Exit(code=1)

    issues: list[DoctorIssue] = []
    if not settings.local_only:
        issues.append(
            DoctorIssue(
                category="policy_mismatch",
                message="A configuracao atual desativou local-only para esta fase.",
                commands=(
                    "aurora model set --endpoint http://127.0.0.1:8080",
                    "aurora config show",
                ),
            )
        )

    try:
        validate_runtime(settings.endpoint_url, settings.model_id)
    except RuntimeDiagnosticError as error:
        issues.append(
            DoctorIssue(
                category=error.category,
                message=error.message,
                commands=error.recovery_commands,
            )
        )

    typer.echo("Diagnostico Aurora")
    typer.echo(f"- endpoint: {mask_sensitive(settings.endpoint_url)}")
    typer.echo(f"- model: {settings.model_id}")
    typer.echo(f"- local-only: {'ativado' if settings.local_only else 'desativado'}")
    typer.echo(f"- telemetria: {'ativada' if settings.telemetry_enabled else 'desativada'}")

    if issues:
        _print_issues(issues)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Runtime local pronto. Nenhum problema encontrado.")


def _print_issues(issues: list[DoctorIssue]) -> None:
    headings = {
        "endpoint_offline": "Conectividade",
        "timeout": "Conectividade",
        "invalid_token": "Autenticacao",
        "model_missing": "Modelo",
        "policy_mismatch": "Privacidade",
    }
    printed_groups: set[str] = set()

    typer.echo("")
    typer.echo("Problemas encontrados:")
    for issue in issues:
        group_name = headings.get(issue.category, "Diagnostico")
        if group_name not in printed_groups:
            typer.echo(f"[{group_name}]")
            printed_groups.add(group_name)
        typer.echo(f"- {issue.message}")
        for command in issue.commands:
            typer.echo(f"  -> {command}")


__all__ = ["doctor_app", "doctor_command", "run_doctor_checks"]
