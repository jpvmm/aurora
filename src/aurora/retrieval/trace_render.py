"""Render IterativeRetrievalTrace for stderr (text) and JSON envelopes.

Pure functions — kept OUT of retrieval/contracts.py so the contract module
stays a pure data layer. Both renderers operate only on AttemptTrace fields
(paths, scores, counts, queries, reasons) — by construction they cannot leak
note content (PRIV-03 + D-13).
"""
from __future__ import annotations

from typing import Iterable

from aurora.retrieval.contracts import AttemptTrace, IterativeRetrievalTrace

_MAX_PATHS_INLINE = 5


def _format_paths(paths: tuple[str, ...]) -> str:
    if not paths:
        return "(none)"
    if len(paths) <= _MAX_PATHS_INLINE:
        return ", ".join(paths)
    shown = ", ".join(paths[:_MAX_PATHS_INLINE])
    extra = len(paths) - _MAX_PATHS_INLINE
    return f"{shown} (+{extra} more)"


def _format_top_score(attempt: AttemptTrace) -> str:
    """Render top_score honestly, disambiguating zero-hits from no-hybrid-hits.

    Phase 7 score-scale split (D-02): top_score reflects ONLY hybrid-origin
    hits. When hits exist but all are keyword/carry origin, the orchestrator
    reports top_score=0.0 (iterative.py:_build_attempt_trace). Without this
    annotation the trace looks identical to "all hybrid hits scored zero",
    which is confusing during diagnostics.
    """
    if attempt.hit_count == 0:
        return "top_score=N/A (no hits)"
    if attempt.top_score == 0.0:
        return "top_score=N/A (no hybrid hits)"
    return f"top_score={attempt.top_score:.2f}"


def _format_attempt(attempt: AttemptTrace) -> Iterable[str]:
    yield (
        f"  attempt {attempt.attempt_number}: "
        f"query=\"{attempt.query}\" "
        f"intent={attempt.intent} "
        f"hits={attempt.hit_count} "
        f"{_format_top_score(attempt)} "
        f"sufficient={attempt.sufficient} "
        f"reason=\"{attempt.reason}\""
    )
    yield f"             paths: {_format_paths(attempt.paths)}"


def render_trace_text(trace: IterativeRetrievalTrace) -> str:
    """Return multi-line stderr-friendly trace summary (D-09 text mode)."""
    markers: list[str] = []
    if trace.judge_enabled:
        markers.append("judge=on")
    if trace.early_exit_reason:
        markers.append(f"exit={trace.early_exit_reason}")
    marker_str = (", " + ", ".join(markers)) if markers else ""
    lines = [
        f"retrieval trace ({len(trace.attempts)} attempt(s){marker_str}):",
    ]
    for attempt in trace.attempts:
        lines.extend(_format_attempt(attempt))
    return "\n".join(lines)


def render_trace_json(trace: IterativeRetrievalTrace) -> dict[str, object]:
    """Return JSON-serializable dict for the --json envelope's `trace` key (D-09)."""
    return {
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "query": a.query,
                "intent": a.intent,
                "hit_count": a.hit_count,
                "top_score": a.top_score,
                "sufficient": a.sufficient,
                "reason": a.reason,
                "paths": list(a.paths),
            }
            for a in trace.attempts
        ],
        "judge_enabled": trace.judge_enabled,
        "early_exit_reason": trace.early_exit_reason,
    }


__all__ = ["render_trace_text", "render_trace_json"]
