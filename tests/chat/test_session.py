"""Unit tests for ChatSession intent routing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from aurora.chat.history import ChatHistory
from aurora.chat.session import ChatSession
from aurora.llm.prompts import INSUFFICIENT_EVIDENCE_MSG, SYSTEM_PROMPT_CHAT, SYSTEM_PROMPT_GROUNDED
from aurora.llm.service import IntentResult
from aurora.retrieval.contracts import RetrievalResult, RetrievedNote


def _intent(intent: str, search: str = "hybrid", terms: list[str] | None = None) -> IntentResult:
    """Helper to create IntentResult for test mocks."""
    return IntentResult(intent=intent, search=search, terms=terms or [])


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

    intent_str = "vault" if vault_intent else "chat"
    mock_llm.classify_intent.return_value = _intent(intent_str)
    mock_llm.ask_grounded.return_value = llm_response
    mock_llm.chat_turn.return_value = llm_response
    mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=insufficient)
    mock_retrieval._memory_backend = None  # No memory backend by default

    session = ChatSession(
        history=history,
        retrieval=mock_retrieval,
        llm=mock_llm,
        settings_loader=_disabled_iterative_settings_loader,
        on_token=lambda t: None,
        on_insufficient=lambda msg: None,
    )
    return session, mock_llm, mock_retrieval


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.chat_history_max_turns = 10
    return settings


def _disabled_iterative_settings_loader():
    """Default settings loader for existing ChatSession tests.

    Phase 7 wires IterativeRetrievalOrchestrator into ChatSession. Existing
    tests don't script reformulation/judge LLM calls and would crash if the
    loop fires — disable the loop here so existing behavior matches today's
    single-shot (D-11). Tests that EXPLICITLY exercise the loop pass their
    own settings_loader.
    """
    from aurora.runtime.settings import RuntimeSettings
    return RuntimeSettings(iterative_retrieval_enabled=False)


class TestChatSessionVaultIntent:
    """Tests for vault-intent turn handling."""

    def test_vault_turn_calls_retrieval_retrieve(self, tmp_path: Path) -> None:
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("o que e Python?")
        mock_retrieval.retrieve.assert_called_once_with("o que e Python?", search_strategy="hybrid", search_terms=[])

    def test_vault_turn_calls_chat_turn_with_context_in_messages(self, tmp_path: Path) -> None:
        """Vault turns use chat_turn with system prompt + context injected in messages."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("o que e Python?")
        mock_llm.chat_turn.assert_called_once()
        call_args = mock_llm.chat_turn.call_args
        messages_arg = call_args[0][0] if call_args[0] else call_args[1].get("messages")
        # System prompt should be first
        assert messages_arg[0]["role"] == "system"
        # User message (with context) should be last
        assert messages_arg[-1]["role"] == "user"
        assert "o que e Python?" in messages_arg[-1]["content"]

    def test_vault_turn_re_retrieves_each_call(self, tmp_path: Path) -> None:
        """Per D-13: re-retrieve from KB on each vault turn."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("pergunta 1")
        session.process_turn("pergunta 2")
        assert mock_retrieval.retrieve.call_count == 2

    def test_vault_turn_uses_system_prompt_grounded(self, tmp_path: Path) -> None:
        """Vault turns (no memory) must use SYSTEM_PROMPT_GROUNDED in system message."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=True)
        session.process_turn("vault question")
        mock_llm.chat_turn.assert_called_once()
        call_args = mock_llm.chat_turn.call_args
        messages_arg = call_args[0][0] if call_args[0] else call_args[1].get("messages")
        system_content = messages_arg[0]["content"]
        # Should contain SYSTEM_PROMPT_GROUNDED text (no memory present)
        assert "vault" in system_content.lower() or "Aurora" in system_content


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
        mock_llm.classify_intent.return_value = _intent("chat")
        mock_llm.chat_turn.return_value = "ok"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,  # max_turns=10
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
        mock_llm.classify_intent.return_value = _intent("chat")
        mock_llm.chat_turn.return_value = "resposta"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
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
        mock_llm.classify_intent.return_value = _intent("chat")
        mock_llm.chat_turn.return_value = "minha resposta"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
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
        mock_llm.classify_intent.return_value = _intent("chat")
        mock_llm.chat_turn.return_value = "resp"

        session = ChatSession(
            history=history,
            retrieval=MagicMock(),
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
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
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=True)
        mock_retrieval._memory_backend = None

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=on_insufficient,
        )
        session.process_turn("o que e X?")
        on_insufficient.assert_called_once_with(INSUFFICIENT_EVIDENCE_MSG)

    def test_insufficient_evidence_does_not_call_chat_turn(self, tmp_path: Path) -> None:
        """Insufficient evidence must not call chat_turn or ask_grounded."""
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=True)
        mock_retrieval._memory_backend = None

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
        )
        session.process_turn("o que e X?")
        mock_llm.chat_turn.assert_not_called()

    def test_insufficient_evidence_returns_insufficient_evidence_msg(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = _make_retrieval_result(insufficient=True)
        mock_retrieval._memory_backend = None

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
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
        mock_llm.classify_intent.return_value = _intent("chat")
        mock_llm.chat_turn.return_value = "resp"
        mock_memory_backend = MagicMock()

        session = ChatSession(
            history=history,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
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
        mock_llm.classify_intent.return_value = _intent("vault")
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
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
        )
        session.process_turn("o que e Python?")
        mock_retrieval.retrieve_with_memory.assert_called_once_with("o que e Python?", search_strategy="hybrid", search_terms=[])


class TestChatSessionMemoryIntent:
    """Tests for memory-intent routing in ChatSession (three-way routing)."""

    def _make_memory_session(
        self,
        tmp_path: "Path",
        *,
        insufficient: bool = False,
        llm_response: str = "resposta memoria",
    ) -> "tuple[ChatSession, MagicMock, MagicMock]":
        """Create ChatSession with mocked LLM returning 'memory' intent."""
        from aurora.chat.history import ChatHistory
        from aurora.retrieval.contracts import RetrievalResult, RetrievedNote

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()

        mock_llm.classify_intent.return_value = _intent("memory")
        mock_llm.chat_turn.return_value = llm_response

        if insufficient:
            mem_result = RetrievalResult(ok=True, notes=(), context_text="", insufficient_evidence=True)
        else:
            mem_note = RetrievedNote(path="memory/2024-01.md", score=0.9, content="conteudo memoria", source="memory")
            mem_result = RetrievalResult(ok=True, notes=(mem_note,), context_text="context", insufficient_evidence=False)

        mock_retrieval.retrieve_memory_first.return_value = mem_result
        mock_retrieval._memory_backend = MagicMock()

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=lambda msg: None,
        )
        return session, mock_llm, mock_retrieval

    def test_memory_intent_calls_retrieve_memory_first(self, tmp_path: Path) -> None:
        """'memory' intent must route to retrieve_memory_first, not retrieve/retrieve_with_memory."""
        session, mock_llm, mock_retrieval = self._make_memory_session(tmp_path)
        session.process_turn("o que conversamos ontem?")
        mock_retrieval.retrieve_memory_first.assert_called_once_with("o que conversamos ontem?", search_strategy="hybrid", search_terms=[])

    def test_memory_intent_does_not_call_retrieve_or_retrieve_with_memory(self, tmp_path: Path) -> None:
        """'memory' intent must NOT call retrieve() or retrieve_with_memory()."""
        session, mock_llm, mock_retrieval = self._make_memory_session(tmp_path)
        session.process_turn("o que conversamos ontem?")
        mock_retrieval.retrieve.assert_not_called()
        mock_retrieval.retrieve_with_memory.assert_not_called()

    def test_memory_intent_uses_memory_first_system_prompt(self, tmp_path: Path) -> None:
        """'memory' intent must use get_system_prompt_memory_first (Priorize as memorias or conversas anteriores)."""
        session, mock_llm, mock_retrieval = self._make_memory_session(tmp_path)
        session.process_turn("o que conversamos ontem?")

        mock_llm.chat_turn.assert_called_once()
        call_args = mock_llm.chat_turn.call_args
        messages_arg = call_args[0][0] if call_args[0] else call_args[1].get("messages")
        system_content = messages_arg[0]["content"]
        # Memory-first prompt must contain memory-relevant text
        assert "memorias" in system_content.lower() or "conversas anteriores" in system_content.lower()

    def test_vault_intent_not_affected_by_memory_routing(self, tmp_path: Path) -> None:
        """Adding memory routing must not break vault intent routing."""
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_llm.chat_turn.return_value = "vault response"

        vault_note = RetrievedNote(path="vault/note.md", score=0.9, content="content", source="vault")
        mock_retrieval.retrieve.return_value = RetrievalResult(
            ok=True, notes=(vault_note,), context_text="context", insufficient_evidence=False
        )
        mock_retrieval._memory_backend = None

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
        )
        session.process_turn("o que escrevi sobre Python?")
        mock_retrieval.retrieve.assert_called_once()
        mock_retrieval.retrieve_memory_first.assert_not_called()

    def test_chat_intent_not_affected_by_memory_routing(self, tmp_path: Path) -> None:
        """Adding memory routing must not break chat intent routing."""
        session, mock_llm, mock_retrieval = _make_session(tmp_path=tmp_path, vault_intent=False)
        session.process_turn("ola")
        mock_retrieval.retrieve.assert_not_called()
        mock_retrieval.retrieve_memory_first.assert_not_called()
        mock_llm.chat_turn.assert_called_once()


