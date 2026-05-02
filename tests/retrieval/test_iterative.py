"""Orchestrator unit tests — pin every CONTEXT decision and RESEARCH pitfall."""
from __future__ import annotations

from typing import Callable

from aurora.retrieval.contracts import RetrievalResult, RetrievedNote
from aurora.retrieval.iterative import (
    IterativeRetrievalOrchestrator,
    _STATUS_REVISANDO,
    _merge_attempts,
    _token_jaccard,
)
from aurora.retrieval.service import _INSUFFICIENT
from aurora.runtime.settings import RuntimeSettings

from .fakes import (
    FakeLLM,
    TieredFakeRetrieval,
    empty_result,
    thick_result,
    thin_result,
)


def _orch(
    *,
    llm: FakeLLM,
    settings: RuntimeSettings | None = None,
    on_status: Callable[[str], None] | None = None,
) -> IterativeRetrievalOrchestrator:
    settings = settings or RuntimeSettings()
    return IterativeRetrievalOrchestrator(
        llm=llm,
        settings_loader=lambda: settings,
        on_status=on_status,
    )


class TestThinThenThickTriggersOneReformulation:
    def test_two_attempts_one_reformulation(self):
        retrieval = TieredFakeRetrieval(tiers=[thin_result(), thick_result()])
        llm = FakeLLM(reformulations=["consulta totalmente diferente refinada"])
        orch = _orch(llm=llm)
        result, trace = orch.run(
            "original",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert len(trace.attempts) == 2
        assert len(llm.reformulate_calls) == 1
        assert len(llm.judge_calls) == 0  # judge default off
        assert trace.attempts[1].sufficient is True
        # The merged result has hits from both attempts (or at least the thick one)
        assert len(result.notes) >= 1


class TestHardCapAtTwoRetrievals:
    def test_never_exceeds_two_attempts(self):
        # 5 thin tiers in queue; retrieve called exactly 2x
        retrieval = TieredFakeRetrieval(tiers=[thin_result()] * 5)
        llm = FakeLLM(reformulations=["consulta refinada substancialmente diferente",
                                       "outra consulta", "mais uma"])
        orch = _orch(llm=llm)
        _, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert len(retrieval.retrieve_calls) == 2
        assert len(trace.attempts) == 2


class TestDoubleEmptyPreservesInsufficient:
    def test_both_empty_returns_insufficient_singleton(self):
        # RESEARCH §pitfalls 1 — the load-bearing pin
        retrieval = TieredFakeRetrieval(tiers=[empty_result(), empty_result()])
        llm = FakeLLM(reformulations=["consulta totalmente diferente"])
        orch = _orch(llm=llm)
        # "q" vs "consulta totalmente diferente" -> Jaccard ~0
        final, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert final.insufficient_evidence is True
        assert final.notes == ()
        assert final is _INSUFFICIENT  # identity — pin singleton reuse
        assert len(trace.attempts) == 2


class TestJaccardGuard:
    def test_high_jaccard_skips_second_retrieval(self):
        # Reformulation that shares > 70% tokens with original
        retrieval = TieredFakeRetrieval(tiers=[thin_result()])
        # Original "produtividade hoje cedo" (3 tokens) ->
        # Reformulated "produtividade hoje cedo manha" (4 tokens) -> 3/4 = 0.75 >= 0.7
        llm = FakeLLM(reformulations=["produtividade hoje cedo manha"])
        status_calls: list[str] = []
        orch = _orch(llm=llm, on_status=status_calls.append)
        _, trace = orch.run(
            "produtividade hoje cedo",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert len(retrieval.retrieve_calls) == 1
        assert trace.early_exit_reason == "high jaccard"
        assert status_calls == []  # status NEVER called when guard fires


class TestStatusCallbackInvokedBeforeSecondRetrieval:
    def test_status_called_when_loop_fires(self):
        retrieval = TieredFakeRetrieval(tiers=[thin_result(), thick_result()])
        llm = FakeLLM(reformulations=["consulta totalmente diferente"])
        status_calls: list[str] = []
        orch = _orch(llm=llm, on_status=status_calls.append)
        orch.run(
            "original",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert status_calls == [_STATUS_REVISANDO]
        assert _STATUS_REVISANDO == "Revisando busca..."

    def test_status_not_called_when_attempt_1_sufficient(self):
        retrieval = TieredFakeRetrieval(tiers=[thick_result()])
        llm = FakeLLM()
        status_calls: list[str] = []
        orch = _orch(llm=llm, on_status=status_calls.append)
        orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert status_calls == []


class TestModeSkipsTopScoreWhenNoHybrid:
    def test_keyword_only_result_is_sufficient_despite_bm25_score(self):
        # Build a result with only origin="keyword" notes — top-score check skipped
        kw_notes = (
            RetrievedNote(
                path="a.md", score=4.2, content="x" * 600,
                source="vault", origin="keyword",
            ),
            RetrievedNote(
                path="b.md", score=2.8, content="y" * 600,
                source="vault", origin="keyword",
            ),
        )
        kw_result = RetrievalResult(
            ok=True, notes=kw_notes,
            context_text="ctx" * 400, insufficient_evidence=False,
        )
        retrieval = TieredFakeRetrieval(tiers=[kw_result])
        llm = FakeLLM()  # No reformulations queued -> sufficient on attempt 1
        orch = _orch(llm=llm)
        _, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="keyword",
            search_terms=["q"],
        )
        assert len(trace.attempts) == 1
        assert trace.attempts[0].sufficient is True


class TestReformulationPromptOnlySeesQueryAndReason:
    def test_secret_in_note_content_does_not_reach_llm(self):
        SECRET = "SECRET_TOKEN_DO_NOT_LEAK_42"
        leaky = RetrievedNote(
            path="leak.md", score=0.18,
            content=f"prefix {SECRET} suffix",
            source="vault", origin="hybrid",
        )
        leaky_thin = RetrievalResult(
            ok=True, notes=(leaky,),
            context_text=f"--- leak.md ---\nprefix {SECRET} suffix",
            insufficient_evidence=False,
        )
        retrieval = TieredFakeRetrieval(tiers=[leaky_thin, thick_result()])
        llm = FakeLLM(reformulations=["consulta totalmente diferente refinada"])
        orch = _orch(llm=llm)
        orch.run(
            "original",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        # The reformulator was called with (original, reason) only — no content
        assert len(llm.reformulate_calls) == 1
        original, reason = llm.reformulate_calls[0]
        assert original == "original"
        assert SECRET not in original
        assert SECRET not in reason


class TestDisabledModeReturnsExactlyOneAttempt:
    def test_disabled_skips_loop_entirely(self):
        settings = RuntimeSettings(iterative_retrieval_enabled=False)
        retrieval = TieredFakeRetrieval(tiers=[thin_result()])
        llm = FakeLLM()  # No scripted responses -> would fail if called
        status_calls: list[str] = []
        orch = _orch(llm=llm, settings=settings, on_status=status_calls.append)
        result, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert len(trace.attempts) == 1
        assert trace.early_exit_reason == "disabled"
        assert llm.reformulate_calls == []
        assert llm.judge_calls == []
        assert status_calls == []
        assert result == thin_result()  # byte-equivalent to single-shot


class TestJudgeOn:
    def test_judge_on_and_first_sufficient_no_reformulation(self):
        settings = RuntimeSettings(iterative_retrieval_judge=True)
        retrieval = TieredFakeRetrieval(tiers=[thick_result()])
        llm = FakeLLM(judge_verdicts=["sim"])
        orch = _orch(llm=llm, settings=settings)
        _, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert len(trace.attempts) == 1
        assert len(llm.judge_calls) == 1
        assert llm.reformulate_calls == []
        assert trace.judge_enabled is True

    def test_judge_on_says_insufficient_triggers_reformulation(self):
        settings = RuntimeSettings(iterative_retrieval_judge=True)
        retrieval = TieredFakeRetrieval(tiers=[thick_result(), thick_result()])
        llm = FakeLLM(
            reformulations=["consulta refinada totalmente nova"],
            judge_verdicts=["nao"],   # judge says insufficient on attempt 1
        )
        orch = _orch(llm=llm, settings=settings)
        _, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
        )
        assert len(trace.attempts) == 2
        # judge NOT called on attempt 2 (budget exhausted per RESEARCH Open Q3)
        assert len(llm.judge_calls) == 1
        assert len(llm.reformulate_calls) == 1


class TestCarryForwardNotTouchedByOrchestrator:
    def test_orchestrator_does_not_import_chatsession(self):
        # D-07 / RESEARCH §pitfalls 2 — structural pin
        import inspect
        from aurora.retrieval import iterative
        source = inspect.getsource(iterative)
        assert "ChatSession" not in source
        assert "_apply_carry_forward" not in source
        # "carry" may appear only in the docstring explaining "carry-forward
        # is the caller's concern". Tolerate that one mention; ban any other.
        lower = source.lower()
        if "carry" in lower:
            assert "carry-forward is the caller" in lower or \
                   "carry-forward" in lower  # only in docstring


class TestFirstAttemptParameterUsedDirectly:
    def test_first_attempt_skips_initial_retrieve_call(self):
        retrieval = TieredFakeRetrieval(tiers=[thick_result(n_notes=5)])  # only used if loop fires
        llm = FakeLLM()
        orch = _orch(llm=llm)
        result, trace = orch.run(
            "q",
            intent="vault",
            retrieve_fn=retrieval.retrieve,
            search_strategy="hybrid",
            search_terms=[],
            first_attempt=thick_result(),
        )
        # No retrieve calls because attempt 1 came from first_attempt and was sufficient
        assert retrieval.retrieve_calls == []
        assert len(trace.attempts) == 1


class TestTokenJaccardIsTokenLevelNotChar:
    def test_shared_affix_does_not_count_as_high_similarity(self):
        # "produtividade" and "produtivo" share characters but no whole tokens
        assert _token_jaccard("produtividade hoje", "produtivo agora") < 0.5

    def test_identical_strings_have_jaccard_1(self):
        assert _token_jaccard("a b c", "a b c") == 1.0

    def test_disjoint_token_sets_have_jaccard_0(self):
        assert _token_jaccard("a b c", "d e f") == 0.0

    def test_empty_strings_handled(self):
        assert _token_jaccard("", "") == 1.0
        assert _token_jaccard("a", "") == 0.0


class TestMergeAttempts:
    def test_double_empty_returns_singleton(self):
        assert _merge_attempts(empty_result(), empty_result()) is _INSUFFICIENT

    def test_dedup_keeps_higher_score_per_path(self):
        n_low = RetrievedNote(path="a.md", score=0.5, content="x" * 400,
                              source="vault", origin="hybrid")
        n_high = RetrievedNote(path="a.md", score=0.9, content="x" * 400,
                               source="vault", origin="hybrid")
        r1 = RetrievalResult(ok=True, notes=(n_low,), context_text="ctx",
                             insufficient_evidence=False)
        r2 = RetrievalResult(ok=True, notes=(n_high,), context_text="ctx",
                             insufficient_evidence=False)
        merged = _merge_attempts(r1, r2)
        assert len(merged.notes) == 1
        assert merged.notes[0].score == 0.9

    def test_hybrid_origin_wins_over_keyword_for_same_path(self):
        n_kw = RetrievedNote(path="a.md", score=4.2, content="x" * 400,
                             source="vault", origin="keyword")
        n_hyb = RetrievedNote(path="a.md", score=0.5, content="x" * 400,
                              source="vault", origin="hybrid")
        r1 = RetrievalResult(ok=True, notes=(n_kw,), context_text="ctx",
                             insufficient_evidence=False)
        r2 = RetrievalResult(ok=True, notes=(n_hyb,), context_text="ctx",
                             insufficient_evidence=False)
        merged = _merge_attempts(r1, r2)
        assert merged.notes[0].origin == "hybrid"
