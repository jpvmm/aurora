"""Aurora chat CLI command — interactive multi-turn conversation with intent routing."""
from __future__ import annotations

import logging
import threading

import typer

from aurora.chat.history import ChatHistory
from aurora.chat.session import ChatSession
from aurora.llm.service import LLMService
from aurora.memory.store import EpisodicMemoryStore
from aurora.memory.summarizer import MemorySummarizer

chat_app = typer.Typer(
    no_args_is_help=False,
    help="Inicie uma conversa interativa com Aurora.",
)

EXIT_COMMANDS = {"sair", "exit", "quit"}

logger = logging.getLogger(__name__)


def _background_save(
    session_turns: list[dict[str, str]],
    llm: LLMService,
    store: EpisodicMemoryStore,
    turn_count: int,
) -> None:
    """Run in daemon thread. Failures are silently logged, never raised (per D-23)."""
    try:
        summarizer = MemorySummarizer(llm=llm, store=store)
        summarizer.summarize_and_save(history_turns=session_turns, turn_count=turn_count)
    except Exception:
        logger.warning("Falha ao salvar memoria em background", exc_info=True)


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

    # Background memory save — after farewell, before returning to user (per D-08, D-12)
    if session.turn_count >= 2:  # D-11: min 2 turns
        store = EpisodicMemoryStore()
        t = threading.Thread(
            target=_background_save,
            args=(session.get_session_turns(), session.llm, store, session.turn_count),
            daemon=True,  # D-12: user exits immediately, do NOT join
        )
        t.start()


__all__ = ["chat_app"]
