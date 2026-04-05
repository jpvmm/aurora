"""QMDSearchBackend — shell-out transport for qmd query and qmd get commands."""
from __future__ import annotations

import json
import subprocess
from typing import Callable, Protocol

from aurora.retrieval.contracts import QMDSearchDiagnostic, QMDSearchHit, QMDSearchResponse
from aurora.runtime.settings import RuntimeSettings, load_settings


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str | None


CommandRunner = Callable[[tuple[str, ...]], CommandResult]
SettingsLoader = Callable[[], RuntimeSettings]


def _default_command_runner(argv: tuple[str, ...]) -> CommandResult:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def _resolve_identifier(value: str | None, *, fallback: str) -> str:
    if value is None:
        return fallback
    normalized = value.strip()
    if not normalized:
        raise ValueError("Identificador QMD nao pode ser vazio.")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("Identificador QMD nao pode conter separadores de caminho.")
    return normalized


class QMDSearchBackend:
    """Concrete QMD CLI transport for search (query) and document fetch (get) operations."""

    def __init__(
        self,
        *,
        index_name: str | None = None,
        collection_name: str | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
        command_runner: CommandRunner | None = None,
        settings_loader: SettingsLoader = load_settings,
    ) -> None:
        settings = settings_loader()
        self.index_name = _resolve_identifier(
            index_name, fallback=settings.kb_qmd_index_name
        )
        self.collection_name = _resolve_identifier(
            collection_name, fallback=settings.kb_qmd_collection_name
        )
        self.top_k = top_k if top_k is not None else settings.retrieval_top_k
        self.min_score = min_score if min_score is not None else settings.retrieval_min_score
        self._run_command = command_runner or _default_command_runner

    def search(self, query: str) -> QMDSearchResponse:
        """Run qmd query --json and parse results into QMDSearchHit dataclasses."""
        # Format min_score with two decimal places to match expected string format
        min_score_str = f"{self.min_score:.2f}"
        command = (
            "qmd",
            "--index",
            self.index_name,
            "query",
            "--json",
            "-n",
            str(self.top_k),
            "-c",
            self.collection_name,
            "--min-score",
            min_score_str,
            query,
        )
        try:
            result = self._run_command(command)
        except FileNotFoundError:
            return QMDSearchResponse(
                ok=False,
                hits=(),
                diagnostics=(
                    QMDSearchDiagnostic(
                        category="backend_unavailable",
                        recovery_hint="Comando `qmd` nao encontrado. Instale o QMD e valide com `qmd --help`.",
                    ),
                ),
            )

        if result.returncode != 0:
            return QMDSearchResponse(
                ok=False,
                hits=(),
                diagnostics=(
                    QMDSearchDiagnostic(
                        category="query_failed",
                        recovery_hint=(
                            f"Falha ao executar qmd query. "
                            f"Execute `qmd --index {self.index_name} query` manualmente para diagnosticar."
                        ),
                    ),
                ),
            )

        try:
            raw_hits = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return QMDSearchResponse(
                ok=False,
                hits=(),
                diagnostics=(
                    QMDSearchDiagnostic(
                        category="parse_error",
                        recovery_hint="Saida do qmd query nao e JSON valido. Execute `aurora kb update` para reindexar.",
                    ),
                ),
            )

        if not isinstance(raw_hits, list):
            raw_hits = []

        hits = tuple(
            QMDSearchHit(
                path=hit.get("file") or hit.get("displayPath") or "",
                score=float(hit.get("score", 0.0)),
                title=str(hit.get("title", "")),
                snippet=str(hit.get("snippet", "")),
            )
            for hit in raw_hits
            if isinstance(hit, dict)
        )

        return QMDSearchResponse(ok=True, hits=hits)

    def keyword_search(self, query: str, *, min_score: float = 0.10) -> QMDSearchResponse:
        """Run qmd search --json (BM25 keyword) and parse results into QMDSearchHit dataclasses.

        Uses BM25 keyword matching instead of hybrid search. Suitable for proper-noun queries
        where hybrid search may underweight exact matches (e.g., names like "Rosely").
        """
        command = (
            "qmd",
            "--index",
            self.index_name,
            "search",
            "--json",
            "-n",
            str(self.top_k),
            "-c",
            self.collection_name,
            "--min-score",
            f"{min_score:.2f}",
            query,
        )
        try:
            result = self._run_command(command)
        except FileNotFoundError:
            return QMDSearchResponse(
                ok=False,
                hits=(),
                diagnostics=(
                    QMDSearchDiagnostic(
                        category="backend_unavailable",
                        recovery_hint="Comando `qmd` nao encontrado. Instale o QMD e valide com `qmd --help`.",
                    ),
                ),
            )

        if result.returncode != 0:
            return QMDSearchResponse(
                ok=False,
                hits=(),
                diagnostics=(
                    QMDSearchDiagnostic(
                        category="query_failed",
                        recovery_hint=(
                            f"Falha ao executar qmd search. "
                            f"Execute `qmd --index {self.index_name} search` manualmente para diagnosticar."
                        ),
                    ),
                ),
            )

        try:
            raw_hits = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return QMDSearchResponse(
                ok=False,
                hits=(),
                diagnostics=(
                    QMDSearchDiagnostic(
                        category="parse_error",
                        recovery_hint="Saida do qmd search nao e JSON valido. Execute `aurora kb update` para reindexar.",
                    ),
                ),
            )

        if not isinstance(raw_hits, list):
            raw_hits = []

        hits = tuple(
            QMDSearchHit(
                path=hit.get("file") or hit.get("displayPath") or "",
                score=float(hit.get("score", 0.0)),
                title=str(hit.get("title", "")),
                snippet=str(hit.get("snippet", "")),
            )
            for hit in raw_hits
            if isinstance(hit, dict)
        )

        return QMDSearchResponse(ok=True, hits=hits)

    def fetch(self, relative_path: str) -> str | None:
        """Run qmd get <collection>/<relative_path> and return full note content.

        Returns None on non-zero exit or when qmd is unavailable (per D-03).
        """
        command = (
            "qmd",
            "--index",
            self.index_name,
            "get",
            f"{self.collection_name}/{relative_path}",
        )
        try:
            result = self._run_command(command)
        except FileNotFoundError:
            return None

        if result.returncode != 0:
            return None

        return result.stdout


__all__ = ["QMDSearchBackend"]