class TestCarryForward:
    """Tests for carry-forward state tracking in ChatSession (D-08, D-09, D-10, D-11)."""

    def _make_vault_session(
        self,
        tmp_path: "Path",
        *,
        notes: "list[RetrievedNote] | None" = None,
        insufficient: bool = False,
        llm_response: str = "resposta teste",
    ) -> "tuple[ChatSession, MagicMock, MagicMock]":
        """Create ChatSession with vault intent and configurable retrieval notes."""
        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()

        mock_llm.classify_intent.return_value = _intent("vault")
        mock_llm.chat_turn.return_value = llm_response

        if insufficient:
            result = RetrievalResult(ok=True, notes=(), context_text="", insufficient_evidence=True)
        else:
            _notes = notes or [RetrievedNote(path="notas/test.md", score=0.9, content="conteudo")]
            result = RetrievalResult(ok=True, notes=tuple(_notes), context_text="context", insufficient_evidence=False)

        mock_retrieval.retrieve.return_value = result
        mock_retrieval._memory_backend = None
        mock_retrieval._backend = MagicMock()
        mock_retrieval._assemble_context = MagicMock(return_value="context combinado")

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=lambda msg: None,
        )
        return session, mock_llm, mock_retrieval

    def test_vault_turn_stores_retrieved_paths(self, tmp_path: Path) -> None:
        """After a vault turn, _last_retrieved_paths contains the retrieved note paths."""
        note_a = RetrievedNote(path="notas/a.md", score=0.9, content="conteudo a")
        note_b = RetrievedNote(path="notas/b.md", score=0.8, content="conteudo b")
        session, _, _ = self._make_vault_session(tmp_path, notes=[note_a, note_b])

        session.process_turn("o que e Python?")

        assert set(session._last_retrieved_paths) == {"notas/a.md", "notas/b.md"}

    def test_carry_forward_supplements_fresh_results(self, tmp_path: Path) -> None:
        """Turn 2 should fetch and include note from turn 1 that is not in fresh results."""
        note_a = RetrievedNote(path="notas/a.md", score=0.9, content="conteudo a")
        note_b = RetrievedNote(path="notas/b.md", score=0.8, content="conteudo b")

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_llm.chat_turn.return_value = "resposta"

        # Turn 1: returns note A
        result_1 = RetrievalResult(ok=True, notes=(note_a,), context_text="context 1", insufficient_evidence=False)
        # Turn 2: returns note B (not note A)
        result_2 = RetrievalResult(ok=True, notes=(note_b,), context_text="context 2", insufficient_evidence=False)
        mock_retrieval.retrieve.side_effect = [result_1, result_2]
        mock_retrieval._memory_backend = None
        mock_retrieval._backend = MagicMock()
        mock_retrieval._backend.fetch.return_value = "conteudo a carregado"
        mock_retrieval._assemble_context = MagicMock(return_value="context combinado")

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=lambda msg: None,
        )

        session.process_turn("primeira pergunta")
        session.process_turn("segunda pergunta")

        # fetch should have been called for note A during turn 2
        mock_retrieval._backend.fetch.assert_called_with("notas/a.md")

    def test_carry_forward_skips_paths_already_in_fresh_results(self, tmp_path: Path) -> None:
        """If fresh results already contain the carry-forward path, fetch should not be called."""
        note_a = RetrievedNote(path="notas/a.md", score=0.9, content="conteudo a")

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_llm.chat_turn.return_value = "resposta"

        # Both turns return note A (already in fresh results on turn 2)
        result = RetrievalResult(ok=True, notes=(note_a,), context_text="context", insufficient_evidence=False)
        mock_retrieval.retrieve.return_value = result
        mock_retrieval._memory_backend = None
        mock_retrieval._backend = MagicMock()
        mock_retrieval._assemble_context = MagicMock(return_value="context")

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=lambda msg: None,
        )

        session.process_turn("primeira pergunta")
        # Reset fetch mock to check calls during turn 2 only
        mock_retrieval._backend.fetch.reset_mock()
        session.process_turn("segunda pergunta")

        # fetch should NOT have been called for note A (already in fresh results)
        mock_retrieval._backend.fetch.assert_not_called()

    def test_carry_forward_cleared_on_chat_intent(self, tmp_path: Path) -> None:
        """After a vault turn then a chat turn, _last_retrieved_paths should be empty."""
        note_a = RetrievedNote(path="notas/a.md", score=0.9, content="conteudo a")

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()
        mock_llm.chat_turn.return_value = "resposta"

        # First turn: vault intent
        # Second turn: chat intent
        mock_llm.classify_intent.side_effect = [_intent("vault"), _intent("chat")]

        vault_result = RetrievalResult(ok=True, notes=(note_a,), context_text="context", insufficient_evidence=False)
        mock_retrieval.retrieve.return_value = vault_result
        mock_retrieval._memory_backend = None
        mock_retrieval._backend = MagicMock()
        mock_retrieval._assemble_context = MagicMock(return_value="context")

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=lambda msg: None,
        )

        session.process_turn("vault question")
        assert len(session._last_retrieved_paths) > 0  # Should have paths after vault turn
        session.process_turn("ola")
        assert session._last_retrieved_paths == []

    def test_carry_forward_caps_at_3_paths(self, tmp_path: Path) -> None:
        """Even if 5 notes are retrieved, _last_retrieved_paths must be capped at 3."""
        notes = [
            RetrievedNote(path=f"notas/note{i}.md", score=0.9 - i * 0.1, content=f"conteudo {i}")
            for i in range(5)
        ]
        session, _, _ = self._make_vault_session(tmp_path, notes=notes)

        session.process_turn("vault question")

        assert len(session._last_retrieved_paths) <= 3

    def test_no_carry_forward_on_first_turn(self, tmp_path: Path) -> None:
        """On the first turn, no carry-forward fetch should occur (no previous context)."""
        note_a = RetrievedNote(path="notas/a.md", score=0.9, content="conteudo a")
        session, _, mock_retrieval = self._make_vault_session(tmp_path, notes=[note_a])

        session.process_turn("primeira pergunta")

        # No fetch calls for carry-forward on first turn
        mock_retrieval._backend.fetch.assert_not_called()

    def test_carry_forward_skips_when_fetch_returns_none(self, tmp_path: Path) -> None:
        """If carry-forward fetch returns None, the path is skipped silently."""
        note_a = RetrievedNote(path="notas/a.md", score=0.9, content="conteudo a")
        note_b = RetrievedNote(path="notas/b.md", score=0.8, content="conteudo b")

        history = ChatHistory(path=tmp_path / "history.jsonl")
        mock_retrieval = MagicMock()
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_llm.chat_turn.return_value = "resposta"

        # Turn 1: returns note A; Turn 2: returns note B
        result_1 = RetrievalResult(ok=True, notes=(note_a,), context_text="context 1", insufficient_evidence=False)
        result_2 = RetrievalResult(ok=True, notes=(note_b,), context_text="context 2", insufficient_evidence=False)
        mock_retrieval.retrieve.side_effect = [result_1, result_2]
        mock_retrieval._memory_backend = None
        mock_retrieval._backend = MagicMock()
        # fetch returns None for note A's path (simulates failure)
        mock_retrieval._backend.fetch.return_value = None
        mock_retrieval._assemble_context = MagicMock(return_value="context 2")

        session = ChatSession(
            history=history,
            retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_token=lambda t: None,
            on_insufficient=lambda msg: None,
        )

        session.process_turn("primeira pergunta")
        # Turn 2: fetch returns None, so no supplement is added
        # Should not raise and should produce a valid response
        result = session.process_turn("segunda pergunta")
        assert result == "resposta"  # Normal response, no crash


