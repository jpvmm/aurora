"""Minimal scripted fakes for iterative retrieval orchestrator tests.

Co-located with tests/retrieval/ — NOT a conftest.py — explicit imports keep
it discoverable for contributors. Match existing inline-helper test conventions
(`_mock_backend`, `_make_session` patterns elsewhere in the suite).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from aurora.retrieval.contracts import (
    RetrievalResult,
    RetrievedNote,
)


@dataclass
class FakeLLM:
    """Scripted LLM service. Indexes responses by call number per method.

    Mirrors the subset of LLMService used by IterativeRetrievalOrchestrator:
    reformulate_query, judge_sufficiency. AssertionError on unscripted call —
    tests must be explicit about the call sequence they expect.
    """
    reformulations: list[str] = field(default_factory=list)
    judge_verdicts: list[str] = field(default_factory=list)
    reformulate_calls: list[tuple[str, str]] = field(default_factory=list)
    judge_calls: list[tuple[str, str]] = field(default_factory=list)

    def reformulate_query(self, original_query: str, reason: str) -> str:
        self.reformulate_calls.append((original_query, reason))
        idx = len(self.reformulate_calls) - 1
        if idx >= len(self.reformulations):
            raise AssertionError(
                f"FakeLLM.reformulate_query call #{idx + 1} not scripted "
                f"(only {len(self.reformulations)} responses queued)"
            )
        return self.reformulations[idx]

    def judge_sufficiency(self, query: str, context_text: str) -> bool:
        self.judge_calls.append((query, context_text))
        idx = len(self.judge_calls) - 1
        if idx >= len(self.judge_verdicts):
            raise AssertionError(
                f"FakeLLM.judge_sufficiency call #{idx + 1} not scripted"
            )
        # Use the production parser so parser+orchestrator are tested together
        from aurora.llm.service import _parse_judge_verdict
        return _parse_judge_verdict(self.judge_verdicts[idx])


@dataclass
class TieredFakeRetrieval:
    """Scripted retrieval. Returns results in order from a tier list.

    Mimics RetrievalService surface needed by the orchestrator's `run()`:
    a single retrieve* function that takes (query, *, search_strategy, search_terms).
    """
    tiers: list[RetrievalResult] = field(default_factory=list)
    retrieve_calls: list[tuple[str, str, list[str]]] = field(default_factory=list)
    _memory_backend: object = None  # ChatSession checks this attribute

    def retrieve(
        self,
        query: str,
        *,
        search_strategy: str = "hybrid",
        search_terms: list[str] | None = None,
    ) -> RetrievalResult:
        self.retrieve_calls.append((query, search_strategy, search_terms or []))
        idx = len(self.retrieve_calls) - 1
        if idx >= len(self.tiers):
            raise AssertionError(f"TieredFakeRetrieval call #{idx + 1} not scripted")
        return self.tiers[idx]

    # Same shape for retrieve_with_memory / retrieve_memory_first
    retrieve_with_memory = retrieve
    retrieve_memory_first = retrieve


# Convenience builders ---------------------------------------------------------

def thin_result() -> RetrievalResult:
    """A 'thin' retrieval result: 1 hybrid hit with low score and short context."""
    note = RetrievedNote(
        path="notas/weak.md", score=0.18, content="x" * 50,
        source="vault", origin="hybrid",
    )
    return RetrievalResult(
        ok=True, notes=(note,),
        context_text="--- notas/weak.md ---\n" + ("x" * 50),
        insufficient_evidence=False,
    )


def thick_result(*, n_notes: int = 3) -> RetrievalResult:
    """A 'thick' result that should pass deterministic sufficiency."""
    notes = tuple(
        RetrievedNote(
            path=f"notas/strong_{i}.md", score=0.85 - i * 0.05,
            content="conteudo substantivo " * 80,
            source="vault", origin="hybrid",
        )
        for i in range(n_notes)
    )
    context = "\n".join(f"--- {n.path} ---\n{n.content}" for n in notes)
    return RetrievalResult(
        ok=True, notes=notes, context_text=context, insufficient_evidence=False,
    )


def empty_result() -> RetrievalResult:
    """A retrieval result with zero notes — matches _INSUFFICIENT semantics."""
    # Mirror the _INSUFFICIENT singleton from retrieval/service.py
    return RetrievalResult(
        ok=True, notes=(), context_text="", insufficient_evidence=True,
    )
