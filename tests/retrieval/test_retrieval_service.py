"""Tests for RetrievalService - search -> fetch -> truncate -> context assembly."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aurora.retrieval.contracts import (
    QMDSearchDiagnostic,
    QMDSearchHit,
    QMDSearchResponse,
    RetrievalResult,
    RetrievedNote,
)
from aurora.retrieval.service import MAX_CONTEXT_CHARS, RetrievalService


def _hit(path: str, score: float = 0.80) -> QMDSearchHit:
    return QMDSearchHit(path=path, score=score, title=path, snippet="snippet")


def _response(hits: list[QMDSearchHit], ok: bool = True) -> QMDSearchResponse:
    return QMDSearchResponse(ok=ok, hits=tuple(hits))


def _mock_backend(search_response: QMDSearchResponse, fetch_content: dict[str, str | None] | None = None):
    backend = MagicMock()
    backend.search.return_value = search_response
    if fetch_content is not None:
        backend.fetch.side_effect = lambda path: fetch_content.get(path)
    else:
        backend.fetch.return_value = "default note content"
    return backend


def _service(backend) -> RetrievalService:
    return RetrievalService(search_backend=backend)


# ---------------------------------------------------------------------------
# retrieve() basic flow
# ---------------------------------------------------------------------------


def test_retrieve_calls_search_then_fetch():
    """retrieve() must call search() then fetch() for each hit."""
    hits = [_hit("notes/a.md", score=0.90)]
    backend = _mock_backend(_response(hits), fetch_content={"notes/a.md": "content a"})

    service = _service(backend)
    result = service.retrieve("test query")

    backend.search.assert_called_once_with("test query")
    backend.fetch.assert_called_once_with("notes/a.md")
    assert result.ok is True
    assert result.insufficient_evidence is False


def test_retrieve_assembles_context_text():
    """retrieve() must assemble context_text with path headers."""
    hits = [_hit("notes/a.md", score=0.90)]
    backend = _mock_backend(_response(hits), fetch_content={"notes/a.md": "note content here"})

    result = _service(backend).retrieve("query")

    assert "notes/a.md" in result.context_text
    assert "note content here" in result.context_text


def test_retrieve_returns_insufficient_evidence_when_no_hits():
    """retrieve() must return InsufficientEvidenceResult when search returns empty hits."""
    backend = _mock_backend(_response([]))

    result = _service(backend).retrieve("obscure query")

    assert result.ok is True
    assert result.insufficient_evidence is True
    assert result.notes == ()
    assert result.context_text == ""


def test_retrieve_returns_insufficient_evidence_when_search_fails():
    """retrieve() must return insufficient evidence when search response is not ok."""
    backend = _mock_backend(_response([], ok=False))

    result = _service(backend).retrieve("query")

    assert result.insufficient_evidence is True


def test_retrieve_skips_notes_where_fetch_returns_none():
    """retrieve() must skip notes whose fetch() returns None."""
    hits = [_hit("notes/a.md", 0.90), _hit("notes/b.md", 0.80)]
    backend = _mock_backend(
        _response(hits),
        fetch_content={"notes/a.md": "content a", "notes/b.md": None},
    )

    result = _service(backend).retrieve("query")

    assert len(result.notes) == 1
    assert result.notes[0].path == "notes/a.md"


def test_retrieve_truncates_context_to_max_chars():
    """retrieve() must truncate context_text to MAX_CONTEXT_CHARS."""
    # Create content that exceeds the limit
    large_content = "x" * (MAX_CONTEXT_CHARS + 5000)
    hits = [_hit("notes/big.md", score=0.95)]
    backend = _mock_backend(
        _response(hits),
        fetch_content={"notes/big.md": large_content},
    )

    result = _service(backend).retrieve("query")

    assert len(result.context_text) <= MAX_CONTEXT_CHARS


def test_retrieve_prioritizes_top_ranked_notes_on_truncation():
    """retrieve() must include top-ranked notes first when truncating."""
    # Make two large notes; only top-ranked should fully appear
    big_content = "Z" * (MAX_CONTEXT_CHARS // 2 + 1000)
    hits = [_hit("notes/top.md", score=0.95), _hit("notes/low.md", score=0.50)]
    backend = _mock_backend(
        _response(hits),
        fetch_content={"notes/top.md": big_content, "notes/low.md": big_content},
    )

    result = _service(backend).retrieve("query")

    assert len(result.context_text) <= MAX_CONTEXT_CHARS
    # Top note must appear in context
    assert "notes/top.md" in result.context_text


def test_retrieve_deduplicates_notes_by_path():
    """retrieve() must deduplicate hits with the same path, keeping highest score."""
    hits = [
        _hit("notes/dup.md", score=0.80),
        _hit("notes/dup.md", score=0.95),  # higher score, same path
        _hit("notes/other.md", score=0.70),
    ]
    backend = _mock_backend(
        _response(hits),
        fetch_content={"notes/dup.md": "dup content", "notes/other.md": "other content"},
    )

    result = _service(backend).retrieve("query")

    paths = [n.path for n in result.notes]
    assert paths.count("notes/dup.md") == 1
    # The deduplicated hit should have the higher score
    dup_note = next(n for n in result.notes if n.path == "notes/dup.md")
    assert dup_note.score == 0.95


# ---------------------------------------------------------------------------
# RuntimeSettings fields
# ---------------------------------------------------------------------------


def test_runtime_settings_accepts_retrieval_top_k():
    """RuntimeSettings must accept retrieval_top_k field."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings(retrieval_top_k=5)
    assert s.retrieval_top_k == 5


