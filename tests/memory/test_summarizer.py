"""Unit tests for MemorySummarizer and LLMService.summarize_session."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from aurora.llm.prompts import SUMMARIZE_SESSION_PROMPT
from aurora.llm.service import LLMService
from aurora.memory.store import EpisodicMemoryStore


# ---------------------------------------------------------------------------
# SUMMARIZE_SESSION_PROMPT tests
# ---------------------------------------------------------------------------


class TestSummarizeSessionPrompt:
    """Tests for SUMMARIZE_SESSION_PROMPT constant."""

    def test_summarize_session_prompt_is_string(self) -> None:
        assert isinstance(SUMMARIZE_SESSION_PROMPT, str)

    def test_summarize_session_prompt_contains_topic_instruction(self) -> None:
        """Prompt must instruct LLM to produce a short title/topic first line."""
        prompt_lower = SUMMARIZE_SESSION_PROMPT.lower()
        # Should mention topic/title in some form
        assert any(word in prompt_lower for word in ["titulo", "primeira linha", "tema", "60"])

    def test_summarize_session_prompt_has_conversation_placeholder(self) -> None:
        """Prompt must have {conversation} format placeholder."""
        assert "{conversation}" in SUMMARIZE_SESSION_PROMPT

    def test_summarize_session_prompt_in_pt_br(self) -> None:
        """Prompt must be in Portuguese (pt-BR)."""
        # Check for common Portuguese words
        prompt_lower = SUMMARIZE_SESSION_PROMPT.lower()
        assert any(word in prompt_lower for word in ["resumo", "conversa", "resumir", "resuma"])


# ---------------------------------------------------------------------------
# LLMService.summarize_session tests
# ---------------------------------------------------------------------------


class TestLLMServiceSummarizeSession:
    """Tests for LLMService.summarize_session method."""

    def _make_llm_service(self, sync_response: str = "Topico\nCorpo do resumo") -> tuple[LLMService, MagicMock]:
        mock_sync_fn = MagicMock(return_value=sync_response)
        service = LLMService(
            endpoint_url="http://localhost:8080",
            model_id="test-model",
            sync_fn=mock_sync_fn,
        )
        return service, mock_sync_fn

    def test_summarize_session_calls_sync_fn(self) -> None:
        service, mock_sync_fn = self._make_llm_service()
        turns = [{"role": "user", "content": "ola"}, {"role": "assistant", "content": "oi"}]
        service.summarize_session(turns)
        mock_sync_fn.assert_called_once()

    def test_summarize_session_passes_endpoint_and_model(self) -> None:
        service, mock_sync_fn = self._make_llm_service()
        turns = [{"role": "user", "content": "msg"}]
        service.summarize_session(turns)
        call_kwargs = mock_sync_fn.call_args[1]
        assert call_kwargs["endpoint_url"] == "http://localhost:8080"
        assert call_kwargs["model_id"] == "test-model"

    def test_summarize_session_message_contains_conversation_text(self) -> None:
        service, mock_sync_fn = self._make_llm_service()
        turns = [
            {"role": "user", "content": "pergunta sobre Python"},
            {"role": "assistant", "content": "Python e uma linguagem"},
        ]
        service.summarize_session(turns)
        call_kwargs = mock_sync_fn.call_args[1]
        messages = call_kwargs["messages"]
        # The prompt content should contain the formatted turns
        combined = " ".join(m["content"] for m in messages)
        assert "pergunta sobre Python" in combined
        assert "Python e uma linguagem" in combined

    def test_summarize_session_returns_raw_llm_response(self) -> None:
        raw_response = "Titulo da Sessao\nEste e um resumo do conteudo da sessao."
        service, _ = self._make_llm_service(sync_response=raw_response)
        turns = [{"role": "user", "content": "msg"}]
        result = service.summarize_session(turns)
        assert result == raw_response

    def test_summarize_session_sends_user_message(self) -> None:
        """summarize_session should send a user-role message (not system)."""
        service, mock_sync_fn = self._make_llm_service()
        turns = [{"role": "user", "content": "test"}]
        service.summarize_session(turns)
        call_kwargs = mock_sync_fn.call_args[1]
        messages = call_kwargs["messages"]
        assert len(messages) >= 1
        # At least one user message must be present
        roles = [m["role"] for m in messages]
        assert "user" in roles


# ---------------------------------------------------------------------------
# MemorySummarizer tests
# ---------------------------------------------------------------------------


class TestMemorySummarizer:
    """Tests for MemorySummarizer.summarize_and_save."""

    def _make_summarizer(self, tmp_path: Path, llm_response: str = "Topico da Sessao\nCorpo do resumo aqui."):
        from aurora.memory.summarizer import MemorySummarizer

        mock_llm = MagicMock()
        mock_llm.summarize_session.return_value = llm_response

        store = EpisodicMemoryStore(memory_dir=tmp_path / "memories")

        summarizer = MemorySummarizer(llm=mock_llm, store=store)
        return summarizer, mock_llm, store

    def test_summarize_and_save_calls_llm_summarize_session(self, tmp_path: Path) -> None:
        summarizer, mock_llm, _ = self._make_summarizer(tmp_path)
        turns = [{"role": "user", "content": "msg1"}, {"role": "assistant", "content": "resp1"}]
        summarizer.summarize_and_save(history_turns=turns, turn_count=2)
        mock_llm.summarize_session.assert_called_once_with(turns)

    def test_summarize_and_save_calls_store_write(self, tmp_path: Path) -> None:
        summarizer, _, store = self._make_summarizer(tmp_path, llm_response="Topico\nCorpo")
        turns = [{"role": "user", "content": "m"}, {"role": "assistant", "content": "r"}]
        result = summarizer.summarize_and_save(history_turns=turns, turn_count=2)
        assert result is not None
        assert result.exists()

    def test_summarize_and_save_parses_topic_from_first_line(self, tmp_path: Path) -> None:
        topic_line = "Discussao sobre inteligencia artificial"
        summarizer, _, store = self._make_summarizer(tmp_path, llm_response=f"{topic_line}\nCorpo do resumo.")
        turns = [{"role": "user", "content": "m"}]
        result = summarizer.summarize_and_save(history_turns=turns, turn_count=2)
        assert result is not None
        content = result.read_text(encoding="utf-8")
        assert topic_line in content

    def test_summarize_and_save_truncates_topic_to_60_chars(self, tmp_path: Path) -> None:
        long_topic = "A" * 80  # More than 60 chars
        summarizer, _, store = self._make_summarizer(tmp_path, llm_response=f"{long_topic}\nCorpo")
        turns = [{"role": "user", "content": "m"}]
        result = summarizer.summarize_and_save(history_turns=turns, turn_count=2)
        assert result is not None
        content = result.read_text(encoding="utf-8")
        # Topic in frontmatter should be max 60 chars
        assert "A" * 80 not in content  # full long topic not stored
        assert "A" * 60 in content or "A" * 59 in content  # truncated version stored

    def test_summarize_and_save_with_turn_count_less_than_2_returns_none(self, tmp_path: Path) -> None:
        """Per D-11: minimum 2 turns required to create memory."""
        summarizer, mock_llm, _ = self._make_summarizer(tmp_path)
        turns = [{"role": "user", "content": "m"}]
        result = summarizer.summarize_and_save(history_turns=turns, turn_count=1)
        assert result is None
        mock_llm.summarize_session.assert_not_called()

    def test_summarize_and_save_with_turn_count_zero_returns_none(self, tmp_path: Path) -> None:
        summarizer, mock_llm, _ = self._make_summarizer(tmp_path)
        result = summarizer.summarize_and_save(history_turns=[], turn_count=0)
        assert result is None
        mock_llm.summarize_session.assert_not_called()

    def test_summarize_and_save_with_empty_turns_returns_none(self, tmp_path: Path) -> None:
        summarizer, mock_llm, _ = self._make_summarizer(tmp_path)
        result = summarizer.summarize_and_save(history_turns=[], turn_count=2)
        assert result is None
        mock_llm.summarize_session.assert_not_called()


# ---------------------------------------------------------------------------
# MemorySummarizer._parse_response tests
# ---------------------------------------------------------------------------


class TestMemorySummarizerParseResponse:
    """Tests for MemorySummarizer._parse_response static method."""

    def _parse(self, raw: str):
        from aurora.memory.summarizer import MemorySummarizer
        return MemorySummarizer._parse_response(raw)

    def test_parse_response_extracts_first_line_as_topic(self) -> None:
        topic, _ = self._parse("Meu Topico\nCorpo do resumo")
        assert topic == "Meu Topico"

    def test_parse_response_extracts_rest_as_summary(self) -> None:
        _, summary = self._parse("Topico\nLinha 1\nLinha 2")
        assert "Linha 1" in summary
        assert "Linha 2" in summary

    def test_parse_response_truncates_topic_at_60_chars(self) -> None:
        long_topic = "X" * 70
        topic, _ = self._parse(f"{long_topic}\nCorpo")
        assert len(topic) <= 60

    def test_parse_response_empty_string_returns_default_topic(self) -> None:
        topic, summary = self._parse("")
        assert topic == "sessao sem titulo"
        assert summary == ""

    def test_parse_response_single_line_returns_empty_summary(self) -> None:
        topic, summary = self._parse("Apenas o topico")
        assert topic == "Apenas o topico"
        assert summary == ""

    def test_parse_response_strips_whitespace_from_topic(self) -> None:
        topic, _ = self._parse("  Topico com espacos  \nCorpo")
        assert topic == "Topico com espacos"

    def test_parse_response_empty_first_line_uses_second_line_as_topic(self) -> None:
        """When raw starts with newline, strip() removes it, so first non-empty line becomes topic."""
        topic, _ = self._parse("\nCorpo sem topico")
        assert topic == "Corpo sem topico"
