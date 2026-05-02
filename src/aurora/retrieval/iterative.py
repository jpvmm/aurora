"""Iterative retrieval orchestrator (Phase 7).

Wraps RetrievalService at the call-site layer to add a bounded one-reformulation
rescue when the first attempt's evidence is thin. Composition over inheritance
(D-discretion + RESEARCH §1): RetrievalService is unchanged.

The orchestrator does NOT compose any prior-turn note injection (D-07). That
concern lives in the caller, which can pre-build attempt #1 and pass it via the
`first_attempt` parameter. For aurora ask (no prior turns) there is no
prior-turn injection, and the orchestrator calls retrieve_fn itself.
"""
from __future__ import annotations

import re
from typing import Callable, Literal

from aurora.llm.service import LLMService
from aurora.retrieval.contracts import (
    AttemptTrace,
    IterativeRetrievalTrace,
    RetrievalResult,
    RetrievedNote,
)
from aurora.retrieval.service import _INSUFFICIENT, MAX_CONTEXT_CHARS
from aurora.retrieval.sufficiency import (
    SufficiencyVerdict,
    judge_sufficiency_deterministic,
)
from aurora.runtime.settings import RuntimeSettings, load_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token_jaccard(a: str, b: str) -> float:
    """TOKEN-LEVEL Jaccard similarity between two query strings.

    Token = lowercase word after splitting on whitespace and punctuation.
    Do NOT switch to char-level / Levenshtein / sequence-matcher — those
    capture string-shape similarity, not semantic-word-overlap, and would
    block legitimately divergent rewrites that share affixes
    (see Phase 7 RESEARCH §pitfalls 5).

    Empty-vs-empty returns 1.0 by convention: both have no distinguishing
    tokens, so they are equivalent. Empty-vs-nonempty returns 0.0.
    """
    tokens_a = set(re.findall(r"\w+", a.lower()))
    tokens_b = set(re.findall(r"\w+", b.lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _assemble_merged_context(notes: list[RetrievedNote]) -> str:
    """Local copy of RetrievalService._assemble_context to avoid coupling.

    Truncates to MAX_CONTEXT_CHARS in note order. Same semantics as
    RetrievalService — keep these two implementations in sync if the
    truncation rules change.
    """
    parts: list[str] = []
    total = 0
    for note in notes:
        entry = f"--- {note.path} ---\n{note.content}\n"
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 0:
            break
        if len(entry) <= remaining:
            parts.append(entry)
            total += len(entry)
        else:
            parts.append(entry[:remaining])
            break
    return "".join(parts)


def _merge_attempts(r1: RetrievalResult, r2: RetrievalResult) -> RetrievalResult:
    """Merge two attempts. CRITICAL: preserve insufficient_evidence on double-empty.

    Per Phase 7 RESEARCH §pitfalls 1 — the naive merge produces a synthetic
    RetrievalResult with insufficient_evidence=False which silently breaks
    RET-04. Always return the _INSUFFICIENT singleton when merged_notes empty.

    Dedup by path: prefer hybrid-origin over keyword/carry, then highest score.
    """
    # Path dedup with hybrid-prefer + highest score per path
    best: dict[str, RetrievedNote] = {}
    for note in list(r1.notes) + list(r2.notes):
        existing = best.get(note.path)
        if existing is None:
            best[note.path] = note
            continue
        # Prefer hybrid origin
        if existing.origin != "hybrid" and note.origin == "hybrid":
            best[note.path] = note
            continue
        if existing.origin == "hybrid" and note.origin != "hybrid":
            continue
        # Same origin tier -> highest score wins
        if note.score > existing.score:
            best[note.path] = note

    # Order: r1 paths first (preserving original order), then r2-only paths
    ordered: list[RetrievedNote] = []
    seen: set[str] = set()
    for n in r1.notes:
        if n.path in best and n.path not in seen:
            ordered.append(best[n.path])
            seen.add(n.path)
    for n in r2.notes:
        if n.path not in seen and n.path in best:
            ordered.append(best[n.path])
            seen.add(n.path)

    if not ordered:
        return _INSUFFICIENT

    ctx = _assemble_merged_context(ordered)
    return RetrievalResult(
        ok=True, notes=tuple(ordered),
        context_text=ctx, insufficient_evidence=False,
    )


def _build_attempt_trace(
    *,
    attempt_number: int,
    query: str,
    intent: Literal["vault", "memory"],
    result: RetrievalResult,
    verdict: SufficiencyVerdict,
) -> AttemptTrace:
    hybrid_scores = [n.score for n in result.notes if n.origin == "hybrid"]
    top_score = max(hybrid_scores) if hybrid_scores else 0.0
    return AttemptTrace(
        attempt_number=attempt_number,
        query=query,
        intent=intent,
        hit_count=len(result.notes),
        top_score=top_score,
        sufficient=verdict.sufficient,
        reason=verdict.reason,
        paths=tuple(n.path for n in result.notes),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_STATUS_REVISANDO = "Revisando busca..."  # D-02 — sentence case, ASCII triple-dot


class IterativeRetrievalOrchestrator:
    """One-reformulation rescue loop around a single retrieve callable.

    Public surface is `run()` only. Carry-forward is the caller's concern (D-07).
    The hardcoded cap is two attempts (D-03) — there is no settings field for it.
    """

    def __init__(
        self,
        *,
        llm: LLMService,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._llm = llm
        self._settings_loader = settings_loader
        self._on_status = on_status or (lambda _msg: None)

    def run(
        self,
        query: str,
        *,
        intent: Literal["vault", "memory"],
        retrieve_fn: Callable[..., RetrievalResult],
        search_strategy: str,
        search_terms: list[str],
        first_attempt: RetrievalResult | None = None,
    ) -> tuple[RetrievalResult, IterativeRetrievalTrace]:
        settings = self._settings_loader()

        # Disabled mode (D-11): single attempt, no sufficiency check, well-formed trace
        if not settings.iterative_retrieval_enabled:
            result_1 = first_attempt if first_attempt is not None else retrieve_fn(
                query, search_strategy=search_strategy, search_terms=search_terms,
            )
            trace_1 = AttemptTrace(
                attempt_number=1, query=query, intent=intent,
                hit_count=len(result_1.notes),
                top_score=max(
                    (n.score for n in result_1.notes if n.origin == "hybrid"),
                    default=0.0,
                ),
                sufficient=True, reason="",
                paths=tuple(n.path for n in result_1.notes),
            )
            return result_1, IterativeRetrievalTrace(
                attempts=(trace_1,), judge_enabled=False,
                early_exit_reason="disabled",
            )

        # Attempt 1
        result_1 = first_attempt if first_attempt is not None else retrieve_fn(
            query, search_strategy=search_strategy, search_terms=search_terms,
        )
        verdict_1 = judge_sufficiency_deterministic(result_1, settings)

        # Optional LLM judge after deterministic pass (D-01)
        if (
            settings.iterative_retrieval_judge
            and verdict_1.sufficient
            and not result_1.insufficient_evidence
        ):
            judge_ok = self._llm.judge_sufficiency(query, result_1.context_text)
            if not judge_ok:
                verdict_1 = SufficiencyVerdict(False, "judge thin")

        attempt_1 = _build_attempt_trace(
            attempt_number=1, query=query, intent=intent,
            result=result_1, verdict=verdict_1,
        )

        # Sufficient -> single attempt
        if verdict_1.sufficient:
            return result_1, IterativeRetrievalTrace(
                attempts=(attempt_1,),
                judge_enabled=settings.iterative_retrieval_judge,
                early_exit_reason="",
            )

        # Reformulate (D-05, D-06): see only the original query + the sufficiency reason
        reformulated = self._llm.reformulate_query(query, verdict_1.reason)

        # Diversity guard (D-12): exit early if reformulation is too similar
        jaccard = _token_jaccard(query, reformulated)
        if jaccard >= settings.iterative_retrieval_jaccard_threshold:
            return result_1, IterativeRetrievalTrace(
                attempts=(attempt_1,),
                judge_enabled=settings.iterative_retrieval_judge,
                early_exit_reason="high jaccard",
            )

        # Visible status BEFORE the second retrieval (D-02)
        self._on_status(_STATUS_REVISANDO)

        # Attempt 2 — fresh search of the reformulated query
        result_2 = retrieve_fn(
            reformulated,
            search_strategy=search_strategy,
            search_terms=search_terms,
        )
        verdict_2 = judge_sufficiency_deterministic(result_2, settings)
        # Per RESEARCH Open Q3 + D-03: judge_sufficiency NOT called on attempt 2
        # because the reformulation budget is already exhausted — even if judge
        # would say insufficient, we have no more rewrites available.
        attempt_2 = _build_attempt_trace(
            attempt_number=2, query=reformulated, intent=intent,
            result=result_2, verdict=verdict_2,
        )

        merged = _merge_attempts(result_1, result_2)
        return merged, IterativeRetrievalTrace(
            attempts=(attempt_1, attempt_2),
            judge_enabled=settings.iterative_retrieval_judge,
            early_exit_reason="",
        )


__all__ = [
    "IterativeRetrievalOrchestrator",
    "_token_jaccard",
    "_merge_attempts",
    "_build_attempt_trace",
    "_STATUS_REVISANDO",
]
