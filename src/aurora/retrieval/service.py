"""RetrievalService — orchestrates QMD search -> fetch -> truncate -> context assembly."""
from __future__ import annotations

import logging
from typing import Callable

from aurora.retrieval.contracts import RetrievalResult, RetrievedNote
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.runtime.settings import RuntimeSettings, load_settings

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 12_000

_INSUFFICIENT = RetrievalResult(
    ok=True,
    notes=(),
    context_text="",
    insufficient_evidence=True,
)


class RetrievalService:
    """Orchestrates vault retrieval: search -> fetch full notes -> assemble truncated context."""

    def __init__(
        self,
        *,
        search_backend: QMDSearchBackend | None = None,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
    ) -> None:
        self._backend = search_backend or QMDSearchBackend(settings_loader=settings_loader)

    def retrieve(self, query: str) -> RetrievalResult:
        """Search vault and assemble grounded context for LLM consumption.

        Steps:
          1. Search QMD index (per D-05: query passed directly, no preprocessing)
          2. Gate on empty/failed results -> InsufficientEvidenceResult
          3. Deduplicate hits by path, keep highest score per path (per D-09)
          4. Fetch full note content via qmd get (per D-03)
          5. Skip notes whose fetch fails
          6. Assemble context, truncate to MAX_CONTEXT_CHARS, top-ranked first (per D-04)
        """
        search_response = self._backend.search(query)

        if not search_response.ok or not search_response.hits:
            logger.debug("retrieve: no results for query (ok=%s)", search_response.ok)
            return _INSUFFICIENT

        # Step 3: Deduplicate by path, keep highest score
        best_by_path: dict[str, float] = {}
        for hit in search_response.hits:
            if hit.path not in best_by_path or hit.score > best_by_path[hit.path]:
                best_by_path[hit.path] = hit.score

        # Build unique hits list sorted score-descending
        seen: set[str] = set()
        unique_hits = []
        for hit in sorted(search_response.hits, key=lambda h: h.score, reverse=True):
            if hit.path not in seen and best_by_path[hit.path] == hit.score:
                seen.add(hit.path)
                unique_hits.append(hit)

        logger.debug(
            "retrieve: %d unique hits after dedup; paths+scores: %s",
            len(unique_hits),
            [(h.path, h.score) for h in unique_hits],
        )

        # Step 4 & 5: Fetch full content, skip None returns
        retrieved: list[RetrievedNote] = []
        for hit in unique_hits:
            content = self._backend.fetch(hit.path)
            if content is None:
                logger.debug("retrieve: skipping %s (fetch returned None)", hit.path)
                continue
            retrieved.append(RetrievedNote(path=hit.path, score=hit.score, content=content))

        if not retrieved:
            return _INSUFFICIENT

        # Step 6: Assemble context in score-descending order, truncate to MAX_CONTEXT_CHARS
        context_parts: list[str] = []
        total_chars = 0

        for note in retrieved:
            header = f"--- {note.path} ---\n"
            body = f"{note.content}\n"
            entry = header + body

            remaining = MAX_CONTEXT_CHARS - total_chars
            if remaining <= 0:
                break

            if len(entry) <= remaining:
                context_parts.append(entry)
                total_chars += len(entry)
            else:
                # Partial fit: truncate the entry
                context_parts.append(entry[:remaining])
                total_chars = MAX_CONTEXT_CHARS
                break

        context_text = "".join(context_parts)

        return RetrievalResult(
            ok=True,
            notes=tuple(retrieved),
            context_text=context_text,
            insufficient_evidence=False,
        )


__all__ = ["RetrievalService", "MAX_CONTEXT_CHARS"]
