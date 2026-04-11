"""Deprecation alias Typer apps for legacy top-level commands.

Each alias emits a pt-BR warning to stderr and then delegates to the same command
functions used by the canonical `aurora config <namespace>` surface. This keeps old
invocations working (`aurora kb ...`, `aurora model ...`, `aurora memory ...`) while
guiding the user toward the new layout.

Per Pitfall 1: these typers do NOT set `invoke_without_command=True` so Typer's help
machinery keeps working at the parent level (e.g. `aurora kb --help`) without firing
the callback for help-only invocations.
"""
from __future__ import annotations

import typer

from aurora.cli.kb import (
    kb_config_app,
    kb_delete_command,
    kb_ingest_command,
    kb_rebuild_command,
    kb_scheduler_app,
    kb_update_command,
)
from aurora.cli.memory import (
    memory_clear,
    memory_edit,
    memory_list,
    memory_search,
)
from aurora.cli.model import (
    model_health_command,
    model_set_command,
    model_start_command,
    model_status_command,
    model_stop_command,
)


# ---------------------------------------------------------------------------
# Deprecated: aurora kb -> aurora config kb
# ---------------------------------------------------------------------------
deprecated_kb_app = typer.Typer(
    no_args_is_help=True,
    help="[DEPRECADO] Use `aurora config kb`.",
)


@deprecated_kb_app.callback()
def _deprecated_kb_callback() -> None:
    typer.echo(
        "Aviso: `aurora kb` foi movido. Use `aurora config kb ...`.",
        err=True,
    )


deprecated_kb_app.command("ingest")(kb_ingest_command)
deprecated_kb_app.command("update")(kb_update_command)
deprecated_kb_app.command("delete")(kb_delete_command)
deprecated_kb_app.command("rebuild")(kb_rebuild_command)
deprecated_kb_app.add_typer(kb_config_app, name="config")
deprecated_kb_app.add_typer(kb_scheduler_app, name="scheduler")


# ---------------------------------------------------------------------------
# Deprecated: aurora model -> aurora config model
# ---------------------------------------------------------------------------
deprecated_model_app = typer.Typer(
    no_args_is_help=True,
    help="[DEPRECADO] Use `aurora config model`.",
)


@deprecated_model_app.callback()
def _deprecated_model_callback() -> None:
    typer.echo(
        "Aviso: `aurora model` foi movido. Use `aurora config model ...`.",
        err=True,
    )


deprecated_model_app.command("set")(model_set_command)
deprecated_model_app.command("start")(model_start_command)
deprecated_model_app.command("stop")(model_stop_command)
deprecated_model_app.command("status")(model_status_command)
deprecated_model_app.command("health")(model_health_command)


# ---------------------------------------------------------------------------
# Deprecated: aurora memory -> aurora config memory
# ---------------------------------------------------------------------------
deprecated_memory_app = typer.Typer(
    no_args_is_help=True,
    help="[DEPRECADO] Use `aurora config memory`.",
)


@deprecated_memory_app.callback()
def _deprecated_memory_callback() -> None:
    typer.echo(
        "Aviso: `aurora memory` foi movido. Use `aurora config memory ...`.",
        err=True,
    )


deprecated_memory_app.command("list")(memory_list)
deprecated_memory_app.command("search")(memory_search)
deprecated_memory_app.command("edit")(memory_edit)
deprecated_memory_app.command("clear")(memory_clear)


__all__ = [
    "deprecated_kb_app",
    "deprecated_memory_app",
    "deprecated_model_app",
]
