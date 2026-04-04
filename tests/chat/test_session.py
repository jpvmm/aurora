"""Unit tests for ChatSession intent routing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from aurora.chat.history import ChatHistory
from aurora.chat.session import ChatSession
from aurora.llm.prompts import INSUFFICIENT_EVIDENCE_MSG, SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_GROUNDED
from aurora.retrieval.contracts import RetrievalResult, RetrievedNote


def _make_retrieval_result(*, insufficient: bool = False, context_text: str = "context") -> RetrievalResult:
    if insufficient:
        return RetrievalResult(ok=True, notes=(), context_text="", insufficient_evidence=True)
    note = RetrievedNote(path="notas/test.md", score=0.9, content="test content")
    return RetrievalResult(ok=True, notes=(note,), context_text=context_text, insufficient_evidence=False)


def _make_session(
    *,
    tmp_path: Path,
    vault_intent: bool = True,
    insufficient: bool = False,
    llm_response: str = "resposta teste",
) -> tuple[ChatSession, MagicMock, MagicMock]:
    """Create ChatSession with mocked LLMService and RetrievalService."""
    history = ChatHistory(path=tmp_path / "history.jsonl")
    mock_retrieval = MagicMock()
    mock_llm = MagicMock()

    intent = "vault" if vault_intent else "chat"
    mock_llm.classify_intent.return_value = intent
    mock_llm.ask_grounded.return_value = llm_response
    mock_llm.chat_turn.return_value = llm_response
    mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=insufficient)

    session = ChatSession(
        history=history,
        retrieval=mock_retrieval,
        llm=mock_llm,
        settings_loader=lambda: _mock_settings(),
        on_token=lambda t: None,
        on_insufficient=lambda msg: None,
    )
    return session, mock_llm, mock_retrieval


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.chat_history_max_turns = 10
    return settings


class TestChatSessionVaultIntent:
    """Tests for vault-intent turn handling."""

    def test_vault_turn_calls_retrieval_retrieve(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("o que e Python?")
        mock_retrieval.retrieve.assert_called_once_with("o que e Python?")

    def test_vault_turn_calls_ask_grounded_with_context(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("o que e Python?")
        mock_llm.ask_grounded.assert_called_once()
        args, kwargs = mock_llm.ask_grounded.call_args
        assert "o que e Python?" in (args + tuple(kwargs.values()))

    def test_vault_turn_does_not_call_chat_turn(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("o que e X?")
        mock_llm.chat_turn.assert_not_called()

    def test_vault_turn_re_retrieves_each_call(self, tmp_path: Path) -> None:
        """Per D-13: re-retrieve from KB on each vault turn."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("pergunta 1")
        session.process_turn("pergunta 2")
        assert mock_retrieval.retrieve.call_count == 2

    def test_vault_turn_uses_system_prompt_grounded(self, tmp_path: Path) -> None:
        """Vault turns use SYSTEM_PROMPT_GROUNDED (passed via ask_grounded contract)."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("vault question")
        # ask_grounded was called (which internally uses SYSTEM_PROMPT_GROUNDED in LLMService)
        mock_llm.ask_grounded.assert_called_once()
        mock_llm.chat_turn.assert_not_called()


class TestChatSessionChatIntent:
    """Tests for chat-intent turn handling."""

    def test_chat_turn_calls_chat_turn_without_retrieval(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=False)
        session.process_turn("ola")
        mock_retrieval.retrieve.assert_not_called()
        mock_llm.chat_turn.assert_called_once()

    def test_chat_turn_includes_system_prompt_chat(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=False)
        session.process_turn("ola")
        args, kwargs = mock_llm.chat_turn.call_args
        messages = args[0] if args else kwargs.get("messages", kwargs.get("args", ((),))[0])
        # Extract the messages argument (first positional arg)
        call_args = mock_llm.chat_turn.call_args
        messages_arg = call_args[0][0] if call_args[0] else call_args[1].get("messages")
        assert messages_arg[0]["role"] == "system"
        assert messages_arg[0]["content"] == SYSTEM_PROMPT_CHAT

    def test_chat_turn_includes_user_message_last(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=False)
        session.process_turn("como vai?")
        call_args = mock_llm.chat_turn.call_args
        messages_arg = call_args[0][0] if call_args[0] else call_args[1].get("messages")
        assert messages_arg[-1]["role"] == "user"
        assert messages_arg[-1]["content"] == "como vai?"

    def test_chat_turn_caps_history_to_max_turns(self, tmp_path: Path) -> None:
        """Messages list should be capped to max_turns pairs."""
        history = ChatHistory(path=tmp_path / "history.jsonl")
        # Pre-populate history with 15 pairs
        for i in range(15):
            history.append_turn("user", f"q{i}")
            history.append_turn("assistant", f"a{i}")

        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "ok"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),  # max_turns=10
            on_token=lambda t: None,
        )
        session.process_turn("nova pergunta")

        call_args = mock_llm.chat_turn.call_args
        messages_arg = call_args[0][0] if call_args[0] else call_args[1].get("messages")
        # system prompt + 10 pairs (20 messages) + new user message = 22 max
        # With 15 pairs in history, cap at 10 -> 20 messages + system + current user = 22
        user_msgs = [m for m in messages_arg if m["role"] == "user"]
        assert len(user_msgs) <= 11  # 10 from history + 1 current


class TestChatSessionIntentClassification:
    """Tests for intent classification behavior."""

    def test_classify_intent_receives_only_latest_message(self, tmp_path: Path) -> None:
        """Per Pitfall 5: only latest user message passed to classifier."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("primeira mensagem")
        session.process_turn("segunda mensagem")
        # Each call should pass only the specific user message
        calls = mock_llm.classify_intent.call_args_list
        assert calls[0] == call("primeira mensagem")
        assert calls[1] == call("segunda mensagem")

    def test_classify_intent_called_on_each_turn(self, tmp_path: Path) -> None:
        session, mock_llm, _ = _make_session(tmp_path=tmp_path)
        session.process_turn("msg1")
        session.process_turn("msg2")
        assert mock_llm.classify_intent.call_count == 2


