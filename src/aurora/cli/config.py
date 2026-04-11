from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import typer

from aurora.runtime.settings import load_settings, telemetry_defaults_env


SENSITIVE_QUERY_KEYS = {"token", "api_key", "apikey", "key", "access_token"}
HF_TOKEN_PATTERN = re.compile(r"hf_[A-Za-z0-9]+")

config_app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Inspecao da configuracao global.",
)


@config_app.callback()
def config_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    typer.echo("Use `aurora config show` ou `aurora config --help` para ver opcoes disponiveis.")
    raise typer.Exit(code=1)


@config_app.command("show")
def config_show_command() -> None:
    settings = load_settings()
    telemetry_defaults = telemetry_defaults_env()

    typer.echo("Configuracao atual do Aurora")
    typer.echo("")
    typer.echo("Runtime:")
    typer.echo(f"- endpoint: {mask_sensitive(settings.endpoint_url)}")
    typer.echo(f"- model: {settings.model_id}")
    typer.echo(f"- source: {mask_sensitive(settings.model_source)}")
    typer.echo("")
    typer.echo("KB:")
    typer.echo(f"- vault: {settings.kb_vault_path or '(nao configurado)'}")
    typer.echo(f"- index: {settings.kb_qmd_index_name}")
    typer.echo(f"- collection: {settings.kb_qmd_collection_name}")
    typer.echo(
        "- auto-embeddings: "
        f"{'ativado' if settings.kb_auto_embeddings_enabled else 'desativado'}"
    )
    typer.echo("")
    typer.echo("Privacidade:")
    typer.echo(f"- local-only: {'ativado' if settings.local_only else 'desativado'}")
    typer.echo(f"- telemetria: {'ativada' if settings.telemetry_enabled else 'desativada'}")
    typer.echo(f"- AGNO_TELEMETRY: {telemetry_defaults['AGNO_TELEMETRY']}")
    typer.echo(
        f"- GRAPHITI_TELEMETRY_ENABLED: {telemetry_defaults['GRAPHITI_TELEMETRY_ENABLED']}"
    )


def mask_sensitive(value: str) -> str:
    masked = HF_TOKEN_PATTERN.sub("hf_***", value)
    parts = urlsplit(masked)

    if not parts.scheme or not parts.netloc:
        return masked

    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"

    userinfo = ""
    if parts.username:
        userinfo = f"{parts.username}:***@"

    query_parts = []
    for key, query_value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            query_parts.append((key, "***"))
        else:
            query_parts.append((key, query_value))
    # Re-encode via ``urlencode`` so percent-encoded values (``%20``, ``%3D``,
    # ...) survive the round-trip instead of being rewritten verbatim.
    query = urlencode(query_parts, doseq=True)

    return urlunsplit((parts.scheme, f"{userinfo}{host}", parts.path, query, parts.fragment))


# Namespace sub-typers — move kb/model/memory/setup under `aurora config` (per D-02, D-03, D-13).
# Deferred to the bottom of the module so `mask_sensitive` (and the top-level
# `config_app`) remain importable from `aurora.cli.doctor` and `aurora.cli.status`
# before the sub-typers — which themselves import from `aurora.cli.config` via
# the shared command helpers — are wired up.
from aurora.cli.kb import kb_app  # noqa: E402
from aurora.cli.memory import memory_app  # noqa: E402
from aurora.cli.model import model_app  # noqa: E402
from aurora.cli.setup import setup_app  # noqa: E402

config_app.add_typer(kb_app, name="kb")
config_app.add_typer(model_app, name="model")
config_app.add_typer(memory_app, name="memory")
config_app.add_typer(setup_app, name="setup")


__all__ = ["config_app", "config_show_command", "mask_sensitive"]
