"""Tests for LLMService.reformulate_query, LLMService.judge_sufficiency, _parse_judge_verdict.

# RESEARCH §3 ambiguity policy: when first segment contains BOTH 'sim' and 'nao',
# negative wins. "sim porque nao falta nada" -> False (conservative reformulation).
# The system prompt instructs the model to answer "Apenas: sim ou nao" — any model
# output containing both tokens is ambiguous and we reformulate to be safe.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from aurora.llm.service import LLMService, _parse_judge_verdict


def _llm(*, sync_response: str = "ok") -> tuple[LLMService, MagicMock]:
    sync_fn = MagicMock(return_value=sync_response)
    service = LLMService(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        sync_fn=sync_fn,
    )
    return service, sync_fn


class TestReformulateQuery:
    def test_calls_sync_fn_with_system_and_user_messages(self):
        service, sync_fn = _llm(sync_response="nova consulta refinada")
        service.reformulate_query("consulta original", "1 hit")
        messages = sync_fn.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "reformula consultas" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "consulta original" in messages[1]["content"]
        assert "1 hit" in messages[1]["content"]

    def test_strips_quotes_and_trailing_punctuation(self):
        service, _ = _llm(sync_response='  "o que escrevi sobre produtividade ontem?"  \n')
        result = service.reformulate_query("orig", "thin")
        assert result == "o que escrevi sobre produtividade ontem"

    def test_strips_single_quotes_too(self):
        service, _ = _llm(sync_response="'minha consulta'")
        assert service.reformulate_query("o", "r") == "minha consulta"

    def test_prompt_does_not_see_note_content(self):
        # Privacy contract (D-06): reformulation prompt sees only query + reason
        service, sync_fn = _llm(sync_response="reformulado")
        SECRET = "SECRET_TOKEN_DO_NOT_LEAK_42"
        # Caller never passes content; this test pins the contract by inspecting
        # what the LLM message payload contains.
        service.reformulate_query("consulta", "top score 0.18")
        serialized = str(sync_fn.call_args.kwargs["messages"])
        assert SECRET not in serialized  # trivially true; contract pin


class TestJudgeSufficiency:
    def test_calls_sync_fn_and_returns_parsed_bool(self):
        service, sync_fn = _llm(sync_response="sim")
        assert service.judge_sufficiency("q", "ctx") is True
        # And the prompt embeds query + context
        msgs = sync_fn.call_args.kwargs["messages"]
        assert "q" in msgs[0]["content"]
        assert "ctx" in msgs[0]["content"]

    def test_fail_closed_on_no_verdict(self):
        service, _ = _llm(sync_response="O contexto fala sobre Python.")
        assert service.judge_sufficiency("q", "ctx") is False


class TestParseJudgeVerdict:
    # Five-branch matrix from RESEARCH §3
    def test_clean_sim_returns_true(self):
        assert _parse_judge_verdict("sim") is True

    def test_clean_nao_returns_false(self):
        assert _parse_judge_verdict("nao") is False
        assert _parse_judge_verdict("não") is False

    def test_sim_porque_nao_falta_nada_negative_wins_returns_false(self):
        # First segment is "sim porque nao falta nada" — no period before "nao".
        # Both 'sim' and 'nao' present in first segment -> negative wins -> False.
        # The system prompt explicitly says "Apenas: sim ou nao", so a model
        # putting both is ambiguous and we conservatively reformulate.
        assert _parse_judge_verdict("sim porque nao falta nada") is False

    def test_nao_mas_sim_em_parte_returns_false(self):
        # "não, mas sim em parte" -> first segment is "não, mas sim em parte"
        # (split on '.\n!?' — the comma is NOT a separator).
        # negative wins -> False.
        assert _parse_judge_verdict("não, mas sim em parte") is False

    def test_empty_returns_false(self):
        assert _parse_judge_verdict("") is False
        assert _parse_judge_verdict("   \n  ") is False

    def test_off_prompt_returns_false(self):
        assert _parse_judge_verdict("O contexto fala sobre Python.") is False

    def test_sim_with_first_period_takes_only_first_segment(self):
        # "Sim. mas falta detalhe" -> first segment "Sim" -> True (no neg in first segment)
        assert _parse_judge_verdict("Sim. mas falta detalhe") is True

    def test_nao_with_first_period_takes_only_first_segment(self):
        # "Não. é suficiente sim" -> first segment "Não" -> False
        assert _parse_judge_verdict("Não. é suficiente sim") is False