def test_runtime_settings_accepts_retrieval_min_score():
    """RuntimeSettings must accept retrieval_min_score field."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings(retrieval_min_score=0.45)
    assert s.retrieval_min_score == 0.45


def test_runtime_settings_accepts_chat_history_max_turns():
    """RuntimeSettings must accept chat_history_max_turns field."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings(chat_history_max_turns=5)
    assert s.chat_history_max_turns == 5


def test_runtime_settings_retrieval_top_k_defaults_to_15():
    """RuntimeSettings.retrieval_top_k must default to 15."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings()
    assert s.retrieval_top_k == 15


def test_runtime_settings_retrieval_top_k_must_be_between_5_and_30():
    """RuntimeSettings must reject retrieval_top_k outside 5-30 range."""
    from pydantic import ValidationError

    from aurora.runtime.settings import RuntimeSettings

    with pytest.raises(ValidationError):
        RuntimeSettings(retrieval_top_k=4)

    with pytest.raises(ValidationError):
        RuntimeSettings(retrieval_top_k=31)

    # Boundary values that must succeed
    s_lower = RuntimeSettings(retrieval_top_k=5)
    assert s_lower.retrieval_top_k == 5

    s_upper = RuntimeSettings(retrieval_top_k=30)
    assert s_upper.retrieval_top_k == 30

    s_default = RuntimeSettings(retrieval_top_k=15)
    assert s_default.retrieval_top_k == 15


# ---------------------------------------------------------------------------
# retrieve_with_memory() — dual-source retrieval
# ---------------------------------------------------------------------------


class TestRetrieveWithMemory:
    """Tests for dual-source retrieval combining vault KB and episodic memory."""

    def test_retrieve_with_memory_accepts_memory_backend_param(self):
        """RetrievalService.__init__ must accept optional memory_backend parameter."""
        kb_backend = _mock_backend(_response([]))
        mem_backend = _mock_backend(_response([]))
        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        assert service._memory_backend is mem_backend

    def test_retrieve_with_memory_calls_both_backends(self):
        """retrieve_with_memory() must call search on both KB and memory backends."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        mem_hits = [_hit("memory/2024-01.md", score=0.80)]

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/2024-01.md": "memory content"},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("test query")

        kb_backend.search.assert_called_once_with("test query")
        mem_backend.search.assert_called_once_with("test query")
        assert result.ok is True
        assert result.insufficient_evidence is False

    def test_retrieve_with_memory_vault_notes_first(self):
        """Vault hits must appear before memory hits in merged context (D-14)."""
        kb_hits = [_hit("vault/note.md", score=0.70)]
        mem_hits = [_hit("memory/2024-01.md", score=0.90)]  # higher score, but memory

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/2024-01.md": "memory content"},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("query")

        # Vault note must come first regardless of score
        assert result.notes[0].source == "vault"
        assert result.notes[1].source == "memory"

    def test_retrieve_with_memory_tags_sources_correctly(self):
        """Vault notes tagged source='vault', memory notes tagged source='memory'."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        mem_hits = [_hit("memory/2024-01.md", score=0.85)]

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/2024-01.md": "memory content"},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("query")

        vault_notes = [n for n in result.notes if n.source == "vault"]
        memory_notes = [n for n in result.notes if n.source == "memory"]
        assert len(vault_notes) == 1
        assert len(memory_notes) == 1
        assert vault_notes[0].path == "vault/note.md"
        assert memory_notes[0].path == "memory/2024-01.md"

    def test_retrieve_with_memory_returns_insufficient_when_both_empty(self):
        """retrieve_with_memory() must return _INSUFFICIENT when both backends have no hits."""
        kb_backend = _mock_backend(_response([]))
        mem_backend = _mock_backend(_response([]))

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("obscure query")

        assert result.insufficient_evidence is True
        assert result.notes == ()


class TestDualSourceContext:
    """Tests for MAX_CONTEXT_CHARS budget across both sources combined."""

    def test_retrieve_with_memory_respects_max_context_chars(self):
        """Combined context from vault + memory must not exceed MAX_CONTEXT_CHARS."""
        large_content = "x" * (MAX_CONTEXT_CHARS // 2 + 2000)
        kb_hits = [_hit("vault/big.md", score=0.90)]
        mem_hits = [_hit("memory/big.md", score=0.85)]

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/big.md": large_content},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/big.md": large_content},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("query")

        assert len(result.context_text) <= MAX_CONTEXT_CHARS


class TestVaultPriority:
    """Tests verifying vault-first ordering in merged results."""

    def test_vault_notes_always_precede_memory_notes(self):
        """All vault notes must appear before any memory notes in merged list."""
        kb_hits = [_hit("vault/a.md", score=0.70), _hit("vault/b.md", score=0.65)]
        mem_hits = [_hit("memory/x.md", score=0.95), _hit("memory/y.md", score=0.90)]

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/a.md": "a", "vault/b.md": "b"},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/x.md": "x", "memory/y.md": "y"},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("query")

        sources = [n.source for n in result.notes]
        # Find first memory index
        memory_indices = [i for i, s in enumerate(sources) if s == "memory"]
        vault_indices = [i for i, s in enumerate(sources) if s == "vault"]
        if memory_indices and vault_indices:
            assert max(vault_indices) < min(memory_indices)


class TestMemoryBackendFailure:
    """Tests verifying graceful handling of memory backend failures (Pitfall 3)."""

    def test_memory_backend_failure_treated_as_empty_results(self):
        """Memory backend query_failed response must be treated as empty, not error."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )
        mem_backend = _mock_backend(_response([], ok=False))  # memory backend fails

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("query")

        # Should still return vault results, not error
        assert result.ok is True
        assert result.insufficient_evidence is False
        assert len(result.notes) == 1
        assert result.notes[0].source == "vault"

    def test_memory_backend_none_uses_kb_only(self):
        """retrieve_with_memory() without memory_backend must use KB only."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )

        service = RetrievalService(search_backend=kb_backend)  # no memory_backend
        result = service.retrieve_with_memory("query")

        assert result.ok is True
        assert len(result.notes) == 1
        assert result.notes[0].source == "vault"


# ---------------------------------------------------------------------------
# retrieve_memory_first() — memory-first dual-source retrieval
# ---------------------------------------------------------------------------


class TestRetrieveMemoryFirst:
    """Tests for memory-first retrieval combining episodic memory and vault KB."""

    def test_retrieve_memory_first_calls_both_backends(self):
        """retrieve_memory_first() must call search on both KB and memory backends."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        mem_hits = [_hit("memory/2024-01.md", score=0.80)]

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/2024-01.md": "memory content"},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_memory_first("test query")

        kb_backend.search.assert_called_once_with("test query")
        mem_backend.search.assert_called_once_with("test query")
        assert result.ok is True
        assert result.insufficient_evidence is False

    def test_retrieve_memory_first_memory_notes_before_vault_notes(self):
        """Memory hits must appear before vault hits in merged notes (D-04)."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        mem_hits = [_hit("memory/2024-01.md", score=0.70)]  # lower score but memory-first

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/2024-01.md": "memory content"},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_memory_first("query")

        # Memory note must come first regardless of score
        assert result.notes[0].source == "memory"
        assert result.notes[1].source == "vault"

    def test_retrieve_memory_first_returns_insufficient_when_both_empty(self):
        """retrieve_memory_first() must return _INSUFFICIENT when both backends have no hits."""
        kb_backend = _mock_backend(_response([]))
        mem_backend = _mock_backend(_response([]))

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_memory_first("obscure query")

        assert result.insufficient_evidence is True
        assert result.notes == ()

    def test_retrieve_memory_first_with_no_memory_backend_returns_vault_only(self):
        """retrieve_memory_first() without memory_backend falls back to vault-only results."""
        kb_hits = [_hit("vault/note.md", score=0.90)]
        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/note.md": "vault content"},
        )

        service = RetrievalService(search_backend=kb_backend)  # no memory_backend
        result = service.retrieve_memory_first("query")

        assert result.ok is True
        assert len(result.notes) == 1
        assert result.notes[0].source == "vault"

    def test_retrieve_memory_first_respects_max_context_chars(self):
        """Combined context from memory + vault must not exceed MAX_CONTEXT_CHARS."""
        large_content = "x" * (MAX_CONTEXT_CHARS // 2 + 2000)
        kb_hits = [_hit("vault/big.md", score=0.90)]
        mem_hits = [_hit("memory/big.md", score=0.85)]

        kb_backend = _mock_backend(
            _response(kb_hits),
            fetch_content={"vault/big.md": large_content},
        )
        mem_backend = _mock_backend(
            _response(mem_hits),
            fetch_content={"memory/big.md": large_content},
        )

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_memory_first("query")

        assert len(result.context_text) <= MAX_CONTEXT_CHARS


# ---------------------------------------------------------------------------
# Prompts — SYSTEM_PROMPT_GROUNDED_WITH_MEMORY and preferences injection
# ---------------------------------------------------------------------------


class TestMemoryPrompts:
    """Tests for memory-aware system prompts and preferences injection."""

    def test_system_prompt_grounded_with_memory_exists(self):
        """SYSTEM_PROMPT_GROUNDED_WITH_MEMORY must be importable from prompts module."""
        from aurora.llm.prompts import SYSTEM_PROMPT_GROUNDED_WITH_MEMORY
        assert isinstance(SYSTEM_PROMPT_GROUNDED_WITH_MEMORY, str)
        assert len(SYSTEM_PROMPT_GROUNDED_WITH_MEMORY) > 0

    def test_system_prompt_grounded_with_memory_has_citation_instructions(self):
        """SYSTEM_PROMPT_GROUNDED_WITH_MEMORY must include citation instructions for both sources."""
        from aurora.llm.prompts import SYSTEM_PROMPT_GROUNDED_WITH_MEMORY
        # Should mention vault citation format
        assert "caminho" in SYSTEM_PROMPT_GROUNDED_WITH_MEMORY or "vault" in SYSTEM_PROMPT_GROUNDED_WITH_MEMORY
        # Should mention memory citation format (D-16)
        assert "memoria" in SYSTEM_PROMPT_GROUNDED_WITH_MEMORY.lower()

    def test_build_system_prompt_with_preferences_prepends_prefs_when_file_exists(self, tmp_path: Path):
        """build_system_prompt_with_preferences() must prepend preferences content."""
        from aurora.llm.prompts import build_system_prompt_with_preferences

        prefs_path = tmp_path / "preferences.md"
        prefs_path.write_text("Prefira respostas curtas.\n", encoding="utf-8")

        base = "Base prompt aqui."
        result = build_system_prompt_with_preferences(base, prefs_path)

        assert "Prefira respostas curtas." in result
        assert "## Preferencias do usuario" in result
        assert "Base prompt aqui." in result
        # Preferences must come before base prompt
        assert result.index("Preferencias do usuario") < result.index("Base prompt aqui.")

    def test_build_system_prompt_with_preferences_returns_base_when_file_missing(self, tmp_path: Path):
        """build_system_prompt_with_preferences() must return base prompt unchanged when file doesn't exist."""
        from aurora.llm.prompts import build_system_prompt_with_preferences

        prefs_path = tmp_path / "preferences.md"  # Does not exist
        base = "Base prompt."
        result = build_system_prompt_with_preferences(base, prefs_path)

        assert result == base

    def test_build_system_prompt_with_preferences_returns_base_when_file_empty(self, tmp_path: Path):
        """build_system_prompt_with_preferences() must return base prompt when preferences file is empty."""
        from aurora.llm.prompts import build_system_prompt_with_preferences

        prefs_path = tmp_path / "preferences.md"
        prefs_path.write_text("   \n   ", encoding="utf-8")  # whitespace only

        base = "Base prompt."
        result = build_system_prompt_with_preferences(base, prefs_path)

        assert result == base


