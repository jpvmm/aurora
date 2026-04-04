"""Unit tests for ChatSession turn tracking and session isolation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aurora.chat.history import ChatHistory
from aurora.chat.session import ChatSession


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.chat_history_max_turns = 10
    return settings


def _make_session(*, tmp_path: Path, vault_intent: bool = False) -> tuple[ChatSession, MagicMock]:
    """Create ChatSession with mocked LLMService and RetrievalService."""
    history = ChatHistory(path=tmp_path / "history.jsonl")
    mock_llm = MagicMock()
    mock_llm.classify_intent.return_value = "vault" if vault_intent else "chat"
    mock_llm.ask_grounded.return_value = "resposta vault"
    mock_llm.chat_turn.return_value = "resposta chat"

    mock_retrieval = MagicMock()
    from aurora.retrieval.contracts import RetrievalResult, RetrievedNote
    note = RetrievedNote(path="notas/test.md", score=0.9, content="content")
    mock_retrieval.retrieve.return_value = RetrievalResult(
        ok=True, notes=(note,), context_text="ctx", insufficient_evidence=False
    )

    session = ChatSession(
        history=history,
        retrieval=mock_retrieval,
        llm=mock_llm,
        settings_loader=lambda: _mock_settings(),
        on_token=lambda t: None,
        on_insufficient=lambda msg: None,
    )
    return session, mock_llm


class TestChatSessionTurnTracking:
    """Tests for turn_count property and session turn isolation."""

    def test_turn_count_starts_at_zero(self, tmp_path: Path) -> None:
        session, _ = _make_session(tmp_path=tmp_path)
        assert session.turn_count == 0

    def test_turn_count_increments_after_each_process_turn(self, tmp_path: Path) -> None:
        session, _ = _make_session(tmp_path=tmp_path)
        session.process_turn("primeira")
        assert session.turn_count == 1

    def test_turn_count_increments_multiple_times(self, tmp_path: Path) -> None:
        session, _ = _make_session(tmp_path=tmp_path)
        session.process_turn("msg1")
        session.process_turn("msg2")
        session.process_turn("msg3")
        assert session.turn_count == 3

    def test_session_start_index_zero_on_empty_history(self, tmp_path: Path) -> None:
        """session_start_index equals len(history.load()) at init time (empty = 0)."""
        session, _ = _make_session(tmp_path=tmp_path)
        assert session.session_start_index == 0

    def test_session_start_index_equals_history_length_at_init(self, tmp_path: Path) -> None:
        """When history has prior turns, session_start_index points past them."""
        history = ChatHistory(path=tmp_path / "history.jsonl")
        # Pre-populate with 2 prior turns
        history.append_turn("user", "historico antigo")
        history.append_turn("assistant", "resposta antiga")

        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "ok"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        # session_start_index should be 2 (skip the 2 pre-existing turns)
        assert session.session_start_index == 2

    def test_get_session_turns_empty_before_any_process_turn(self, tmp_path: Path) -> None:
        session, _ = _make_session(tmp_path=tmp_path)
        turns = session.get_session_turns()
        assert turns == []

    def test_get_session_turns_returns_current_session_only(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        # Pre-populate with prior session turns
        history.append_turn("user", "sessao anterior user")
        history.append_turn("assistant", "sessao anterior assistant")

        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "nova resposta"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )

        session.process_turn("nova pergunta")

        session_turns = session.get_session_turns()
        # Should only include the 2 new turns (user + assistant), not the 2 prior
        assert len(session_turns) == 2
        contents = [t["content"] for t in session_turns]
        assert "nova pergunta" in contents
        assert "nova resposta" in contents
        assert "sessao anterior user" not in contents

    def test_get_session_turns_excludes_historical_turns(self, tmp_path: Path) -> None:
        """Per Pitfall 8: session_start_index isolates current session turns."""
        history = ChatHistory(path=tmp_path / "history.jsonl")
        # 4 prior turns
        for i in range(4):
            history.append_turn("user", f"old_user_{i}")
            history.append_turn("assistant", f"old_asst_{i}")

        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "current_response"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )

        session.process_turn("current_question")
        session.process_turn("current_question_2")

        session_turns = session.get_session_turns()
        assert len(session_turns) == 4  # 2 user + 2 assistant from current session
        for t in session_turns:
            assert not t["content"].startswith("old_")

    def test_llm_property_accessible(self, tmp_path: Path) -> None:
        session, mock_llm = _make_session(tmp_path=tmp_path)
        assert session.llm is mock_llm

    def test_history_property_accessible(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "ok"
        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        assert session.history is history
