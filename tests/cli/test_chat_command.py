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