# ---------------------------------------------------------------------------
# MAX_CONTEXT_CHARS constant
# ---------------------------------------------------------------------------


def test_max_context_chars_is_24000():
    """MAX_CONTEXT_CHARS must equal 24,000 characters."""
    assert MAX_CONTEXT_CHARS == 24_000


# ---------------------------------------------------------------------------
# _extract_proper_nouns helper
# ---------------------------------------------------------------------------


class TestExtractProperNouns:
    """Tests for the _extract_proper_nouns helper function."""

    def test_extracts_capitalized_non_first_words(self):
        """Capitalized words that are not the first word must be returned."""
        from aurora.retrieval.service import _extract_proper_nouns

        result = _extract_proper_nouns("notas sobre Rosely")
        assert result == {"Rosely"}

    def test_skips_common_portuguese_starters(self):
        """Common Portuguese sentence starters (O, A, De, etc.) are skipped."""
        from aurora.retrieval.service import _extract_proper_nouns

        result = _extract_proper_nouns("O que o Anderson fez?")
        assert result == {"Anderson"}
        result2 = _extract_proper_nouns("Onde esta Maria?")
        assert "Maria" in result2

    def test_extracts_quoted_phrases(self):
        """Double-quoted phrases must be extracted as proper nouns."""
        from aurora.retrieval.service import _extract_proper_nouns

        result = _extract_proper_nouns('"meu diario" de marco')
        assert result == {"meu diario"}

    def test_returns_empty_for_no_proper_nouns(self):
        """Lowercase-only queries must return an empty set."""
        from aurora.retrieval.service import _extract_proper_nouns

        result = _extract_proper_nouns("o que eu escrevi ontem")
        assert result == set()

    def test_multiple_proper_nouns(self):
        """Multiple capitalized words and/or quoted phrases must all be returned."""
        from aurora.retrieval.service import _extract_proper_nouns

        result = _extract_proper_nouns("conversa com Maria sobre Python")
        assert result == {"Maria", "Python"}


