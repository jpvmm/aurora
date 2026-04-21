from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import typer

from aurora.kb.contracts import KBFileDiagnostic, KBOperationCounters, KBOperationSummary
from aurora.kb.manifest import (
    KBManifestNoteRecord,
    KBManifestStateError,
    load_kb_manifest,
)
from aurora.kb.scheduler import KBSchedulerStatus, KBSchedulerService
from aurora.kb.service import KBService, KBServiceError
from aurora.runtime.settings import load_settings, save_settings


kb_app = typer.Typer(
    no_args_is_help=True,
    help="Comandos de ciclo de vida da base de conhecimento do vault.",
)

kb_config_app = typer.Typer(
    no_args_is_help=True,
    help="Inspecao e ajuste da configuracao operacional do KB.",
)

kb_scheduler_app = typer.Typer(
    no_args_is_help=True,
    help="Controle de execucao agendada para atualizacoes KB.",
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
    service = KBService()
    progress = None if json_output else _render_progress
    try:
        summary = service.run_ingest(
            vault_path=vault_path,
            dry_run=dry_run,
            on_progress=progress,
        )
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_summary(summary=summary, json_output=json_output)
    _raise_for_partial_embedding(summary)


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
    verify_hash: bool = typer.Option(
        False,
        "--verify-hash",
        help="Usa hash para refinar deteccao de alteracoes em notas.",
    ),
    index: str | None = typer.Option(
        None,
        "--index",
        help="Sobrescreve indice ativo apenas nesta execucao.",
    ),
    collection: str | None = typer.Option(
        None,
        "--collection",
        help="Sobrescreve collection ativa apenas nesta execucao.",
    ),
) -> None:
    service = _build_service(index_name=index, collection_name=collection)
    progress = None if json_output else _render_progress
    try:
        summary = service.run_update(
            dry_run=dry_run,
            verify_hash=verify_hash,
            on_progress=progress,
        )
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_summary(summary=summary, json_output=json_output)
    _raise_for_partial_embedding(summary)


@kb_app.command("delete")
def kb_delete_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Confirma exclusao destrutiva sem prompt interativo.",
    ),
    index: str | None = typer.Option(
        None,
        "--index",
        help="Sobrescreve indice ativo apenas nesta execucao.",
    ),
    collection: str | None = typer.Option(
        None,
        "--collection",
        help="Sobrescreve collection ativa apenas nesta execucao.",
    ),
) -> None:
    if not yes and not _confirm_delete(json_output=json_output):
        raise typer.Exit(code=1)

    service = _build_service(index_name=index, collection_name=collection)
    progress = None if json_output else _render_progress
    try:
        summary = service.run_delete(on_progress=progress)
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_summary(summary=summary, json_output=json_output, index_only=True)
    _raise_for_partial_embedding(summary)


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
    index: str | None = typer.Option(
        None,
        "--index",
        help="Sobrescreve indice ativo apenas nesta execucao.",
    ),
    collection: str | None = typer.Option(
        None,
        "--collection",
        help="Sobrescreve collection ativa apenas nesta execucao.",
    ),
) -> None:
    service = _build_service(index_name=index, collection_name=collection)
    progress = None if json_output else _render_progress
    try:
        summary = service.run_rebuild(dry_run=dry_run, on_progress=progress)
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_summary(summary=summary, json_output=json_output)
    _raise_for_partial_embedding(summary)