# ---------------------------------------------------------------------------
# Phase 7 integration tests — orchestrator wiring, status, persistence,
# disable-path byte-equivalence, carry-forward composition.
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field

from aurora.retrieval.contracts import IterativeRetrievalTrace
from aurora.retrieval.iterative import IterativeRetrievalOrchestrator
from aurora.runtime.settings import RuntimeSettings


@dataclass
class _ChatFakeLLM:
    """Minimal scripted LLM for chat-session integration tests.

    Mirrors the surface IterativeRetrievalOrchestrator uses (reformulate_query,
    judge_sufficiency) plus the chat-session surface (classify_intent, chat_turn).
    Lives here (not in tests/retrieval/fakes.py) because cross-package fake reuse
    would require either adding tests/__init__.py + switching wave-2's relative
    imports to absolute, or duplicating; we picked duplication for the smallest
    diff (option a from wave-2 handoff).
    """
    reformulations: list[str] = field(default_factory=list)
    judge_verdicts: list[bool] = field(default_factory=list)
    reformulate_calls: list[tuple[str, str]] = field(default_factory=list)
    judge_calls: list[tuple[str, str]] = field(default_factory=list)
    chat_response: str = "resposta"

    def reformulate_query(self, original_query: str, reason: str) -> str:
        self.reformulate_calls.append((original_query, reason))
        idx = len(self.reformulate_calls) - 1
        if idx >= len(self.reformulations):
            raise AssertionError(
                f"_ChatFakeLLM.reformulate_query call #{idx + 1} not scripted"
            )
        return self.reformulations[idx]

    def judge_sufficiency(self, query: str, context_text: str) -> bool:
        self.judge_calls.append((query, context_text))
        idx = len(self.judge_calls) - 1
        if idx >= len(self.judge_verdicts):
            raise AssertionError(
                f"_ChatFakeLLM.judge_sufficiency call #{idx + 1} not scripted"
            )
        return self.judge_verdicts[idx]

    def classify_intent(self, message: str):
        return _intent("vault")

    def chat_turn(self, messages, on_token=None):
        if on_token:
            on_token(self.chat_response)
        return self.chat_response