# ---------------------------------------------------------------------------
# Keyword fallback in retrieve()
# ---------------------------------------------------------------------------


def _mock_backend_with_keyword(
    search_response: QMDSearchResponse,
    keyword_response: QMDSearchResponse | None = None,
    fetch_content: dict[str, str | None] | None = None,
):
    """Create a mock backend that also supports keyword_search()."""
    backend = _mock_backend(search_response, fetch_content)
    if keyword_response is not None:
        backend.keyword_search.return_value = keyword_response
    else:
        backend.keyword_search.return_value = QMDSearchResponse(ok=True, hits=())
    return backend


class TestSearchStrategy:
    """Tests for LLM-driven search strategy in retrieve methods."""

    def test_retrieve_keyword_strategy_calls_keyword_search(self):
        """retrieve() with search_strategy='keyword' must call keyword_search per term."""
        kw_hits = [_hit("notes/rosely.md", score=0.60)]
        backend = _mock_backend_with_keyword(
            _response([]),
            QMDSearchResponse(ok=True, hits=tuple(kw_hits)),
            fetch_content={"notes/rosely.md": "rosely content"},
        )

        service = RetrievalService(search_backend=backend)
        result = service.retrieve("find Rosely", search_strategy="keyword", search_terms=["Rosely"])

        backend.keyword_search.assert_called_once_with("Rosely")
        backend.search.assert_not_called()
        assert len(result.notes) == 1

    def test_retrieve_both_strategy_calls_hybrid_and_keyword(self):
        """retrieve() with search_strategy='both' must call both search and keyword_search."""
        kb_hits = [_hit("notes/a.md", score=0.80)]
        kw_hits = [_hit("notes/rosely.md", score=0.60)]
        backend = _mock_backend_with_keyword(
            _response(kb_hits),
            QMDSearchResponse(ok=True, hits=tuple(kw_hits)),
            fetch_content={"notes/a.md": "content a", "notes/rosely.md": "rosely content"},
        )

        service = RetrievalService(search_backend=backend)
        result = service.retrieve("notas sobre Rosely", search_strategy="both", search_terms=["Rosely"])

        backend.search.assert_called_once()
        backend.keyword_search.assert_called_once_with("Rosely")
        assert len(result.notes) == 2

    def test_retrieve_hybrid_strategy_only_calls_search(self):
        """retrieve() with search_strategy='hybrid' (default) must NOT call keyword_search."""
        kb_hits = [_hit("notes/a.md", score=0.80)]
        backend = _mock_backend_with_keyword(
            _response(kb_hits),
            fetch_content={"notes/a.md": "content a"},
        )

        service = RetrievalService(search_backend=backend)
        service.retrieve("o que eu escrevi ontem")

        backend.keyword_search.assert_not_called()

    def test_retrieve_deduplicates_both_strategy_results(self):
        """When same path returned by both strategies, keep highest score."""
        path = "notes/dup.md"
        kb_hits = [_hit(path, score=0.50)]
        kw_hits = [_hit(path, score=0.80)]

        backend = _mock_backend_with_keyword(
            _response(kb_hits),
            QMDSearchResponse(ok=True, hits=tuple(kw_hits)),
            fetch_content={path: "deduped content"},
        )

        service = RetrievalService(search_backend=backend)
        result = service.retrieve("notas sobre Rosely", search_strategy="both", search_terms=["Rosely"])

        paths = [n.path for n in result.notes]
        assert paths.count(path) == 1
        dup_note = next(n for n in result.notes if n.path == path)
        assert dup_note.score == 0.80

    def test_retrieve_with_memory_uses_strategy(self):
        """retrieve_with_memory() must respect search_strategy parameter."""
        kw_hits = [_hit("vault/rosely.md", score=0.60)]
        kb_backend = _mock_backend_with_keyword(
            _response([]),
            QMDSearchResponse(ok=True, hits=tuple(kw_hits)),
            fetch_content={"vault/rosely.md": "rosely content"},
        )
        mem_backend = _mock_backend(_response([]))

        service = RetrievalService(search_backend=kb_backend, memory_backend=mem_backend)
        result = service.retrieve_with_memory("find Rosely", search_strategy="keyword", search_terms=["Rosely"])

        kb_backend.keyword_search.assert_called_once_with("Rosely")
        assert len(result.notes) == 1
