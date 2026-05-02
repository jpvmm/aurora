"""Aurora chat CLI command — interactive multi-turn conversation with intent routing."""
from __future__ import annotations

import logging
import threading

import typer

from aurora.chat.history import ChatHistory
from aurora.chat.session import ChatSession
from aurora.llm.service import LLMService
from aurora.memory.store import EpisodicMemoryStore, MEMORY_COLLECTION, MEMORY_INDEX
from aurora.memory.summarizer import MemorySummarizer
from aurora.retrieval.contracts import IterativeRetrievalTrace
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.retrieval.trace_render import render_trace_text

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
    trace: bool = typer.Option(
        False,
        "--trace",
        help="Mostra trace por turno apos a resposta.",
    ),
) -> None:
    """Start an interactive multi-turn chat session with intent routing."""
    if clear:
        history = ChatHistory()
        history.clear()
        typer.echo("Historico de conversa limpo.")
        return

    def _status(msg: str) -> None:
        typer.echo(msg, err=True)

    memory_backend = QMDSearchBackend(
        index_name=MEMORY_INDEX,
        collection_name=MEMORY_COLLECTION,
    )

    # --trace wiring (D-09): per-turn trace consumer captures the orchestrator's
    # IterativeRetrievalTrace so we can render it to stderr after each response.
    captured: dict[str, IterativeRetrievalTrace | None] = {"trace": None}

    def _consume_trace(t: IterativeRetrievalTrace) -> None:
        captured["trace"] = t

    session = ChatSession(
        on_status=_status,
        memory_backend=memory_backend,
        last_trace_consumer=_consume_trace if trace else None,
    )
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

            if trace and captured["trace"] is not None:
                typer.echo(render_trace_text(captured["trace"]), err=True)
                captured["trace"] = None  # reset for next turn
    except KeyboardInterrupt:
        typer.echo("\nAte logo!")

    # Memory save on exit (per D-08, D-12)
    if session.turn_count >= 2:  # D-11: min 2 turns
        typer.echo("Salvando memoria...", err=True)
        store = EpisodicMemoryStore()
        t = threading.Thread(
            target=_background_save,
            args=(session.get_session_turns(), session.llm, store, session.turn_count),
        )
        t.start()
        t.join(timeout=30)  # wait up to 30s for summary to complete
        if t.is_alive():
            typer.echo("Memoria sendo salva em background...", err=True)


__all__ = ["chat_app"]
