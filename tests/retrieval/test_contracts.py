"""Structural tests for retrieval contracts (PRIV-03 enforcement)."""
from __future__ import annotations

from dataclasses import fields

from aurora.retrieval.contracts import (
    AttemptTrace,
    IterativeRetrievalTrace,
    RetrievedNote,
    _FORBIDDEN_TRACE_FIELDS,
)


class TestTraceDataclassPrivacy:
    def test_trace_dataclasses_have_no_content_fields(self):
        """PRIV-03 / D-13: trace structure must not have a field that could hold note content."""
        for cls in (AttemptTrace, IterativeRetrievalTrace):
            field_names = {f.name for f in fields(cls)}
            offenders = field_names & _FORBIDDEN_TRACE_FIELDS
            assert offenders == set(), (
                f"{cls.__name__} contains forbidden content-bearing field(s): {offenders}. "
                "Adding such a field violates PRIV-03 and is blocked by this test."
            )

    def test_attempt_trace_has_required_fields(self):
        names = {f.name for f in fields(AttemptTrace)}
        assert names == {
            "attempt_number", "query", "intent", "hit_count",
            "top_score", "sufficient", "reason", "paths",
        }

    def test_iterative_retrieval_trace_has_required_fields(self):
        names = {f.name for f in fields(IterativeRetrievalTrace)}
        assert names == {"attempts", "judge_enabled", "early_exit_reason"}


class TestRetrievedNoteOrigin:
    def test_origin_defaults_to_hybrid(self):
        note = RetrievedNote(path="x.md", score=0.5, content="x", source="vault")
        assert note.origin == "hybrid"

    def test_origin_can_be_keyword_or_carry(self):
        n1 = RetrievedNote(
            path="a.md", score=0.5, content="x", source="vault", origin="keyword"
        )
        n2 = RetrievedNote(
            path="b.md", score=0.0, content="y", source="vault", origin="carry"
        )
        assert n1.origin == "keyword"
        assert n2.origin == "carry"

    def test_existing_construction_without_origin_still_works(self):
        # Backward compat: construction without origin keeps default "hybrid"
        note = RetrievedNote(path="a.md", score=0.5, content="x")
        assert note.origin == "hybrid"
        assert note.source == "vault"
