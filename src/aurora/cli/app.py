"""Root CLI app for Aurora."""

import typer

from aurora.cli.model import model_app
from aurora.cli.setup import run_first_run_wizard, setup_app, should_run_first_run_wizard

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
    help="Aurora CLI local.",
)


@app.callback()
def root(ctx: typer.Context) -> None:
    """Aurora root command."""
    if ctx.invoked_subcommand is not None:
        return
    if should_run_first_run_wizard():
        run_first_run_wizard()


def _placeholder(group_name: str) -> None:
    typer.echo(
        f"O grupo '{group_name}' ainda não implementado nesta fase.",
        err=True,
    )
    raise typer.Exit(code=1)


config_app = typer.Typer(invoke_without_command=True, no_args_is_help=False)
doctor_app = typer.Typer(invoke_without_command=True, no_args_is_help=False)


@config_app.callback()
def config_placeholder() -> None:
    _placeholder("config")


@doctor_app.callback()
def doctor_placeholder() -> None:
    _placeholder("doctor")


app.add_typer(setup_app, name="setup")
app.add_typer(config_app, name="config")
app.add_typer(model_app, name="model")
app.add_typer(doctor_app, name="doctor")
