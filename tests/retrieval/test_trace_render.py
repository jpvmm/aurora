"""Tests for trace_render — pure functions, easy to pin."""
from __future__ import annotations

from aurora.retrieval.contracts import AttemptTrace, IterativeRetrievalTrace
from aurora.retrieval.trace_render import render_trace_json, render_trace_text


def _attempt(**overrides) -> AttemptTrace:
    defaults: dict[str, object] = dict(
        attempt_number=1,
        query="q",
        intent="vault",
        hit_count=2,
        top_score=0.42,
        sufficient=True,
        reason="",
        paths=("a.md", "b.md"),
    )
    defaults.update(overrides)
    return AttemptTrace(**defaults)  # type: ignore[arg-type]


class TestRenderTraceText:
    def test_single_attempt_minimal(self):
        trace = IterativeRetrievalTrace(attempts=(_attempt(),), judge_enabled=False)
        out = render_trace_text(trace)
        assert "retrieval trace (1 attempt(s)):" in out
        assert "attempt 1:" in out
        assert "paths: a.md, b.md" in out

    def test_judge_enabled_marker(self):
        trace = IterativeRetrievalTrace(attempts=(_attempt(),), judge_enabled=True)
        assert "judge=on" in render_trace_text(trace)

    def test_judge_disabled_no_marker(self):
        trace = IterativeRetrievalTrace(attempts=(_attempt(),), judge_enabled=False)
        assert "judge=on" not in render_trace_text(trace)

    def test_early_exit_marker(self):
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(),), judge_enabled=False,
            early_exit_reason="high jaccard",
        )
        assert "exit=high jaccard" in render_trace_text(trace)

    def test_two_attempts_listed_in_order(self):
        a1 = _attempt(attempt_number=1, sufficient=False, reason="1 hit")
        a2 = _attempt(attempt_number=2, query="reformulada", sufficient=True)
        trace = IterativeRetrievalTrace(attempts=(a1, a2), judge_enabled=False)
        out = render_trace_text(trace)
        assert out.index("attempt 1:") < out.index("attempt 2:")
        assert "retrieval trace (2 attempt(s)):" in out

    def test_path_truncation_at_five(self):
        many_paths = tuple(f"n{i}.md" for i in range(8))
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(paths=many_paths),), judge_enabled=False,
        )
        out = render_trace_text(trace)
        assert "(+3 more)" in out

    def test_top_score_renders_na_when_no_hits(self):
        """hit_count=0 → 'top_score=N/A (no hits)' so trace doesn't lie about a 0.0 score."""
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(hit_count=0, top_score=0.0, paths=()),),
            judge_enabled=False,
        )
        out = render_trace_text(trace)
        assert "top_score=N/A (no hits)" in out
        assert "top_score=0.00" not in out, (
            "Zero hits must render as N/A, not 0.00 — that masks the cause"
        )

    def test_top_score_renders_na_when_no_hybrid_hits(self):
        """hit_count>0 but top_score=0.0 means all hits are keyword/carry origin (Phase 7 D-02 score-scale split).

        Without this disambiguation the trace looks identical to "all hybrid hits scored 0",
        which is misleading during diagnostics. Bug C from the 2026-05-03 debug session.
        """
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(hit_count=1, top_score=0.0, paths=("diario/14-04-2026.md",)),),
            judge_enabled=False,
        )
        out = render_trace_text(trace)
        assert "top_score=N/A (no hybrid hits)" in out
        assert "hits=1" in out

    def test_top_score_renders_numeric_when_hybrid_hits_present(self):
        """Normal case: hybrid hit with real score renders as the numeric value."""
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(hit_count=3, top_score=0.42),),
            judge_enabled=False,
        )
        out = render_trace_text(trace)
        assert "top_score=0.42" in out
        assert "N/A" not in out

    def test_empty_paths_renders_none(self):
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(paths=()),), judge_enabled=False,
        )
        out = render_trace_text(trace)
        assert "(none)" in out


class TestRenderTraceJson:
    def test_serialization_shape(self):
        trace = IterativeRetrievalTrace(
            attempts=(
                _attempt(reason="1 hit", sufficient=False),
                _attempt(attempt_number=2, sufficient=True),
            ),
            judge_enabled=True,
            early_exit_reason="",
        )
        payload = render_trace_json(trace)
        assert payload["judge_enabled"] is True
        assert payload["early_exit_reason"] == ""
        attempts = payload["attempts"]
        assert isinstance(attempts, list)
        assert len(attempts) == 2
        assert attempts[0]["attempt_number"] == 1
        assert attempts[0]["reason"] == "1 hit"
        assert attempts[0]["sufficient"] is False
        assert attempts[1]["attempt_number"] == 2
        assert attempts[1]["sufficient"] is True

    def test_paths_serialized_as_lists(self):
        trace = IterativeRetrievalTrace(attempts=(_attempt(),), judge_enabled=False)
        payload = render_trace_json(trace)
        attempts = payload["attempts"]
        assert isinstance(attempts, list)
        assert attempts[0]["paths"] == ["a.md", "b.md"]

    def test_early_exit_reason_passes_through(self):
        trace = IterativeRetrievalTrace(
            attempts=(_attempt(),), judge_enabled=False,
            early_exit_reason="disabled",
        )
        payload = render_trace_json(trace)
        assert payload["early_exit_reason"] == "disabled"

    def test_json_serializable(self):
        """Output must be JSON-serializable end-to-end."""
        import json

        trace = IterativeRetrievalTrace(
            attempts=(_attempt(),), judge_enabled=True,
            early_exit_reason="high jaccard",
        )
        payload = render_trace_json(trace)
        # Must round-trip without TypeError
        recovered = json.loads(json.dumps(payload))
        assert recovered["judge_enabled"] is True
