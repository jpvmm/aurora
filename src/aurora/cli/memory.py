"""Aurora memory CLI commands — manage long-term episodic memory and preferences."""
from __future__ import annotations

import json as json_mod
import os
import subprocess
import sys

import typer

from aurora.memory.store import MEMORY_COLLECTION, EpisodicMemoryStore
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.runtime.paths import get_preferences_path
from aurora.runtime.settings import load_settings

memory_app = typer.Typer(name="memory", help="Gerencia memorias de longo prazo.")


@memory_app.command("list")
def memory_list(
    json: bool = typer.Option(False, "--json", help="Saida em JSON."),
) -> None:
    """Lista todas as memorias episodicas com data e topico."""
    store = EpisodicMemoryStore()
    memories = store.list_memories()

    if json:
        typer.echo(json_mod.dumps(memories, ensure_ascii=False, indent=2))
        return

    if not memories:
        typer.echo("Nenhuma memoria encontrada.")
        return

    for m in memories:
        date = m.get("date", "?")
        topic = m.get("topic", "sem titulo")
        turns = m.get("turn_count", "?")
        typer.echo(f"  {date}  [{turns} turnos]  {topic}")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Busca semantica nas memorias."),
    json: bool = typer.Option(False, "--json", help="Saida em JSON."),
) -> None:
    """Busca semantica nas memorias episodicas via QMD."""
    settings = load_settings()
    backend = QMDSearchBackend(
        collection_name=MEMORY_COLLECTION,
        top_k=settings.memory_top_k,
        min_score=settings.memory_min_score,
    )
    response = backend.search(query)

    if json:
        hits = [
            {"path": h.path, "score": h.score, "title": h.title, "snippet": h.snippet}
            for h in response.hits
        ]
        typer.echo(
            json_mod.dumps({"ok": response.ok, "hits": hits}, ensure_ascii=False, indent=2)
        )
        return

    if not response.ok:
        typer.echo(
            "Falha ao buscar memorias. Verifique se a colecao aurora-memory existe.",
            err=True,
        )
        return

    if not response.hits:
        typer.echo("Nenhuma memoria encontrada para essa busca.")
        return

    for hit in response.hits:
        typer.echo(f"  [{hit.score:.2f}]  {hit.title or hit.path}")
        if hit.snippet:
            typer.echo(f"           {hit.snippet[:120]}")


@memory_app.command("edit")
def memory_edit() -> None:
    """Abre o arquivo de preferencias (Tier 1) no editor padrao."""
    prefs_path = get_preferences_path()
    if not prefs_path.exists():
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text(
            "# Preferencias Aurora\n"
            "# Escreva regras, convencoes e preferencias aqui.\n"
            "# Este conteudo e injetado no prompt do sistema durante aurora chat.\n",
            encoding="utf-8",
        )
        typer.echo(f"Arquivo criado: {prefs_path}")

    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(prefs_path)], check=False)


@memory_app.command("clear")
def memory_clear(
    yes: bool = typer.Option(False, "--yes", help="Confirma limpeza sem prompt interativo."),
    json: bool = typer.Option(False, "--json", help="Saida em JSON."),
) -> None:
    """Remove todas as memorias episodicas. Preferencias e KB nao sao afetados."""
    if not yes:
        confirm = typer.confirm(
            "Remover todas as memorias episodicas? (preferencias e KB nao serao afetados)"
        )
        if not confirm:
            typer.echo("Operacao cancelada.")
            return

    store = EpisodicMemoryStore()
    deleted = store.clear()

    # Remove QMD collection (per Pitfall 6)
    settings = load_settings()
    _remove_qmd_collection(settings.kb_qmd_index_name)

    if json:
        typer.echo(
            json_mod.dumps(
                {"deleted": deleted, "collection_removed": MEMORY_COLLECTION},
                ensure_ascii=False,
            )
        )
        return

    typer.echo(f"Memorias removidas: {deleted} arquivo(s).")
    typer.echo(f"Colecao QMD '{MEMORY_COLLECTION}' removida.")


def _remove_qmd_collection(index_name: str) -> None:
    """Remove the aurora-memory QMD collection. Ignores errors (collection may not exist)."""
    try:
        subprocess.run(
            ("qmd", "--index", index_name, "collection", "remove", MEMORY_COLLECTION),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pass  # qmd not installed — nothing to remove


__all__ = ["memory_app"]
