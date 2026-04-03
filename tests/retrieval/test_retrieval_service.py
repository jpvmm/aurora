"""Tests for RetrievalService - search -> fetch -> truncate -> context assembly."""
from __future__ import annotations

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


def test_runtime_settings_retrieval_top_k_defaults_to_7():
    """RuntimeSettings.retrieval_top_k must default to 7."""
    from aurora.runtime.settings import RuntimeSettings

    s = RuntimeSettings()
    assert s.retrieval_top_k == 7


def test_runtime_settings_retrieval_top_k_must_be_between_5_and_10():
    """RuntimeSettings must reject retrieval_top_k outside 5-10 range."""
    from pydantic import ValidationError

    from aurora.runtime.settings import RuntimeSettings

    with pytest.raises(ValidationError):
        RuntimeSettings(retrieval_top_k=4)

    with pytest.raises(ValidationError):
        RuntimeSettings(retrieval_top_k=11)