@kb_app.command("recent")
def kb_recent_command(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        help="Maximo de notas a exibir (padrao: 10).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    try:
        manifest = load_kb_manifest()
    except KBManifestStateError as error:
        _render_manifest_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    if manifest is None:
        _render_recent_empty(json_output=json_output)
        return

    sorted_notes = sorted(
        manifest.notes.items(),
        key=lambda item: (item[1].indexed_at, item[0]),
        reverse=True,
    )
    _render_recent(
        vault_root=manifest.vault_root,
        total=len(manifest.notes),
        notes=sorted_notes[:limit],
        json_output=json_output,
    )


@kb_config_app.command("show")
def kb_config_show_command() -> None:
    settings = load_settings()
    typer.echo("Configuracao KB atual")
    typer.echo(f"vault: {settings.kb_vault_path or '(nao configurado)'}")
    typer.echo(f"include: {list(settings.kb_include)}")
    typer.echo(f"exclude: {list(settings.kb_exclude)}")
    typer.echo(f"index: {settings.kb_qmd_index_name}")
    typer.echo(f"collection: {settings.kb_qmd_collection_name}")
    typer.echo(
        f"auto-embeddings: {'ativado' if settings.kb_auto_embeddings_enabled else 'desativado'}"
    )


@kb_config_app.command("set")
def kb_config_set_command(
    vault: str | None = typer.Option(
        None,
        "--vault",
        help="Define caminho absoluto do vault padrao para KB.",
    ),
    include: list[str] | None = typer.Option(
        None,
        "--include",
        help="Padrao de include (repita a opcao para varios valores).",
    ),
    exclude: list[str] | None = typer.Option(
        None,
        "--exclude",
        help="Padrao de exclude (repita a opcao para varios valores).",
    ),
    index: str | None = typer.Option(
        None,
        "--index",
        help="Nome do indice QMD ativo.",
    ),
    collection: str | None = typer.Option(
        None,
        "--collection",
        help="Nome da collection QMD ativa.",
    ),
    auto_embeddings: bool | None = typer.Option(
        None,
        "--auto-embeddings/--no-auto-embeddings",
        help="Ativa/desativa embeddings automáticos apos mutacoes KB.",
    ),
) -> None:
    if all(
        option is None
        for option in (vault, include, exclude, index, collection, auto_embeddings)
    ):
        typer.echo(
            "Nenhuma alteracao informada. Use ao menos um parametro "
            "(--vault/--include/--exclude/--index/--collection/--auto-embeddings)."
        )
        raise typer.Exit(code=1)

    settings = load_settings()
    update_payload: dict[str, object] = {}
    if vault is not None:
        update_payload["kb_vault_path"] = vault.strip()
    if include is not None:
        update_payload["kb_include"] = tuple(include)
    if exclude is not None:
        update_payload["kb_exclude"] = tuple(exclude)
    if index is not None:
        update_payload["kb_qmd_index_name"] = index
    if collection is not None:
        update_payload["kb_qmd_collection_name"] = collection
    if auto_embeddings is not None:
        update_payload["kb_auto_embeddings_enabled"] = auto_embeddings

    updated = save_settings(settings.model_copy(update=update_payload))
    typer.echo("Configuracao KB atualizada.")
    typer.echo(f"index ativo: {updated.kb_qmd_index_name}")
    typer.echo(f"collection ativa: {updated.kb_qmd_collection_name}")
    typer.echo(
        f"auto-embeddings: {'ativado' if updated.kb_auto_embeddings_enabled else 'desativado'}"
    )


@kb_scheduler_app.command("enable")
def kb_scheduler_enable_command(
    hour: int | None = typer.Option(
        None,
        "--hour",
        min=0,
        max=23,
        help="Hora local (0-23) para execucao diaria.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    service = KBSchedulerService()
    try:
        status = service.enable(hour_local=hour)
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_scheduler_status(status=status, json_output=json_output)


@kb_scheduler_app.command("disable")
def kb_scheduler_disable_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    service = KBSchedulerService()
    try:
        status = service.disable()
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_scheduler_status(status=status, json_output=json_output)


@kb_scheduler_app.command("status")
def kb_scheduler_status_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Renderiza resposta estruturada em JSON.",
    ),
) -> None:
    service = KBSchedulerService()
    try:
        status = service.status()
    except KBServiceError as error:
        _render_service_error(error=error, json_output=json_output)
        raise typer.Exit(code=1) from error

    _render_scheduler_status(status=status, json_output=json_output)


def _render_progress(stage: str, counters: KBOperationCounters) -> None:
    typer.echo(
        "etapa: "
        f"{stage} "
        f"read={counters.read} "
        f"indexed={counters.indexed} "
        f"updated={counters.updated} "
        f"removed={counters.removed} "
        f"skipped={counters.skipped} "
        f"errors={counters.errors}"
    )


def _render_summary(
    *,
    summary: KBOperationSummary,
    json_output: bool,
    index_only: bool = False,
) -> None:
    if json_output:
        typer.echo(summary.to_json())
        return

    typer.echo(f"operacao: {summary.operation}")
    typer.echo(f"dry-run: {'sim' if summary.dry_run else 'nao'}")
    if index_only:
        typer.echo("modo: index-only")
    typer.echo(f"duracao_s: {summary.duration_seconds:.3f}")
    typer.echo(f"vault: {summary.scope.vault_root}")
    typer.echo(
        "effective_scope: "
        f"include={list(summary.scope.include)} "
        f"exclude={list(summary.scope.exclude)}"
    )
    typer.echo(
        "totais: "
        f"read={summary.counters.read} "
        f"indexed={summary.counters.indexed} "
        f"updated={summary.counters.updated} "
        f"removed={summary.counters.removed} "
        f"skipped={summary.counters.skipped} "
        f"errors={summary.counters.errors}"
    )
    _render_embedding_status(summary=summary)
    _render_diagnostics(summary.diagnostics)


def _render_diagnostics(diagnostics: tuple[KBFileDiagnostic, ...]) -> None:
    for diagnostic in diagnostics:
        typer.echo(
            "diagnostico: "
            f"path={diagnostic.path} "
            f"category={diagnostic.category} "
            f"recovery_hint={diagnostic.recovery_hint}"
        )


def _render_embedding_status(*, summary: KBOperationSummary) -> None:
    if summary.embedding is None:
        return
    if not summary.embedding.attempted:
        typer.echo("embedding: nao executado")
        return
    if summary.embedding.ok:
        typer.echo("embedding: atualizado")
        return

    typer.echo("warning: embeddings desatualizados (falha parcial)")
    if summary.embedding.category:
        typer.echo(f"embedding_category: {summary.embedding.category}")
    if summary.embedding.recovery_command:
        typer.echo(f"recuperacao: {summary.embedding.recovery_command}")


def _render_scheduler_status(*, status: KBSchedulerStatus, json_output: bool) -> None:
    payload = {
        "enabled": status.enabled,
        "local_hour": status.local_hour,
        "timezone": status.timezone_name,
        "next_due_at": _format_optional_datetime(status.next_due_at),
        "catch_up_eligible": status.catch_up_eligible,
        "last_planned_slot_at": _format_optional_datetime(status.last_planned_slot_at),
        "last_run_started_at": _format_optional_datetime(status.last_run_started_at),
        "last_run_completed_at": _format_optional_datetime(status.last_run_completed_at),
        "last_run_ok": status.last_run_ok,
        "last_run_reason": status.last_run_reason,
        "last_error_category": status.last_error_category,
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    typer.echo(f"scheduler: {'ativado' if status.enabled else 'desativado'}")
    typer.echo(f"hora_local: {status.local_hour}")
    typer.echo(f"timezone: {status.timezone_name}")
    typer.echo(f"proxima_execucao: {payload['next_due_at'] or 'nenhuma'}")
    typer.echo(f"catch_up_elegivel: {'sim' if status.catch_up_eligible else 'nao'}")
    typer.echo(f"ultimo_slot_planejado: {payload['last_planned_slot_at'] or 'nenhum'}")
    typer.echo(f"ultima_execucao_inicio: {payload['last_run_started_at'] or 'nenhuma'}")
    typer.echo(f"ultima_execucao_fim: {payload['last_run_completed_at'] or 'nenhuma'}")
    typer.echo(
        "ultimo_resultado: "
        f"{'sucesso' if status.last_run_ok is True else 'falha' if status.last_run_ok is False else 'nao executado'}"
    )
    if status.last_run_reason:
        typer.echo(f"ultimo_motivo: {status.last_run_reason}")
    if status.last_error_category:
        typer.echo(f"ultimo_erro: {status.last_error_category}")


def _render_recent(
    *,
    vault_root: str,
    total: int,
    notes: list[tuple[str, KBManifestNoteRecord]],
    json_output: bool,
) -> None:
    if json_output:
        payload = {
            "vault_root": vault_root,
            "total": total,
            "count": len(notes),
            "notes": [
                {
                    "path": path,
                    "indexed_at": record.indexed_at,
                    "size": record.size,
                    "cleaned_size": record.cleaned_size,
                    "mtime_ns": record.mtime_ns,
                    "sha256": record.sha256,
                    "templater_tags_removed": record.templater_tags_removed,
                }
                for path, record in notes
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    typer.echo(f"vault: {vault_root}")
    typer.echo(f"notas recentes: {len(notes)} de {total}")
    if not notes:
        typer.echo("(sem notas indexadas)")
        return
    for path, record in notes:
        typer.echo(f"  {record.indexed_at}  {path}")


def _render_recent_empty(*, json_output: bool) -> None:
    if json_output:
        payload = {
            "vault_root": None,
            "total": 0,
            "count": 0,
            "notes": [],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    typer.echo("Nenhum manifesto KB encontrado.")
    typer.echo("recuperacao: aurora config kb ingest <vault>")


def _render_manifest_error(
    *, error: KBManifestStateError, json_output: bool
) -> None:
    if json_output:
        payload = {
            "ok": False,
            "message": error.message,
            "recovery_commands": list(error.recovery_commands),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    typer.echo(f"erro: {error.message}")
    for command in error.recovery_commands:
        typer.echo(f"recuperacao: {command}")


def _format_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=UTC)
    else:
        normalized = value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _raise_for_partial_embedding(summary: KBOperationSummary) -> None:
    if summary.embedding is None:
        return
    if summary.embedding.attempted and not summary.embedding.ok:
        raise typer.Exit(code=2)


def _render_service_error(*, error: KBServiceError, json_output: bool) -> None:
    if json_output:
        payload = {
            "ok": False,
            "category": error.category,
            "message": error.message,
            "diagnostics": [
                {
                    "path": item.path,
                    "category": item.category,
                    "recovery_hint": item.recovery_hint,
                }
                for item in error.diagnostics
            ],
            "recovery_commands": list(error.recovery_commands),
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    typer.echo(f"erro: {error.message}")
    typer.echo(f"categoria: {error.category}")
    _render_diagnostics(error.diagnostics)
    for command in error.recovery_commands:
        typer.echo(f"recuperacao: {command}")


def _build_service(*, index_name: str | None, collection_name: str | None) -> KBService:
    if index_name is None and collection_name is None:
        return KBService()
    return KBService(index_name=index_name, collection_name=collection_name)


def _confirm_delete(*, json_output: bool) -> bool:
    if _is_interactive_terminal():
        return typer.confirm(
            "Excluir dados da collection ativa do KB? Esta acao e destrutiva.",
            default=False,
        )

    message = (
        "Delete exige confirmacao explicita em modo nao interativo. "
        "Use `aurora kb delete --yes`."
    )
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "category": "confirmation_required",
                    "message": message,
                    "recovery_commands": ["aurora kb delete --yes"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return False

    typer.echo(f"erro: {message}")
    typer.echo("recuperacao: aurora kb delete --yes")
    return False


def _is_interactive_terminal() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


kb_app.add_typer(kb_config_app, name="config")
kb_app.add_typer(kb_scheduler_app, name="scheduler")


__all__ = ["kb_app"]
