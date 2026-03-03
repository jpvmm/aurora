from __future__ import annotations

import json

import typer

from aurora.kb.contracts import KBOperationCounters, KBOperationSummary, KBScopeConfig
from aurora.runtime.settings import load_settings


kb_app = typer.Typer(
    no_args_is_help=True,
    help="Comandos de ciclo de vida da base de conhecimento do vault.",
)


@kb_app.command("ingest")
def kb_ingest_command(
    vault_path: str = typer.Argument(..., help="Caminho absoluto do vault Obsidian."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Mostra escopo e contadores sem aplicar indexacao.",
    ),
) -> None:
    summary = _build_summary(operation="ingest", vault_path=vault_path, dry_run=dry_run)
    _fail_fast_not_ready(operation="ingest", summary=summary, json_output=json_output)


@kb_app.command("update")
def kb_update_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Mostra alteracoes planejadas sem atualizar o indice.",
    ),
) -> None:
    summary = _build_summary(operation="update", dry_run=dry_run)
    _fail_fast_not_ready(operation="update", summary=summary, json_output=json_output)


@kb_app.command("delete")
def kb_delete_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    summary = _build_summary(operation="delete", dry_run=False)
    _fail_fast_not_ready(operation="delete", summary=summary, json_output=json_output)


@kb_app.command("rebuild")
def kb_rebuild_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Mostra escopo e contadores previstos sem reconstruir o indice.",
    ),
) -> None:
    summary = _build_summary(operation="rebuild", dry_run=dry_run)
    _fail_fast_not_ready(operation="rebuild", summary=summary, json_output=json_output)


def _build_summary(
    *,
    operation: str,
    dry_run: bool,
    vault_path: str | None = None,
) -> KBOperationSummary:
    settings = load_settings()
    effective_vault = (vault_path or settings.kb_vault_path).strip() or "<vault-nao-configurado>"
    scope = KBScopeConfig(
        vault_root=effective_vault,
        include=settings.kb_include,
        exclude=settings.kb_exclude,
        default_excludes=settings.kb_default_excludes,
    )
    counters = KBOperationCounters(read=0, indexed=0, updated=0, removed=0, skipped=0, errors=1)
    return KBOperationSummary(
        operation=operation,
        dry_run=dry_run,
        duration_seconds=0.0,
        counters=counters,
        scope=scope,
        diagnostics=(),
    )


def _fail_fast_not_ready(
    *,
    operation: str,
    summary: KBOperationSummary,
    json_output: bool,
) -> None:
    recovery = (
        "Revise o escopo global com `aurora config show`.",
        f"Tente novamente quando o servico KB da Fase 2 estiver habilitado: `aurora kb {operation}`.",
    )
    diagnostic = {
        "categoria": "kb_service_unavailable",
        "mensagem": "Comando KB ainda nao conectado ao servico de indexacao desta fase.",
        "fase": "Fase 2 - Vault Knowledge Base Lifecycle",
        "recuperacao": list(recovery),
        "summary": summary.model_dump(mode="json"),
    }

    if json_output:
        typer.echo(json.dumps(diagnostic, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo("Operacao KB indisponivel no momento.")
        typer.echo(f"categoria: {diagnostic['categoria']}")
        typer.echo(f"fase: {diagnostic['fase']}")
        typer.echo(f"operacao: {summary.operation}")
        for step in recovery:
            typer.echo(f"recuperacao: {step}")
    raise typer.Exit(code=1)


__all__ = ["kb_app"]
