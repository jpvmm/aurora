"""Deterministic sufficiency primitive for the iterative retrieval loop.

Pure function operating on RetrievalResult + RuntimeSettings. No I/O, no LLM,
no logging — keeps the orchestrator (retrieval/iterative.py, Plan 07-02) simple
to test.

Per RESEARCH section 2: hybrid scores (qmd query) are 0.0..1.0; BM25 scores
(qmd search) are unbounded. The top-score threshold is meaningful ONLY against
hybrid-origin hits. When a result has zero hybrid-origin notes, the top-score
check is intentionally skipped (treat keyword/carry as score-passing because
we have no calibrated BM25 threshold).
"""
from __future__ import annotations

from dataclasses import dataclass

from aurora.retrieval.contracts import RetrievalResult
from aurora.runtime.settings import RuntimeSettings


@dataclass(frozen=True)
class SufficiencyVerdict:
    """Outcome of a deterministic sufficiency check.

    sufficient: True when the result passes all configured floors.
    reason: empty when sufficient; short tag describing the failure when not.
            The orchestrator passes this string to the LLM reformulator
            so it knows which way to push the rewrite (more specific vs broader).
    """

    sufficient: bool
    reason: str


def judge_sufficiency_deterministic(
    result: RetrievalResult,
    settings: RuntimeSettings,
) -> SufficiencyVerdict:
    """Apply the three deterministic floors from D-01.

    Order (deterministic, matches test expectations):
        1. zero hits        -> "zero hits"
        2. hit count        -> "{n} hit" / "{n} hits"
        3. context length   -> "context {n} chars"
        4. hybrid top score -> "top score {x:.2f}"  (only when hybrid hits exist)
    """
    if result.insufficient_evidence:
        return SufficiencyVerdict(False, "zero hits")

    hit_count = len(result.notes)
    if hit_count < settings.retrieval_min_hits:
        # English singular/plural — matches what the orchestrator passes to the LLM
        unit = "hit" if hit_count == 1 else "hits"
        return SufficiencyVerdict(False, f"{hit_count} {unit}")

    context_len = len(result.context_text)
    if context_len < settings.retrieval_min_context_chars:
        return SufficiencyVerdict(False, f"context {context_len} chars")

    # Top-score check ONLY against hybrid-origin notes (RESEARCH section 2)
    hybrid_scores = [n.score for n in result.notes if n.origin == "hybrid"]
    if hybrid_scores:
        top = max(hybrid_scores)
        if top < settings.retrieval_min_top_score:
            return SufficiencyVerdict(False, f"top score {top:.2f}")

    return SufficiencyVerdict(True, "")


__all__ = ["SufficiencyVerdict", "judge_sufficiency_deterministic"]
