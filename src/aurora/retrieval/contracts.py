"""Frozen dataclass contracts for the retrieval layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class QMDSearchDiagnostic:
    """Error info for a failed search operation, mirrors QMDBackendDiagnostic pattern."""

    category: str
    recovery_hint: str


@dataclass(frozen=True)
class QMDSearchHit:
    """Single search result from a qmd query command."""

    path: str
    score: float
    title: str
    snippet: str


@dataclass(frozen=True)
class QMDSearchResponse:
    """Result of a qmd query search operation."""

    ok: bool
    hits: tuple[QMDSearchHit, ...] = ()
    diagnostics: tuple[QMDSearchDiagnostic, ...] = ()


@dataclass(frozen=True)
class RetrievedNote:
    """Full note content after retrieval via qmd get."""

    path: str
    score: float
    content: str
    source: str = "vault"
    origin: Literal["hybrid", "keyword", "carry"] = "hybrid"


@dataclass(frozen=True)
class RetrievalResult:
    """Final retrieval output consumed by LLMService.

    When insufficient_evidence is True, notes and context_text are empty.
    """

    ok: bool
    notes: tuple[RetrievedNote, ...]
    context_text: str
    insufficient_evidence: bool = False


@dataclass(frozen=True)
class AttemptTrace:
    """One attempt within an iterative retrieval execution.

    PRIV-03: structurally MUST NOT contain note content. Only paths, scores,
    counts, queries, and verdict reason strings (which are derived from counts/
    scores, not from note text). Adding any field whose name is in
    _FORBIDDEN_TRACE_FIELDS will fail
    tests/retrieval/test_contracts.py::test_trace_dataclasses_have_no_content_fields.
    """

    attempt_number: int
    query: str
    intent: Literal["vault", "memory"]
    hit_count: int
    top_score: float
    sufficient: bool
    reason: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class IterativeRetrievalTrace:
    """Full per-execution trace surfaced via --trace.

    PRIV-03: see AttemptTrace docstring. Same structural constraint applies.
    """

    attempts: tuple[AttemptTrace, ...]
    judge_enabled: bool
    early_exit_reason: str = ""


_FORBIDDEN_TRACE_FIELDS = frozenset({
    "content", "snippet", "text", "body", "note_content",
    "excerpt", "preview", "fragment", "passage",
})


__all__ = [
    "QMDSearchDiagnostic",
    "QMDSearchHit",
    "QMDSearchResponse",
    "RetrievedNote",
    "RetrievalResult",
    "AttemptTrace",
    "IterativeRetrievalTrace",
    "_FORBIDDEN_TRACE_FIELDS",
]
