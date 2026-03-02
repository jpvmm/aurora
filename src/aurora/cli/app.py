"""Root CLI app for Aurora."""

import typer


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Aurora CLI local.",
)


@app.callback()
def root() -> None:
    """Aurora root command."""


def _placeholder(group_name: str) -> None:
    typer.echo(
        f"O grupo '{group_name}' ainda não implementado nesta fase.",
        err=True,
    )
    raise typer.Exit(code=1)


setup_app = typer.Typer(invoke_without_command=True, no_args_is_help=False)
config_app = typer.Typer(invoke_without_command=True, no_args_is_help=False)
model_app = typer.Typer(invoke_without_command=True, no_args_is_help=False)
doctor_app = typer.Typer(invoke_without_command=True, no_args_is_help=False)


@setup_app.callback()
def setup_placeholder() -> None:
    _placeholder("setup")


@config_app.callback()
def config_placeholder() -> None:
    _placeholder("config")


@model_app.callback()
def model_placeholder() -> None:
    _placeholder("model")


@doctor_app.callback()
def doctor_placeholder() -> None:
    _placeholder("doctor")


app.add_typer(setup_app, name="setup")
app.add_typer(config_app, name="config")
app.add_typer(model_app, name="model")
app.add_typer(doctor_app, name="doctor")
