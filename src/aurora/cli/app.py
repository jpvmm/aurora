"""Root CLI app for Aurora."""

import typer

from aurora.cli.ask import ask_app
from aurora.cli.chat import chat_app
from aurora.cli.config import config_app
from aurora.cli.doctor import doctor_app
from aurora.cli.kb import kb_app
from aurora.cli.memory import memory_app
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
        return
    typer.echo(ctx.get_help())


app.add_typer(setup_app, name="setup")
app.add_typer(config_app, name="config")
app.add_typer(model_app, name="model")
app.add_typer(doctor_app, name="doctor")
app.add_typer(kb_app, name="kb")
app.add_typer(ask_app, name="ask")
app.add_typer(chat_app, name="chat")
app.add_typer(memory_app, name="memory")
