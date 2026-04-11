"""aurora status — unified dashboard for model, KB, memory, and config state.

Per plan 05-02 (D-05, D-06, D-07, D-11, D-16):
- Report-only: NO network requests, NO auto-start
- Reads lock file via ServerLifecycleService.get_status() (does NOT call check_health)
- Supports --json for structured output
- Graceful degradation when any service raises
"""
from __future__ import annotations

import importlib.metadata
import json
import os

import typer

from aurora.cli.config import mask_sensitive

status_app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Painel de estado atual do Aurora.",
)


@status_app.callback()
def status_command(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False, "--json", help="Renderiza resposta estruturada em JSON."
    ),
) -> None:
    """Mostra um painel unificado do estado atual do Aurora."""
    if ctx.invoked_subcommand is not None:
        return
    _run_status(json_output=json_output)


def _run_status(*, json_output: bool) -> None:
    # ------------------------------------------------------------------
    # 1. Version (importlib.metadata — graceful fallback)
    # ------------------------------------------------------------------
    try:
        version_str = importlib.metadata.version("aurora")
    except Exception:
        version_str = "desconhecido"

    # ------------------------------------------------------------------
    # 2. Config (settings load — fallback to empty values on failure)
    # ------------------------------------------------------------------
    try:
        from aurora.runtime.settings import load_settings

        settings = load_settings()
        vault_path = settings.kb_vault_path or ""
        local_only = bool(settings.local_only)
        telemetry_enabled = bool(settings.telemetry_enabled)
        collection_name = settings.kb_qmd_collection_name
    except Exception:
        settings = None
        vault_path = ""
        local_only = True
        telemetry_enabled = False
        collection_name = ""

    # ------------------------------------------------------------------
    # 3. Model state — lock file only, NO check_health (per D-06)
    # ------------------------------------------------------------------
    model_state: str | None = None
    model_id: str = ""
    endpoint_url: str = ""
    pid: int | None = None
    uptime_seconds: int | None = None
    try:
        from aurora.runtime.server_lifecycle import ServerLifecycleService

        lifecycle_status = ServerLifecycleService().get_status()
        model_state = lifecycle_status.lifecycle_state
        model_id = lifecycle_status.model_id or ""
        endpoint_url = lifecycle_status.endpoint_url or ""
        pid = lifecycle_status.pid
        uptime_seconds = lifecycle_status.uptime_seconds
    except Exception:
        model_state = None
        model_id = ""
        endpoint_url = ""
        pid = None
        uptime_seconds = None

    # ------------------------------------------------------------------
    # 4. KB state — manifest read + mtime for last_update
    # ------------------------------------------------------------------
    note_count = 0
    vault_root: str = vault_path or ""
    last_update: str | None = None
    try:
        from aurora.kb.manifest import load_kb_manifest
        from aurora.runtime.paths import get_kb_manifest_path

        manifest = load_kb_manifest()
        if manifest is not None:
            note_count = len(manifest.notes)
            vault_root = manifest.vault_root or vault_root
            manifest_path = get_kb_manifest_path()
            try:
                mtime = os.path.getmtime(manifest_path)
                from datetime import UTC, datetime

                last_update = (
                    datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
            except Exception:
                last_update = None
        else:
            note_count = 0
            if not vault_root:
                vault_root = "(nao configurado)"
    except Exception:
        note_count = 0
        last_update = None
        if not vault_root:
            vault_root = "(nao configurado)"

    # ------------------------------------------------------------------
    # 5. Memory state
    # ------------------------------------------------------------------
    memory_count = 0
    # Named `last_session_date` — the underlying source key is `date`, which is a
    # human-readable date string (not a session identifier). See REVIEW IN-04.
    last_session_date: str | None = None
    try:
        from aurora.memory.store import EpisodicMemoryStore

        memories = EpisodicMemoryStore().list_memories()
        memory_count = len(memories)
        if memories:
            tail = memories[-1]
            last_session_date = tail.get("date") if isinstance(tail, dict) else None
    except Exception:
        memory_count = 0
        last_session_date = None

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    if json_output:
        payload = {
            "version": version_str,
            "model": {
                "state": model_state or "desconhecido",
                "model_id": model_id,
                "endpoint": endpoint_url,
                "pid": pid,
                "uptime_seconds": uptime_seconds,
            },
            "kb": {
                "collection": collection_name,
                "vault": vault_root,
                "note_count": note_count,
                "last_update": last_update,
            },
            "memory": {
                "memory_count": memory_count,
                "last_session_date": last_session_date,
            },
            "config": {
                "vault_path": vault_path,
                "local_only": local_only,
                "telemetry_enabled": telemetry_enabled,
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # Text dashboard
    typer.echo(f"Aurora v{version_str}")
    typer.echo("")
    typer.echo("Modelo:")
    typer.echo(f"  estado: {model_state or 'desconhecido'}")
    typer.echo(f"  modelo: {model_id or '-'}")
    masked_endpoint = mask_sensitive(endpoint_url) if endpoint_url else "-"
    typer.echo(f"  endpoint: {masked_endpoint}")
    typer.echo(f"  pid: {pid if pid is not None else '-'}")
    typer.echo(
        f"  uptime(s): {uptime_seconds if uptime_seconds is not None else '-'}"
    )
    typer.echo("")
    typer.echo("Base de Conhecimento:")
    typer.echo(f"  collection: {collection_name or '-'}")
    typer.echo(f"  vault: {vault_root or '(nao configurado)'}")
    typer.echo(f"  notas indexadas: {note_count}")
    typer.echo(f"  ultima atualizacao: {last_update or 'nunca'}")
    typer.echo("")
    typer.echo("Memoria:")
    typer.echo(f"  memorias: {memory_count}")
    typer.echo(f"  ultima sessao: {last_session_date or 'nenhuma'}")
    typer.echo("")
    typer.echo("Configuracao:")
    typer.echo(f"  vault: {vault_path or '(nao configurado)'}")
    typer.echo(
        f"  local-only: {'ativado' if local_only else 'desativado'}"
    )
    typer.echo(
        f"  telemetria: {'ativada' if telemetry_enabled else 'desativada'}"
    )


__all__ = ["status_app", "status_command"]
