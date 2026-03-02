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
