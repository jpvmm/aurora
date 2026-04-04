"""Unit tests for aurora chat CLI memory background save behavior."""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app


runner = CliRunner()


def _make_mock_session(turn_count: int = 2, session_turns: list | None = None) -> MagicMock:
    """Create a mock ChatSession with configurable turn_count."""
    mock_session = MagicMock()
    mock_session.turn_count = turn_count
    mock_session.get_session_turns.return_value = session_turns or [
        {"role": "user", "content": "pergunta"},
        {"role": "assistant", "content": "resposta"},
    ]
    mock_session.llm = MagicMock()
    return mock_session


class TestChatCommandMemorySave:
    """Tests for background memory save on chat exit."""

    def test_background_thread_spawned_when_turn_count_ge_2(self) -> None:
        """Per D-11: spawn background thread when turn_count >= 2 on exit."""
        mock_session = _make_mock_session(turn_count=2)

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_cls.return_value = mock_session
            with patch("aurora.cli.chat.threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                with patch("builtins.input", side_effect=["sair"]):
                    result = runner.invoke(app, ["chat"])

        assert result.exit_code == 0
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    def test_background_thread_is_daemon_true(self) -> None:
        """Per D-12: daemon=True so user exits immediately."""
        mock_session = _make_mock_session(turn_count=2)

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_cls.return_value = mock_session
            with patch("aurora.cli.chat.threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                with patch("builtins.input", side_effect=["sair"]):
                    runner.invoke(app, ["chat"])

        call_kwargs = mock_thread_cls.call_args[1]
        assert call_kwargs.get("daemon") is True

    def test_no_thread_when_turn_count_less_than_2(self) -> None:
        """Per D-11: no memory created for sessions with fewer than 2 turns."""
        mock_session = _make_mock_session(turn_count=1)

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_cls.return_value = mock_session
            with patch("aurora.cli.chat.threading.Thread") as mock_thread_cls:
                with patch("builtins.input", side_effect=["sair"]):
                    runner.invoke(app, ["chat"])

        mock_thread_cls.assert_not_called()

    def test_no_thread_when_turn_count_zero(self) -> None:
        mock_session = _make_mock_session(turn_count=0)

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_cls.return_value = mock_session
            with patch("aurora.cli.chat.threading.Thread") as mock_thread_cls:
                with patch("builtins.input", side_effect=EOFError):
                    runner.invoke(app, ["chat"])

        mock_thread_cls.assert_not_called()

    def test_background_thread_spawned_on_keyboard_interrupt(self) -> None:
        """Background save should also occur on Ctrl+C exit."""
        mock_session = _make_mock_session(turn_count=3)

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_cls.return_value = mock_session
            with patch("aurora.cli.chat.threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                with patch("builtins.input", side_effect=KeyboardInterrupt):
                    runner.invoke(app, ["chat"])

        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    def test_thread_target_is_background_save(self) -> None:
        """Thread target should be _background_save function."""
        from aurora.cli.chat import _background_save

        mock_session = _make_mock_session(turn_count=2)

        with patch("aurora.cli.chat.ChatSession") as mock_cls:
            mock_cls.return_value = mock_session
            with patch("aurora.cli.chat.threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread
                with patch("builtins.input", side_effect=["sair"]):
                    runner.invoke(app, ["chat"])

        call_kwargs = mock_thread_cls.call_args[1]
        assert call_kwargs.get("target") is _background_save


class TestBackgroundSaveFunction:
    """Tests for _background_save helper function."""

    def test_background_save_calls_summarizer(self) -> None:
        from aurora.cli.chat import _background_save

        mock_llm = MagicMock()
        mock_store = MagicMock()

        with patch("aurora.cli.chat.MemorySummarizer") as mock_summarizer_cls:
            mock_summarizer = MagicMock()
            mock_summarizer_cls.return_value = mock_summarizer
            turns = [{"role": "user", "content": "msg"}]
            _background_save(turns, mock_llm, mock_store, turn_count=2)

        mock_summarizer_cls.assert_called_once_with(llm=mock_llm, store=mock_store)
        mock_summarizer.summarize_and_save.assert_called_once_with(
            history_turns=turns, turn_count=2
        )

    def test_background_save_catches_exceptions_silently(self) -> None:
        """Per D-23: background failures are logged, never raised."""
        from aurora.cli.chat import _background_save

        mock_llm = MagicMock()
        mock_store = MagicMock()

        with patch("aurora.cli.chat.MemorySummarizer") as mock_summarizer_cls:
            mock_summarizer_cls.side_effect = RuntimeError("simulated failure")
            # Should NOT raise
            _background_save([], mock_llm, mock_store, turn_count=2)

    def test_background_save_logs_warning_on_exception(self) -> None:
        """Per D-23: exceptions are logged as warning, not raised."""
        from aurora.cli.chat import _background_save

        mock_llm = MagicMock()
        mock_store = MagicMock()

        with patch("aurora.cli.chat.MemorySummarizer") as mock_summarizer_cls:
            mock_summarizer_cls.side_effect = RuntimeError("simulated failure")
            with patch("aurora.cli.chat.logger") as mock_logger:
                _background_save([], mock_llm, mock_store, turn_count=2)
                mock_logger.warning.assert_called_once()
