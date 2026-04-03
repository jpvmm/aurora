"""aurora ask — single-shot grounded Q&A command."""
from __future__ import annotations

import json
import logging
from typing import Callable

import typer

from aurora.llm.prompts import INSUFFICIENT_EVIDENCE_MSG
from aurora.llm.service import LLMService
from aurora.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)

ask_app = typer.Typer(
    help="Pergunte ao vault e receba respostas fundamentadas.",
    context_settings={"allow_interspersed_args": True},
)


@ask_app.callback(invoke_without_command=True)
def ask_command(
    query: str = typer.Argument(..., help="Pergunta para buscar no vault."),
    json_output: bool = typer.Option(False, "--json", help="Renderiza resposta em JSON."),
) -> None:
    """Busca evidencias no vault e gera uma resposta fundamentada."""
    retrieval = RetrievalService()
    result = retrieval.retrieve(query)

    logger.debug(
        "Retrieval: %d hits, paths+scores=%s",
        len(result.notes),
        [(n.path, n.score) for n in result.notes],
    )

    if result.insufficient_evidence:
        if json_output:
            print(
                json.dumps(
                    {
                        "query": query,
                        "answer": "",
                        "sources": [],
                        "insufficient_evidence": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            typer.echo(INSUFFICIENT_EVIDENCE_MSG)
        return

    llm = LLMService()

    if json_output:
        # Collect tokens silently in JSON mode
        collected: list[str] = []

        def _collect_token(token: str) -> None:
            collected.append(token)

        on_token: Callable[[str], None] = _collect_token
    else:
        def _print_token(token: str) -> None:
            print(token, end="", flush=True)

        on_token = _print_token

    response = llm.ask_grounded(query, result.context_text, on_token=on_token)

    if json_output:
        sources = list(dict.fromkeys(n.path for n in result.notes))
        print(
            json.dumps(
                {
                    "query": query,
                    "answer": response,
                    "sources": sources,
                    "insufficient_evidence": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print()  # Final newline after streamed tokens


__all__ = ["ask_app"]
