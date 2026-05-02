"""RetrievalService — orchestrates QMD search -> fetch -> truncate -> context assembly."""
from __future__ import annotations

import logging
import re
from typing import Callable

from aurora.retrieval.contracts import QMDSearchHit, RetrievalResult, RetrievedNote
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.runtime.settings import RuntimeSettings, load_settings

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 24_000


def _extract_proper_nouns(query: str) -> set[str]:
    """Extract likely proper nouns from a query string.

    Extracts:
    - Double-quoted phrases: "meu diario" -> {"meu diario"}
    - Capitalized words that are NOT the first word of the string
      (sentence-start words are conventionally capitalized but not necessarily proper nouns)

    Returns an empty set if no proper nouns are detected.
    """
    result: set[str] = set()

    # Extract quoted phrases and strip them from the working string
    quoted_phrases = re.findall(r'"([^"]+)"', query)
    for phrase in quoted_phrases:
        result.add(phrase)
    working = re.sub(r'"[^"]+"', " ", query)

    # Extract capitalized words
    # Skip common Portuguese sentence-start words that are conventionally capitalized
    _SKIP_STARTS = {"O", "A", "Os", "As", "Um", "Uma", "Eu", "No", "Na", "De", "Em", "Se", "Que", "Como"}
    words = working.split()
    for word in words:
        stripped = word.rstrip("?!.,;:")
        if len(stripped) >= 2 and stripped[0].isupper() and stripped not in _SKIP_STARTS:
            result.add(stripped)

    return result

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

    def retrieve(
        self,
        query: str,
        *,
        search_strategy: str = "hybrid",
        search_terms: list[str] | None = None,
    ) -> RetrievalResult:
        """Search vault and assemble grounded context for LLM consumption.

        The search_strategy (from intent classification) determines which QMD commands to use:
        - "hybrid": qmd query (semantic + keyword + rerank) — default
        - "keyword": qmd search (BM25 exact match) — best for names, specific terms
        - "both": run both and merge results

        Hits are split into hybrid- and keyword-origin buckets so emitted
        RetrievedNotes can be tagged accurately (Phase 7 sufficiency primitive
        applies the top-score floor only against hybrid hits — RESEARCH §2).
        """
        terms = search_terms or []
        hybrid_hits, keyword_hits = self._search_with_strategy_split(
            self._backend, query, search_strategy, terms
        )

        if not hybrid_hits and not keyword_hits:
            return _INSUFFICIENT

        retrieved = self._fetch_notes_split(hybrid_hits, keyword_hits, source="vault")
        if not retrieved:
            return _INSUFFICIENT

        context_text = self._assemble_context(retrieved)

        return RetrievalResult(
            ok=True,
            notes=tuple(retrieved),
            context_text=context_text,
            insufficient_evidence=False,
        )

    def retrieve_memory_first(
        self,
        query: str,
        *,
        search_strategy: str = "hybrid",
        search_terms: list[str] | None = None,
    ) -> RetrievalResult:
        """Query both KB and memory collections, merge results, memory-first."""
        terms = search_terms or []
        # Split KB hits by source path so we can tag origin per-bucket (RESEARCH §2)
        kb_hybrid_hits, kb_keyword_hits = self._search_with_strategy_split(
            self._backend, query, search_strategy, terms
        )

        # Query memory collection; treat failures as empty (Pitfall 3)
        mem_hits: tuple[QMDSearchHit, ...] = ()
        if self._memory_backend is not None:
            mem_response = self._memory_backend.search(query)
            if mem_response.ok:
                mem_hits = mem_response.hits

        # Gate: no results from either source
        has_kb = bool(kb_hybrid_hits) or bool(kb_keyword_hits)
        has_mem = bool(mem_hits)
        if not has_kb and not has_mem:
            return _INSUFFICIENT

        # Vault notes: hybrid + keyword bucketed (cross-origin dedup keeps hybrid)
        vault_notes = self._fetch_notes_split(
            kb_hybrid_hits, kb_keyword_hits, source="vault"
        )

        # Dedup and fetch memory notes (source="memory", origin="hybrid" — memory uses semantic only)
        mem_unique = self._dedup_hits(mem_hits)
        memory_notes: list[RetrievedNote] = []
        if self._memory_backend is not None:
            memory_notes = self._fetch_notes(
                mem_unique, source="memory", origin="hybrid", backend=self._memory_backend
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

    def retrieve_with_memory(
        self,
        query: str,
        *,
        search_strategy: str = "hybrid",
        search_terms: list[str] | None = None,
    ) -> RetrievalResult:
        """Query both KB and memory collections, merge results, vault-first."""
        terms = search_terms or []
        # Split KB hits by source path so we can tag origin per-bucket (RESEARCH §2)
        kb_hybrid_hits, kb_keyword_hits = self._search_with_strategy_split(
            self._backend, query, search_strategy, terms
        )

        # Query memory collection; treat failures as empty (Pitfall 3)
        mem_hits: tuple[QMDSearchHit, ...] = ()
        if self._memory_backend is not None:
            mem_response = self._memory_backend.search(query)
            if mem_response.ok:
                mem_hits = mem_response.hits

        # Gate: no results from either source
        has_kb = bool(kb_hybrid_hits) or bool(kb_keyword_hits)
        has_mem = bool(mem_hits)
        if not has_kb and not has_mem:
            return _INSUFFICIENT

        # Vault notes: hybrid + keyword bucketed (cross-origin dedup keeps hybrid)
        vault_notes = self._fetch_notes_split(
            kb_hybrid_hits, kb_keyword_hits, source="vault"
        )

        # Dedup and fetch memory notes (source="memory", origin="hybrid" — memory uses semantic only)
        mem_unique = self._dedup_hits(mem_hits)
        memory_notes: list[RetrievedNote] = []
        if self._memory_backend is not None:
            memory_notes = self._fetch_notes(
                mem_unique, source="memory", origin="hybrid", backend=self._memory_backend
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

    def _keyword_fallback(
        self, query: str, backend: QMDSearchBackend
    ) -> tuple[QMDSearchHit, ...]:
        """Run keyword search if query contains proper nouns; return hits or empty tuple.

        Proper noun detection is intentionally simple: capitalized non-first words and
        double-quoted phrases. Uses min_score=0.10 (BM25 scores differ from hybrid).
        """
        proper_nouns = _extract_proper_nouns(query)
        if not proper_nouns:
            return ()

        # Search for each proper noun individually and merge results
        all_hits: list[QMDSearchHit] = []
        for noun in proper_nouns:
            response = backend.keyword_search(noun)
            if response.ok:
                all_hits.extend(response.hits)
            else:
                logger.debug("_keyword_fallback: keyword_search for %r returned ok=False", noun)

        return tuple(all_hits)

    def _search_with_strategy(
        self,
        backend: QMDSearchBackend,
        query: str,
        strategy: str,
        terms: list[str],
    ) -> tuple[QMDSearchHit, ...]:
        """Execute search using the LLM-determined strategy."""
        all_hits: tuple[QMDSearchHit, ...] = ()

        if strategy == "keyword" and terms:
            for term in terms:
                response = backend.keyword_search(term)
                if response.ok:
                    all_hits = all_hits + response.hits
        elif strategy == "both":
            response = backend.search(query)
            all_hits = response.hits if response.ok else ()
            for term in terms:
                kw_response = backend.keyword_search(term)
                if kw_response.ok:
                    all_hits = all_hits + kw_response.hits
        else:  # hybrid (default)
            response = backend.search(query)
            all_hits = response.hits if response.ok else ()

        return all_hits

    def _search_with_strategy_split(
        self,
        backend: QMDSearchBackend,
        query: str,
        strategy: str,
        terms: list[str],
    ) -> tuple[tuple[QMDSearchHit, ...], tuple[QMDSearchHit, ...]]:
        """Execute search using the LLM strategy and split into (hybrid, keyword) buckets.

        Phase 7-01 introduced this helper alongside the legacy _search_with_strategy
        so each bucket can be tagged with its retrieval-path origin downstream
        (origin="hybrid" for backend.search, origin="keyword" for backend.keyword_search).
        Existing callers of _search_with_strategy are unchanged.
        """
        hybrid_hits: tuple[QMDSearchHit, ...] = ()
        keyword_hits: tuple[QMDSearchHit, ...] = ()

        if strategy == "keyword" and terms:
            for term in terms:
                response = backend.keyword_search(term)
                if response.ok:
                    keyword_hits = keyword_hits + response.hits
        elif strategy == "both":
            response = backend.search(query)
            hybrid_hits = response.hits if response.ok else ()
            for term in terms:
                kw_response = backend.keyword_search(term)
                if kw_response.ok:
                    keyword_hits = keyword_hits + kw_response.hits
        else:  # hybrid (default)
            response = backend.search(query)
            hybrid_hits = response.hits if response.ok else ()

        return hybrid_hits, keyword_hits

    def _fetch_notes_split(
        self,
        hybrid_hits: tuple[QMDSearchHit, ...],
        keyword_hits: tuple[QMDSearchHit, ...],
        *,
        source: str = "vault",
    ) -> list[RetrievedNote]:
        """Dedup each bucket and fetch notes tagged with the correct origin.

        Cross-origin dedup: when the same path appears in both buckets, the
        hybrid hit wins (semantic ranking is more meaningful than BM25 for the
        sufficiency primitive's top-score check).
        """
        hybrid_unique = self._dedup_hits(hybrid_hits) if hybrid_hits else []
        keyword_unique = self._dedup_hits(keyword_hits) if keyword_hits else []

        # Cross-origin dedup: prefer hybrid (semantic) when same path appears in both
        hybrid_paths = {h.path for h in hybrid_unique}
        keyword_unique = [h for h in keyword_unique if h.path not in hybrid_paths]

        hybrid_notes = self._fetch_notes(hybrid_unique, source=source, origin="hybrid")
        keyword_notes = self._fetch_notes(keyword_unique, source=source, origin="keyword")
        return hybrid_notes + keyword_notes

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
        origin: str = "hybrid",
        backend: QMDSearchBackend | None = None,
    ) -> list[RetrievedNote]:
        """Fetch full content for each hit, skip None returns (per D-03).

        The ``origin`` kw-arg tags each emitted note with its retrieval source path
        ("hybrid" for backend.search, "keyword" for backend.keyword_search, "carry"
        for ChatSession's _apply_carry_forward supplements). Phase 7 sufficiency
        primitive uses this to apply the top-score floor only against hybrid hits.
        """
        _backend = backend if backend is not None else self._backend
        retrieved: list[RetrievedNote] = []
        for hit in hits:
            content = _backend.fetch(hit.path)
            if content is None:
                logger.debug("_fetch_notes: skipping %s (fetch returned None)", hit.path)
                continue
            retrieved.append(
                RetrievedNote(
                    path=hit.path,
                    score=hit.score,
                    content=content,
                    source=source,
                    origin=origin,
                )
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


__all__ = ["RetrievalService", "MAX_CONTEXT_CHARS", "_extract_proper_nouns"]
