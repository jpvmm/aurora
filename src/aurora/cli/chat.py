"""Aurora chat CLI command — interactive multi-turn conversation with intent routing."""
from __future__ import annotations

import typer

from aurora.chat.history import ChatHistory
from aurora.chat.session import ChatSession

chat_app = typer.Typer(
    no_args_is_help=False,
    help="Inicie uma conversa interativa com Aurora.",
)

EXIT_COMMANDS = {"sair", "exit", "quit"}


@chat_app.callback(invoke_without_command=True)
def chat_command(
    clear: bool = typer.Option(False, "--clear", help="Limpa historico de conversa."),
) -> None:
    """Start an interactive multi-turn chat session with intent routing."""
    if clear:
        history = ChatHistory()
        history.clear()
        typer.echo("Historico de conversa limpo.")
        return

    session = ChatSession()
    typer.echo("Aurora Chat — digite 'sair' para encerrar.")
    typer.echo("")

    try:
        while True:
            try:
                user_input = input("voce> ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in EXIT_COMMANDS:
                typer.echo("Ate logo!")
                break

            typer.echo("")  # blank line before response
            session.process_turn(user_input)
            typer.echo("")  # blank line after response
    except KeyboardInterrupt:
        typer.echo("\nAte logo!")


__all__ = ["chat_app"]