class TestChatSessionHistoryPersistence:
    """Tests for conversation history persistence."""

    def test_process_turn_appends_user_message_to_history(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "resposta"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        session.process_turn("ola")
        records = history.load()
        user_records = [r for r in records if r["role"] == "user"]
        assert len(user_records) == 1
        assert user_records[0]["content"] == "ola"

    def test_process_turn_appends_assistant_response_to_history(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "minha resposta"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        session.process_turn("pergunta")
        records = history.load()
        assistant_records = [r for r in records if r["role"] == "assistant"]
        assert len(assistant_records) == 1
        assert assistant_records[0]["content"] == "minha resposta"

    def test_process_turn_appends_both_user_and_assistant(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "resp"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        session.process_turn("hello")
        records = history.load()
        assert len(records) == 2
        assert records[0]["role"] == "user"
        assert records[1]["role"] == "assistant"


class TestChatSessionInsufficientEvidence:
    """Tests for insufficient evidence handling."""

    def test_insufficient_evidence_calls_on_insufficient(self, tmp_path: Path) -> None:
        on_insufficient = MagicMock()
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "vault"
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=True)

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
            on_insufficient=on_insufficient,
        )
        session.process_turn("o que e X?")
        on_insufficient.assert_called_once_with(INSUFFICIENT_EVIDENCE_MSG)

    def test_insufficient_evidence_does_not_call_ask_grounded(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "vault"
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=True)

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        session.process_turn("o que e X?")
        mock_llm.ask_grounded.assert_not_called()

    def test_insufficient_evidence_returns_insufficient_evidence_msg(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "vault"
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=True)

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        result = session.process_turn("pergunta sem evidencia")
        assert result == INSUFFICIENT_EVIDENCE_MSG


class TestChatSessionMemoryBackend:
    """Tests for ChatSession dual-retrieval when memory_backend is configured."""

    def test_chat_session_accepts_memory_backend_param(self, tmp_path: Path) -> None:
        """ChatSession.__init__ must accept optional memory_backend parameter."""
        from unittest.mock import MagicMock
        from aurora.chat.session import ChatSession
        from aurora.chat.history import ChatHistory

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "chat"
        mock_llm.chat_turn.return_value = "resp"
        mock_memory_backend = MagicMock()

        session = ChatSession(
            history=history,
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
            memory_backend=mock_memory_backend,
        )
        # Should not raise; memory_backend should be passed to retrieval service
        assert session is not None

    def test_vault_turn_uses_retrieve_with_memory_when_memory_backend_configured(self, tmp_path: Path) -> None:
        """_handle_vault_turn must call retrieve_with_memory when memory_backend is available."""
        from aurora.retrieval.contracts import RetrievalResult, RetrievedNote
        from aurora.chat.session import ChatSession
        from aurora.chat.history import ChatHistory

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = "vault"
        mock_llm.ask_grounded.return_value = "resposta"
        mock_llm.chat_turn.return_value = "resposta"

        vault_note = RetrievedNote(path="vault/note.md", score=0.9, content="conteudo", source="vault")
        mock_retrieval.retrieve_with_memory.return_value = RetrievalResult(
            ok=True,
            notes=(vault_note,),
            context_text="context",
            insufficient_evidence=False,
        )
        mock_retrieval._memory_backend = MagicMock()  # Simulate memory backend present

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=lambda: _mock_settings(),
            on_token=lambda t: None,
        )
        session.process_turn("o que e Python?")
        mock_retrieval.retrieve_with_memory.assert_called_once_with("o que e Python?")
