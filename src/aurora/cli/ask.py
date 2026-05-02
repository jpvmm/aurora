"""aurora ask — single-shot grounded Q&A command."""
from __future__ import annotations

import json
import logging
from typing import Callable

import typer

from aurora.llm.prompts import INSUFFICIENT_EVIDENCE_MSG
from aurora.llm.service import LLMService
from aurora.memory.store import MEMORY_COLLECTION, MEMORY_INDEX
from aurora.retrieval.iterative import IterativeRetrievalOrchestrator
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.retrieval.service import RetrievalService
from aurora.retrieval.trace_render import render_trace_json, render_trace_text

logger = logging.getLogger(__name__)

ask_app = typer.Typer(
    help="Pergunte ao vault e receba respostas fundamentadas.",
    context_settings={"allow_interspersed_args": True},
)


@ask_app.callback(invoke_without_command=True)
def ask_command(
    words: list[str] = typer.Argument(None, help="Pergunta para buscar no vault."),
    json_output: bool = typer.Option(False, "--json", help="Renderiza resposta em JSON."),
    trace: bool = typer.Option(
        False,
        "--trace",
        help="Mostra trace por tentativa de retrieval.",
    ),
) -> None:
    """Busca evidencias no vault e memorias e gera uma resposta fundamentada."""
    if not words:
        typer.echo("Uso: aurora ask <pergunta>", err=True)
        raise typer.Exit(code=1)
    query = " ".join(words)

    llm = LLMService()

    if not json_output:
        typer.echo("Analisando pergunta...", err=True)

    intent_result = llm.classify_intent(query)

    if not json_output:
        typer.echo("Buscando no vault e memorias...", err=True)

    memory_backend = QMDSearchBackend(
        index_name=MEMORY_INDEX,
        collection_name=MEMORY_COLLECTION,
    )
    retrieval = RetrievalService(memory_backend=memory_backend)

    # Iterative retrieval loop (D-04, D-09): the orchestrator drives attempt 1
    # itself (no carry-forward in `aurora ask`) and emits "Revisando busca..." to
    # stderr only when not in JSON mode (D-02).
    def _status(msg: str) -> None:
        if not json_output:
            typer.echo(msg, err=True)

    orchestrator = IterativeRetrievalOrchestrator(llm=llm, on_status=_status)

    intent_for_loop = "memory" if intent_result.intent == "memory" else "vault"

    def _retrieve_for_loop(q, *, search_strategy, search_terms):
        return retrieval.retrieve_with_memory(
            q, search_strategy=search_strategy, search_terms=search_terms,
        )

    result, captured_trace = orchestrator.run(
        query,
        intent=intent_for_loop,
        retrieve_fn=_retrieve_for_loop,
        search_strategy=intent_result.search,
        search_terms=intent_result.terms,
        first_attempt=None,
    )

    logger.debug(
        "Retrieval: %d hits, paths+scores=%s",
        len(result.notes),
        [(n.path, n.score) for n in result.notes],
    )

    if not json_output and not result.insufficient_evidence:
        vault_count = sum(1 for n in result.notes if n.source == "vault")
        memory_count = sum(1 for n in result.notes if n.source == "memory")
        if memory_count > 0:
            typer.echo(
                f"Encontrei {vault_count} nota(s) e {memory_count} memoria(s). Gerando resposta...",
                err=True,
            )
        else:
            typer.echo(
                f"Encontrei {len(result.notes)} nota(s) relevante(s). Gerando resposta...",
                err=True,
            )

    if result.insufficient_evidence:
        if json_output:
            payload: dict[str, object] = {
                "query": query,
                "answer": "",
                "sources": [],
                "insufficient_evidence": True,
            }
            if trace:
                # Symmetry: --trace must surface the trace on the insufficient path
                # too (NIT 2 — pinned by test_trace_emitted_on_insufficient_evidence_path_json_mode).
                payload["trace"] = render_trace_json(captured_trace)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            typer.echo(INSUFFICIENT_EVIDENCE_MSG)
            if trace:
                # Symmetry with happy path: --trace renders to stderr regardless
                # of which branch fired (pinned by test_trace_emitted_on_insufficient_evidence_path_text_mode).
                typer.echo(render_trace_text(captured_trace), err=True)
        return

    if json_output:
        collected: list[str] = []

        def _collect_token(token: str) -> None:
            collected.append(token)

        on_token: Callable[[str], None] = _collect_token
    else:
        def _print_token(token: str) -> None:
            print(token, end="", flush=True)

        on_token = _print_token

    has_memory = any(n.source == "memory" for n in result.notes)
    if has_memory:
        from aurora.llm.prompts import get_system_prompt_grounded_with_memory
        system_prompt = get_system_prompt_grounded_with_memory()
        context_msg = f"Contexto do vault e memorias:\n\n{result.context_text}\n\nPergunta: {query}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg},
        ]
        response = llm.chat_turn(messages, on_token=on_token)
    else:
        response = llm.ask_grounded(query, result.context_text, on_token=on_token)

    if json_output:
        sources = list(dict.fromkeys(n.path for n in result.notes))
        payload = {
            "query": query,
            "answer": response,
            "sources": sources,
            "insufficient_evidence": False,
        }
        if trace:
            payload["trace"] = render_trace_json(captured_trace)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print()  # Final newline after streamed tokens
        if trace:
            typer.echo(render_trace_text(captured_trace), err=True)


__all__ = ["ask_app"]
