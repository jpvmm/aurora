"""Frozen dataclass contracts for the retrieval layer."""
from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class RetrievalResult:
    """Final retrieval output consumed by LLMService.

    When insufficient_evidence is True, notes and context_text are empty.
    """

    ok: bool
    notes: tuple[RetrievedNote, ...]
    context_text: str
    insufficient_evidence: bool = False


__all__ = [
    "QMDSearchDiagnostic",
    "QMDSearchHit",
    "QMDSearchResponse",
    "RetrievedNote",
    "RetrievalResult",
]
