"""Unit tests for aurora chat CLI command."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app


runner = CliRunner()


class TestChatCommandHelp:
    """Tests for --help output."""

    def test_chat_help_shows_command_description(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "Aurora Chat" in result.output or "conversa" in result.output.lower() or "chat" in result.output.lower()

    def test_chat_help_shows_clear_option(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--clear" in result.output


class TestChatCommandWelcome:
    """Tests for welcome message and interactive loop."""

    def test_chat_prints_welcome_message(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=EOFError):
                result = runner.invoke(app, ["chat"])
        assert "Aurora Chat" in result.output

    def test_chat_prints_exit_instruction(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=EOFError):
                result = runner.invoke(app, ["chat"])
        assert "sair" in result.output


class TestChatCommandInputRouting:
    """Tests for user input routing to ChatSession."""

    def test_chat_passes_input_to_process_turn(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["olá mundo", EOFError]):
                result = runner.invoke(app, ["chat"])
        mock_session.process_turn.assert_called_once_with("olá mundo")

    def test_chat_skips_empty_input(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["", "  ", EOFError]):
                result = runner.invoke(app, ["chat"])
        mock_session.process_turn.assert_not_called()

    def test_chat_multiple_inputs_all_routed(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["msg1", "msg2", EOFError]):
                result = runner.invoke(app, ["chat"])
        assert mock_session.process_turn.call_count == 2


class TestChatCommandExit:
    """Tests for clean exit behaviors."""

    def test_chat_exits_on_keyboard_interrupt(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "Ate logo" in result.output or "logo" in result.output.lower()

    def test_chat_exits_cleanly_on_sair(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["sair"]):
                result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "Ate logo" in result.output or "logo" in result.output.lower()
        # process_turn should NOT be called for "sair"
        mock_session.process_turn.assert_not_called()

    def test_chat_exits_cleanly_on_exit(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["exit"]):
                result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0

    def test_chat_exits_cleanly_on_quit(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["quit"]):
                result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0

    def test_chat_exits_on_eof(self) -> None:
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=EOFError):
                result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0


class TestChatCommandClear:
    """Tests for --clear flag."""

    def test_chat_clear_clears_history(self) -> None:
        with patch("aurora.cli.chat.ChatHistory") as mock_cls:
            mock_history = MagicMock()
            mock_cls.return_value = mock_history
            result = runner.invoke(app, ["chat", "--clear"])
        mock_history.clear.assert_called_once()

    def test_chat_clear_prints_confirmation_in_pt_br(self) -> None:
        with patch("aurora.cli.chat.ChatHistory") as mock_cls:
            mock_history = MagicMock()
            mock_cls.return_value = mock_history
            result = runner.invoke(app, ["chat", "--clear"])
        assert result.exit_code == 0
        # Should print confirmation in pt-BR
        output_lower = result.output.lower()
        assert "historico" in output_lower or "history" in output_lower or "limpo" in output_lower or "clear" in output_lower

    def test_chat_clear_does_not_start_session(self) -> None:
        with patch("aurora.cli.chat.ChatHistory"):
            with patch("aurora.cli.chat.ChatSession") as mock_session_cls:
                result = runner.invoke(app, ["chat", "--clear"])
        mock_session_cls.assert_not_called()


class TestChatAppRegistration:
    """Tests for chat_app registration in app.py."""

    def test_chat_registered_in_app(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "chat" in result.output

    def test_aurora_chat_help_accessible(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Phase 7 Plan 03: --trace flag + PRIV-03 leak tests
# ---------------------------------------------------------------------------

_SECRET_CHAT = "SECRET_TOKEN_DO_NOT_LEAK_42"


class TestChatTrace:
    """--trace flag wires last_trace_consumer; PRIV-03 leak guards."""

    def test_chat_help_shows_trace_option(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--trace" in result.output

    def test_trace_flag_passes_consumer_to_session(self) -> None:
        """When --trace is set, ChatSession is constructed with a non-None last_trace_consumer."""
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=EOFError):
                runner.invoke(app, ["chat", "--trace"])
        # ChatSession should be called with last_trace_consumer=<callable>
        kwargs = mock_cls.call_args.kwargs
        assert "last_trace_consumer" in kwargs
        assert kwargs["last_trace_consumer"] is not None
        assert callable(kwargs["last_trace_consumer"])

    def test_no_trace_flag_passes_none_consumer(self) -> None:
        """Default (no --trace) -> last_trace_consumer is None (no overhead)."""
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=EOFError):
                runner.invoke(app, ["chat"])
        kwargs = mock_cls.call_args.kwargs
        # Either omitted entirely or explicitly None
        assert kwargs.get("last_trace_consumer") is None

    def test_trace_renders_per_turn_to_stderr(self) -> None:
        """After process_turn, the captured trace renders to stderr via render_trace_text."""
        from aurora.retrieval.contracts import AttemptTrace, IterativeRetrievalTrace

        captured_consumer: list = []

        def _fake_process_turn(msg, _captured=captured_consumer):
            # Simulate the orchestrator calling the trace consumer
            trace = IterativeRetrievalTrace(
                attempts=(
                    AttemptTrace(
                        attempt_number=1, query=msg, intent="vault",
                        hit_count=2, top_score=0.9, sufficient=True,
                        reason="", paths=("notas/x.md", "notas/y.md"),
                    ),
                ),
                judge_enabled=False, early_exit_reason="",
            )
            _captured[0](trace)
            return "resposta"

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_session.process_turn.side_effect = _fake_process_turn

            def _capture(**kwargs):
                captured_consumer.append(kwargs.get("last_trace_consumer"))
                return mock_session

            mock_cls.side_effect = _capture
            with patch("builtins.input", side_effect=["pergunta", EOFError]):
                result = runner.invoke(app, ["chat", "--trace"])

        assert result.exit_code == 0
        assert "retrieval trace" in (result.stderr or "")
        assert "notas/x.md" in (result.stderr or "")

    def test_trace_does_not_leak_note_content_in_stderr(self) -> None:
        """PRIV-03: SECRET in fake retrieval cannot reach stderr via --trace.

        The trace surface (AttemptTrace) is structurally content-free — only
        paths/scores/counts/queries/reasons. Even if a maintainer mistakenly
        injects SECRET into a path or query, it must NOT come from note.content.
        Here we simulate a trace with paths/queries only — SECRET is in note
        content (which is never rendered by trace_render).
        """
        from aurora.retrieval.contracts import AttemptTrace, IterativeRetrievalTrace

        captured_consumer: list = []

        # The trace contains ONLY safe fields (no SECRET). The SECRET would only
        # leak if trace_render reached into RetrievedNote.content — which it
        # cannot, because AttemptTrace doesn't carry content fields.
        safe_trace = IterativeRetrievalTrace(
            attempts=(
                AttemptTrace(
                    attempt_number=1, query="pergunta", intent="vault",
                    hit_count=1, top_score=0.5, sufficient=True,
                    reason="", paths=("notas/secret-bearer.md",),
                ),
            ),
            judge_enabled=False, early_exit_reason="",
        )

        def _fake_process_turn(msg, _captured=captured_consumer):
            _captured[0](safe_trace)
            return f"resposta (SECRET stayed in content: {_SECRET_CHAT})"
            # NOTE: we ALSO put SECRET in the response just to prove it doesn't
            # bleed into stderr via the trace renderer.

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_session.process_turn.side_effect = _fake_process_turn

            def _capture(**kwargs):
                captured_consumer.append(kwargs.get("last_trace_consumer"))
                return mock_session

            mock_cls.side_effect = _capture
            with patch("builtins.input", side_effect=["pergunta", EOFError]):
                result = runner.invoke(app, ["chat", "--trace"])

        assert result.exit_code == 0
        # SECRET must not leak via the trace renderer to stderr
        assert _SECRET_CHAT not in (result.stderr or ""), (
            "PRIV-03 violation: secret leaked to stderr via --trace"
        )

    def test_trace_omitted_without_flag(self) -> None:
        """Without --trace, no 'retrieval trace' string appears anywhere."""
        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.turn_count = 0
            mock_session.process_turn.return_value = "resposta"
            mock_cls.return_value = mock_session
            with patch("builtins.input", side_effect=["pergunta", EOFError]):
                result = runner.invoke(app, ["chat"])
        assert "retrieval trace" not in (result.stderr or "")
        assert "retrieval trace" not in (result.stdout or "")
