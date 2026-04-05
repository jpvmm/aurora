"""RetrievalService — orchestrates QMD search -> fetch -> truncate -> context assembly."""
from __future__ import annotations

import logging
from typing import Callable

from aurora.retrieval.contracts import QMDSearchHit, RetrievalResult, RetrievedNote
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
        memory_backend: QMDSearchBackend | None = None,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
    ) -> None:
        self._backend = search_backend or QMDSearchBackend(settings_loader=settings_loader)
        self._memory_backend = memory_backend

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

        unique_hits = self._dedup_hits(search_response.hits)
        retrieved = self._fetch_notes(unique_hits, source="vault")

        if not retrieved:
            return _INSUFFICIENT

        context_text = self._assemble_context(retrieved)

        return RetrievalResult(
            ok=True,
            notes=tuple(retrieved),
            context_text=context_text,
            insufficient_evidence=False,
        )

    def retrieve_memory_first(self, query: str) -> RetrievalResult:
        """Query both KB and memory collections, merge results, memory-first (D-04, D-06).

        Always queries memory backend first (priority). Queries KB as supplement.
        Memory notes are listed first. Combined context respects MAX_CONTEXT_CHARS.
        """
        # Always query KB
        kb_response = self._backend.search(query)

        # Query memory collection; treat failures as empty (Pitfall 3)
        mem_hits: tuple[QMDSearchHit, ...] = ()
        if self._memory_backend is not None:
            mem_response = self._memory_backend.search(query)
            if mem_response.ok:
                mem_hits = mem_response.hits

        # Gate: no results from either source
        has_kb = kb_response.ok and bool(kb_response.hits)
        has_mem = bool(mem_hits)
        if not has_kb and not has_mem:
            return _INSUFFICIENT

        # Dedup and fetch vault notes (source="vault")
        kb_unique = self._dedup_hits(kb_response.hits if kb_response.ok else ())
        vault_notes = self._fetch_notes(kb_unique, source="vault")

        # Dedup and fetch memory notes (source="memory")
        mem_unique = self._dedup_hits(mem_hits)
        memory_notes: list[RetrievedNote] = []
        if self._memory_backend is not None:
            for hit in mem_unique:
                content = self._memory_backend.fetch(hit.path)
                if content is not None:
                    memory_notes.append(
                        RetrievedNote(
                            path=hit.path,
                            score=hit.score,
                            content=content,
                            source="memory",
                        )
                    )

        all_notes = memory_notes + vault_notes  # MEMORY first (D-04)
        if not all_notes:
            return _INSUFFICIENT

        context_text = self._assemble_context(all_notes)
        return RetrievalResult(
            ok=True,
            notes=tuple(all_notes),
            context_text=context_text,
            insufficient_evidence=False,
        )

    def retrieve_with_memory(self, query: str) -> RetrievalResult:
        """Query both KB and memory collections, merge results, vault-first (D-14, D-15).

        Always queries KB. Queries memory backend if available; failures treated as
        empty results (Pitfall 3). Vault notes are always listed first (D-14).
        Combined context respects MAX_CONTEXT_CHARS budget (Pitfall 4).
        """
        # Always query KB
        kb_response = self._backend.search(query)

        # Query memory collection; treat failures as empty (Pitfall 3)
        mem_hits: tuple[QMDSearchHit, ...] = ()
        if self._memory_backend is not None:
            mem_response = self._memory_backend.search(query)
            if mem_response.ok:
                mem_hits = mem_response.hits

        # Gate: no results from either source
        has_kb = kb_response.ok and bool(kb_response.hits)
        has_mem = bool(mem_hits)
        if not has_kb and not has_mem:
            return _INSUFFICIENT

        # Dedup and fetch vault notes (source="vault")
        kb_unique = self._dedup_hits(kb_response.hits if kb_response.ok else ())
        vault_notes = self._fetch_notes(kb_unique, source="vault")

        # Dedup and fetch memory notes (source="memory")
        mem_unique = self._dedup_hits(mem_hits)
        memory_notes: list[RetrievedNote] = []
        if self._memory_backend is not None:
            for hit in mem_unique:
                content = self._memory_backend.fetch(hit.path)
                if content is not None:
                    memory_notes.append(
                        RetrievedNote(
                            path=hit.path,
                            score=hit.score,
                            content=content,
                            source="memory",
                        )
                    )

        all_notes = vault_notes + memory_notes  # vault first (D-14)
        if not all_notes:
            return _INSUFFICIENT

        context_text = self._assemble_context(all_notes)
        return RetrievalResult(
            ok=True,
            notes=tuple(all_notes),
            context_text=context_text,
            insufficient_evidence=False,
        )

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    def _dedup_hits(self, hits: tuple[QMDSearchHit, ...]) -> list[QMDSearchHit]:
        """Deduplicate hits by path, keeping highest score per path (per D-09)."""
        best_by_path: dict[str, float] = {}
        for hit in hits:
            if hit.path not in best_by_path or hit.score > best_by_path[hit.path]:
                best_by_path[hit.path] = hit.score

        seen: set[str] = set()
        unique_hits: list[QMDSearchHit] = []
        for hit in sorted(hits, key=lambda h: h.score, reverse=True):
            if hit.path not in seen and best_by_path[hit.path] == hit.score:
                seen.add(hit.path)
                unique_hits.append(hit)

        logger.debug(
            "_dedup_hits: %d unique hits; paths+scores: %s",
            len(unique_hits),
            [(h.path, h.score) for h in unique_hits],
        )
        return unique_hits

    def _fetch_notes(
        self,
        hits: list[QMDSearchHit],
        *,
        source: str = "vault",
        backend: QMDSearchBackend | None = None,
    ) -> list[RetrievedNote]:
        """Fetch full content for each hit, skip None returns (per D-03)."""
        _backend = backend if backend is not None else self._backend
        retrieved: list[RetrievedNote] = []
        for hit in hits:
            content = _backend.fetch(hit.path)
            if content is None:
                logger.debug("_fetch_notes: skipping %s (fetch returned None)", hit.path)
                continue
            retrieved.append(
                RetrievedNote(path=hit.path, score=hit.score, content=content, source=source)
            )
        return retrieved

    def _assemble_context(self, notes: list[RetrievedNote]) -> str:
        """Assemble context in note order, truncate to MAX_CONTEXT_CHARS (per D-04)."""
        context_parts: list[str] = []
        total_chars = 0

        for note in notes:
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

        return "".join(context_parts)


__all__ = ["RetrievalService", "MAX_CONTEXT_CHARS"]
