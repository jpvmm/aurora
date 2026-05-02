"""Five-branch coverage for the deterministic sufficiency primitive."""
from __future__ import annotations

from aurora.retrieval.contracts import RetrievalResult, RetrievedNote
from aurora.retrieval.sufficiency import (
    SufficiencyVerdict,
    judge_sufficiency_deterministic,
)
from aurora.runtime.settings import RuntimeSettings


def _settings() -> RuntimeSettings:
    # Use defaults: min_top_score=0.35, min_hits=2, min_context_chars=800
    return RuntimeSettings()


def _note(
    *,
    score: float = 0.85,
    origin: str = "hybrid",
    path: str = "n.md",
    content_chars: int = 1200,
) -> RetrievedNote:
    return RetrievedNote(
        path=path,
        score=score,
        content="x" * content_chars,
        source="vault",
        origin=origin,
    )


def _result(
    notes: list[RetrievedNote], *, insufficient: bool = False
) -> RetrievalResult:
    context = "\n".join(f"--- {n.path} ---\n{n.content}" for n in notes)
    return RetrievalResult(
        ok=True,
        notes=tuple(notes),
        context_text=context,
        insufficient_evidence=insufficient,
    )


class TestSufficiencyFiveBranches:
    def test_branch_1_sufficient(self):
        result = _result(
            [_note(path="a.md"), _note(path="b.md"), _note(path="c.md")]
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is True
        assert verdict.reason == ""

    def test_branch_2_zero_hits(self):
        result = RetrievalResult(
            ok=True, notes=(), context_text="", insufficient_evidence=True
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is False
        assert verdict.reason == "zero hits"

    def test_branch_3_count_thin(self):
        # 1 note (below min_hits=2)
        result = _result([_note(path="solo.md")])
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is False
        assert verdict.reason == "1 hit"

    def test_branch_4_score_thin(self):
        # 2 hybrid notes but top score 0.18 (below 0.35); both have plenty of context
        result = _result(
            [
                _note(path="a.md", score=0.18, content_chars=600),
                _note(path="b.md", score=0.15, content_chars=600),
            ]
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is False
        assert verdict.reason == "top score 0.18"

    def test_branch_5_context_thin(self):
        # 2 notes, top score 0.85, but total context length below 800 chars
        result = _result(
            [
                _note(path="a.md", score=0.85, content_chars=80),
                _note(path="b.md", score=0.75, content_chars=80),
            ]
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is False
        assert verdict.reason.startswith("context ")
        assert verdict.reason.endswith(" chars")

    def test_branch_6_mode_skips_top_score_when_no_hybrid(self):
        # Only keyword-origin notes (BM25 score 4.2 is "unbounded" -> skip top-score)
        result = _result(
            [
                _note(path="kw1.md", score=4.2, content_chars=600, origin="keyword"),
                _note(path="kw2.md", score=2.8, content_chars=600, origin="keyword"),
            ]
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is True
        assert verdict.reason == ""

    def test_carry_origin_does_not_count_toward_hybrid_top_score(self):
        # Carry-forward note with score 0.0 must NOT make top-score check fail
        # when there are no hybrid notes alongside.
        result = _result(
            [
                _note(path="kw.md", score=4.2, content_chars=600, origin="keyword"),
                _note(path="carry.md", score=0.0, content_chars=600, origin="carry"),
            ]
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.sufficient is True

    def test_singular_vs_plural_hit_unit(self):
        # n=1 unit string
        result = _result([_note(path="a.md")])
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.reason == "1 hit"


class TestSufficiencyOrderingDeterminism:
    """Reason ordering is deterministic — first failing floor short-circuits."""

    def test_zero_hits_short_circuits_before_count_check(self):
        # insufficient_evidence flag should win even if notes happen to be empty for both reasons
        result = RetrievalResult(
            ok=True, notes=(), context_text="", insufficient_evidence=True
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.reason == "zero hits"

    def test_count_thin_short_circuits_before_context_check(self):
        # 1 hit with very short context — count check fires first, not context check
        result = _result([_note(path="a.md", content_chars=10)])
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.reason == "1 hit"

    def test_context_thin_short_circuits_before_score_check(self):
        # 2 hybrid notes with low top score AND short context — context wins ordering
        result = _result(
            [
                _note(path="a.md", score=0.18, content_chars=80),
                _note(path="b.md", score=0.15, content_chars=80),
            ]
        )
        verdict = judge_sufficiency_deterministic(result, _settings())
        assert verdict.reason.startswith("context ")


class TestSufficiencyVerdictDataclass:
    def test_verdict_is_frozen(self):
        v = SufficiencyVerdict(True, "")
        try:
            v.sufficient = False  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("SufficiencyVerdict must be frozen")

    def test_verdict_fields(self):
        v = SufficiencyVerdict(False, "1 hit")
        assert v.sufficient is False
        assert v.reason == "1 hit"