def _thin_result() -> RetrievalResult:
    """Single hybrid hit, low score, short context — fails sufficiency floors."""
    note = RetrievedNote(
        path="notas/weak.md", score=0.18, content="x" * 50,
        source="vault", origin="hybrid",
    )
    return RetrievalResult(
        ok=True, notes=(note,),
        context_text="--- notas/weak.md ---\n" + ("x" * 50),
        insufficient_evidence=False,
    )


def _thick_result(*, n_notes: int = 3) -> RetrievalResult:
    """Multi-note hybrid result that passes deterministic sufficiency."""
    notes = tuple(
        RetrievedNote(
            path=f"notas/strong_{i}.md", score=0.85 - i * 0.05,
            content="conteudo substantivo " * 80,
            source="vault", origin="hybrid",
        )
        for i in range(n_notes)
    )
    context = "\n".join(f"--- {n.path} ---\n{n.content}" for n in notes)
    return RetrievalResult(
        ok=True, notes=notes, context_text=context, insufficient_evidence=False,
    )


class TestPhase7Integration:
    """Pin D-02, D-04, D-07, D-08, D-10, D-11 at the integration level."""

    def test_carry_forward_composes_once_not_per_attempt(self, tmp_path: Path) -> None:
        """D-07 / RESEARCH §pitfalls 2: carry-forward applied once before orchestrator.

        The orchestrator MUST receive the carry-forward-augmented result via
        first_attempt; ChatSession's _apply_carry_forward must NOT be invoked
        again for attempt 2 (the orchestrator never sees the carry-forward path).
        """
        history = ChatHistory(path=tmp_path / "h.jsonl")
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        mock_retrieval.retrieve.return_value = _thick_result()

        spy_calls: list[tuple[str, RetrievalResult | None]] = []

        class _SpyOrch:
            def run(self, query, *, intent, retrieve_fn, search_strategy,
                    search_terms, first_attempt=None):
                spy_calls.append((query, first_attempt))
                return first_attempt or _thick_result(), IterativeRetrievalTrace(
                    attempts=(), judge_enabled=False,
                )

        spy = _SpyOrch()
        mock_llm = MagicMock()
        mock_llm.classify_intent.return_value = _intent("vault")
        mock_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=mock_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_status=lambda _msg: None,
            on_token=lambda _t: None,
            orchestrator=spy,
        )
        session.process_turn("q")
        assert len(spy_calls) == 1
        assert spy_calls[0][1] is not None  # first_attempt was passed

    def test_visible_status_line_emitted_when_loop_fires(self, tmp_path: Path) -> None:
        """D-02: 'Revisando busca...' on stderr exactly once when loop fires."""
        status_calls: list[str] = []
        history = ChatHistory(path=tmp_path / "h.jsonl")

        # Real orchestrator with FakeLLM scripted to return a different reformulation
        # so the Jaccard guard does not fire and the loop runs both attempts.
        fake_llm = _ChatFakeLLM(
            reformulations=["consulta totalmente diferente refinada"],
        )
        # Retrieval: thin attempt 1, thick attempt 2 (orchestrator drives both)
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        mock_retrieval.retrieve.side_effect = [_thin_result(), _thick_result()]
        mock_retrieval._backend = MagicMock()
        mock_retrieval._backend.fetch.return_value = None  # no carry-forward content
        mock_retrieval._assemble_context = MagicMock(return_value="ctx")

        orch = IterativeRetrievalOrchestrator(
            llm=fake_llm,
            settings_loader=lambda: RuntimeSettings(),  # iterative enabled by default
            on_status=status_calls.append,
        )
        # ChatSession's classify_intent + chat_turn are still on the LLM —
        # use a separate MagicMock for the chat-session llm slot
        chat_llm = MagicMock()
        chat_llm.classify_intent.return_value = _intent("vault")
        chat_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=chat_llm,
            settings_loader=lambda: RuntimeSettings(),
            on_status=status_calls.append,
            on_token=lambda _t: None,
            orchestrator=orch,
        )
        session.process_turn("q")
        # Revisando busca... must appear exactly once (D-02)
        assert status_calls.count("Revisando busca...") == 1

    def test_reformulation_persisted_to_history(self, tmp_path: Path) -> None:
        """D-10 (integration): [reformulation] entry in JSONL after thin->thick."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        fake_llm = _ChatFakeLLM(
            reformulations=["consulta totalmente diferente refinada"],
        )
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        mock_retrieval.retrieve.side_effect = [_thin_result(), _thick_result()]
        mock_retrieval._backend = MagicMock()
        mock_retrieval._backend.fetch.return_value = None
        mock_retrieval._assemble_context = MagicMock(return_value="ctx")

        orch = IterativeRetrievalOrchestrator(
            llm=fake_llm,
            settings_loader=lambda: RuntimeSettings(),
            on_status=lambda _msg: None,
        )
        chat_llm = MagicMock()
        chat_llm.classify_intent.return_value = _intent("vault")
        chat_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=chat_llm,
            settings_loader=lambda: RuntimeSettings(),
            on_status=lambda _msg: None,
            on_token=lambda _t: None,
            orchestrator=orch,
        )
        session.process_turn("q")

        records = history.load()
        assert any(
            r["role"] == "system" and r["content"].startswith("[reformulation] ")
            for r in records
        )

    def test_get_recent_excludes_reformulations_after_loop(self, tmp_path: Path) -> None:
        """D-10 (integration smoke): get_recent never returns reformulation entries
        after the loop has actually persisted them through the real ChatSession path."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        fake_llm = _ChatFakeLLM(
            reformulations=["consulta totalmente diferente refinada"],
        )
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        mock_retrieval.retrieve.side_effect = [_thin_result(), _thick_result()]
        mock_retrieval._backend = MagicMock()
        mock_retrieval._backend.fetch.return_value = None
        mock_retrieval._assemble_context = MagicMock(return_value="ctx")

        orch = IterativeRetrievalOrchestrator(
            llm=fake_llm,
            settings_loader=lambda: RuntimeSettings(),
            on_status=lambda _msg: None,
        )
        chat_llm = MagicMock()
        chat_llm.classify_intent.return_value = _intent("vault")
        chat_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=chat_llm,
            settings_loader=lambda: RuntimeSettings(),
            on_status=lambda _msg: None,
            on_token=lambda _t: None,
            orchestrator=orch,
        )
        session.process_turn("q")
        recent = history.get_recent(max_turns=10)
        assert all(
            not (m["role"] == "system" and m["content"].startswith("[reformulation] "))
            for m in recent
        )

    def test_disable_path_byte_equivalent(self, tmp_path: Path) -> None:
        """D-11 + RESEARCH §6: byte-equivalent to single-shot when disabled.

        Zero LLM rescue calls, zero [reformulation] history entries, single retrieve call.
        """
        history = ChatHistory(path=tmp_path / "h.jsonl")
        fake_llm = _ChatFakeLLM()  # No scripted responses -> AssertionError on any call
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        # Even a thin result does NOT trigger the loop in disabled mode
        mock_retrieval.retrieve.return_value = _thin_result()

        orch = IterativeRetrievalOrchestrator(
            llm=fake_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_status=lambda _msg: None,
        )
        chat_llm = MagicMock()
        chat_llm.classify_intent.return_value = _intent("vault")
        chat_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=chat_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_status=lambda _msg: None,
            on_token=lambda _t: None,
            orchestrator=orch,
        )
        session.process_turn("q")

        # Single retrieval call (no rescue retry), no reformulation/judge LLM calls
        assert mock_retrieval.retrieve.call_count == 1
        assert fake_llm.reformulate_calls == []
        assert fake_llm.judge_calls == []
        recs = history.load()
        assert all(
            not (r["role"] == "system" and r["content"].startswith("[reformulation] "))
            for r in recs
        )

    def test_last_trace_consumer_invoked_with_trace(self, tmp_path: Path) -> None:
        """trace consumer (set by CLI for --trace) receives the orchestrator's trace."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        mock_retrieval.retrieve.return_value = _thick_result()

        captured: list[IterativeRetrievalTrace] = []

        chat_llm = MagicMock()
        chat_llm.classify_intent.return_value = _intent("vault")
        chat_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=chat_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_status=lambda _msg: None,
            on_token=lambda _t: None,
            last_trace_consumer=captured.append,
        )
        session.process_turn("q")
        assert len(captured) == 1
        assert isinstance(captured[0], IterativeRetrievalTrace)
        # Disabled mode -> exactly one attempt with disabled exit reason
        assert len(captured[0].attempts) == 1
        assert captured[0].early_exit_reason == "disabled"

    def test_carry_forward_origin_tagged_carry(self, tmp_path: Path) -> None:
        """RESEARCH §2 + D-07: carry-forward supplements MUST be tagged origin='carry'.

        Wave 1 left them defaulting to 'hybrid' which broke the sufficiency
        primitive's hybrid-only top-score check. This pins the explicit tag.
        """
        history = ChatHistory(path=tmp_path / "h.jsonl")
        mock_retrieval = MagicMock()
        mock_retrieval._memory_backend = None
        mock_retrieval._backend = MagicMock()
        mock_retrieval._backend.fetch.return_value = "carry content"
        mock_retrieval._assemble_context = MagicMock(return_value="ctx")

        chat_llm = MagicMock()
        chat_llm.classify_intent.return_value = _intent("vault")
        chat_llm.chat_turn.return_value = "ans"

        session = ChatSession(
            history=history, retrieval=mock_retrieval,
            llm=chat_llm,
            settings_loader=_disabled_iterative_settings_loader,
            on_status=lambda _msg: None,
            on_token=lambda _t: None,
        )
        # Seed carry-forward state with a path
        session._last_retrieved_paths = ["notas/seed.md"]
        # Fresh retrieval returns a different note (so seed becomes a supplement)
        fresh = RetrievalResult(
            ok=True,
            notes=(
                RetrievedNote(
                    path="notas/fresh.md", score=0.9, content="x" * 800,
                    source="vault", origin="hybrid",
                ),
            ),
            context_text="ctx", insufficient_evidence=False,
        )
        result = session._apply_carry_forward(fresh)
        carry_notes = [n for n in result.notes if n.origin == "carry"]
        assert len(carry_notes) == 1
        assert carry_notes[0].path == "notas/seed.md"
