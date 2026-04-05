"""Tests for aurora ask CLI command — grounded Q&A pipeline."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.llm.prompts import INSUFFICIENT_EVIDENCE_MSG
from aurora.retrieval.contracts import RetrievalResult, RetrievedNote

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOTE_A = RetrievedNote(path="notas/projeto-x.md", score=0.92, content="Projeto X e sobre...", source="vault")
_NOTE_B = RetrievedNote(path="notas/contexto.md", score=0.85, content="Contexto adicional...", source="vault")
_NOTE_MEM = RetrievedNote(path="memory/2024-01.md", score=0.80, content="Conversa anterior...", source="memory")

_GOOD_RESULT = RetrievalResult(
    ok=True,
    notes=(_NOTE_A, _NOTE_B),
    context_text="--- notas/projeto-x.md ---\nProjeto X e sobre...\n",
    insufficient_evidence=False,
)

_GOOD_RESULT_WITH_MEMORY = RetrievalResult(
    ok=True,
    notes=(_NOTE_MEM, _NOTE_A),
    context_text="--- memory/2024-01.md ---\nConversa anterior...\n--- notas/projeto-x.md ---\nProjeto X e sobre...\n",
    insufficient_evidence=False,
)

_INSUFFICIENT_RESULT = RetrievalResult(
    ok=True,
    notes=(),
    context_text="",
    insufficient_evidence=True,
)

STREAMED_TOKENS = ["O projeto ", "X e sobre ", "algo especial."]
FULL_ANSWER = "O projeto X e sobre algo especial."


def _mock_ask_grounded_streaming(mock_llm_instance: MagicMock) -> None:
    """Configure the mock LLMService to stream tokens and return full answer."""

    def side_effect(query: str, context_text: str, *, on_token):
        for token in STREAMED_TOKENS:
            on_token(token)
        return FULL_ANSWER

    mock_llm_instance.ask_grounded.side_effect = side_effect


# ---------------------------------------------------------------------------
# Test: streaming text output
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_streams_answer_to_stdout(mock_retrieval_cls, mock_llm_cls):
    """aurora ask 'query' streams answer tokens to stdout."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    result = runner.invoke(app, ["ask", "o que e o projeto X"])

    assert result.exit_code == 0
    assert FULL_ANSWER in result.output


# ---------------------------------------------------------------------------
# Test: JSON output mode
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_json_output(mock_retrieval_cls, mock_llm_cls):
    """aurora ask 'query' --json returns structured JSON."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    result = runner.invoke(app, ["ask", "o que e o projeto X", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["query"] == "o que e o projeto X"
    assert data["answer"] == FULL_ANSWER
    assert isinstance(data["sources"], list)
    assert "notas/projeto-x.md" in data["sources"]
    assert data["insufficient_evidence"] is False


# ---------------------------------------------------------------------------
# Test: insufficient evidence — text mode
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_insufficient_evidence_text(mock_retrieval_cls, mock_llm_cls):
    """aurora ask with no evidence prints pt-BR refusal and exits 0."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _INSUFFICIENT_RESULT

    result = runner.invoke(app, ["ask", "algo sem resultado"])

    assert result.exit_code == 0
    assert INSUFFICIENT_EVIDENCE_MSG in result.output
    mock_llm_cls.return_value.ask_grounded.assert_not_called()


# ---------------------------------------------------------------------------
# Test: insufficient evidence — JSON mode
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_insufficient_evidence_json(mock_retrieval_cls, mock_llm_cls):
    """aurora ask --json with insufficient evidence returns JSON with insufficient_evidence=True."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _INSUFFICIENT_RESULT

    result = runner.invoke(app, ["ask", "algo sem resultado", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["insufficient_evidence"] is True
    assert data["sources"] == []
    assert data["answer"] == ""
    mock_llm_cls.return_value.ask_grounded.assert_not_called()


# ---------------------------------------------------------------------------
# Test: always retrieves (no intent routing per D-15)
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_always_calls_retrieve(mock_retrieval_cls, mock_llm_cls):
    """aurora ask calls classify_intent then retrieve_with_memory with strategy."""
    from aurora.llm.service import IntentResult
    mock_llm_cls.return_value.classify_intent.return_value = IntentResult(intent="vault", search="hybrid", terms=[])
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    runner.invoke(app, ["ask", "alguma query"])

    mock_llm_cls.return_value.classify_intent.assert_called_once_with("alguma query")
    mock_retrieval_cls.return_value.retrieve_with_memory.assert_called_once()


# ---------------------------------------------------------------------------
# Test: retrieval context_text passed to LLM
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_passes_context_text_to_llm(mock_retrieval_cls, mock_llm_cls):
    """context_text from retrieval is passed to LLMService for grounded answer."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    runner.invoke(app, ["ask", "minha query"])

    # For vault-only results, ask_grounded is used; verify context_text passed
    call_kwargs = mock_llm_cls.return_value.ask_grounded.call_args
    assert call_kwargs is not None
    # First positional arg is query, second is context_text
    args, kwargs = call_kwargs
    assert _GOOD_RESULT.context_text in args or _GOOD_RESULT.context_text == args[1]


# ---------------------------------------------------------------------------
# Test: streaming uses print with flush=True not typer.echo (Pitfall 7)
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_streaming_uses_print_flush(mock_retrieval_cls, mock_llm_cls):
    """Streaming output uses print(token, end='', flush=True) per Pitfall 7."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    captured_tokens: list[str] = []

    def side_effect(query: str, context_text: str, *, on_token):
        for token in STREAMED_TOKENS:
            on_token(token)
        return FULL_ANSWER

    mock_llm_cls.return_value.ask_grounded.side_effect = side_effect

    # Capture the on_token callable passed to ask_grounded
    received_on_token = None

    def capture_on_token(query: str, context_text: str, *, on_token):
        nonlocal received_on_token
        received_on_token = on_token
        for token in STREAMED_TOKENS:
            on_token(token)
        return FULL_ANSWER

    mock_llm_cls.return_value.ask_grounded.side_effect = capture_on_token

    with patch("builtins.print") as mock_print:
        runner.invoke(app, ["ask", "query"])

    # Verify print was called with end='' and flush=True for tokens
    token_calls = [
        call
        for call in mock_print.call_args_list
        if call.kwargs.get("end") == "" and call.kwargs.get("flush") is True
    ]
    assert len(token_calls) == len(STREAMED_TOKENS)


# ---------------------------------------------------------------------------
# Test: logs retrieved note paths and scores (D-07)
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_logs_note_paths_and_scores(mock_retrieval_cls, mock_llm_cls, caplog):
    """ask command logs retrieved note paths and scores at DEBUG (D-07), not content."""
    import logging

    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    with caplog.at_level(logging.DEBUG, logger="aurora.cli.ask"):
        runner.invoke(app, ["ask", "query"])

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("notas/projeto-x.md" in msg for msg in debug_msgs)
    assert any("0.92" in msg for msg in debug_msgs)
    # Content must NOT be logged
    assert not any("Projeto X e sobre..." in msg for msg in debug_msgs)


# ---------------------------------------------------------------------------
# Test: command registered in app.py as `aurora ask`
# ---------------------------------------------------------------------------


def test_ask_command_registered_in_app():
    """ask command is accessible as `aurora ask`."""
    result = runner.invoke(app, ["ask", "--help"])
    # Should show help, not a "no such command" error
    assert result.exit_code == 0 or "vault" in result.output.lower()


# ---------------------------------------------------------------------------
# New tests: dual-source ask upgrade (Task 2)
# ---------------------------------------------------------------------------


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_uses_retrieve_with_memory_not_retrieve(mock_retrieval_cls, mock_llm_cls):
    """aurora ask must call retrieve_with_memory(), NOT retrieve()."""
    from aurora.llm.service import IntentResult
    mock_llm_cls.return_value.classify_intent.return_value = IntentResult(intent="vault", search="hybrid", terms=[])
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    runner.invoke(app, ["ask", "alguma query"])

    mock_retrieval_cls.return_value.retrieve_with_memory.assert_called_once()
    mock_retrieval_cls.return_value.retrieve.assert_not_called()


@patch("aurora.cli.ask.QMDSearchBackend")
@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_creates_memory_backend(mock_retrieval_cls, mock_llm_cls, mock_qmd_cls):
    """aurora ask must instantiate QMDSearchBackend with MEMORY_INDEX and MEMORY_COLLECTION."""
    from aurora.memory.store import MEMORY_COLLECTION, MEMORY_INDEX

    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    runner.invoke(app, ["ask", "alguma query"])

    mock_qmd_cls.assert_called_once_with(
        index_name=MEMORY_INDEX,
        collection_name=MEMORY_COLLECTION,
    )


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_status_message_mentions_memorias(mock_retrieval_cls, mock_llm_cls):
    """aurora ask status message must mention 'memorias' (not just 'vault')."""
    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
    _mock_ask_grounded_streaming(mock_llm_cls.return_value)

    result = runner.invoke(app, ["ask", "pergunta"])

    assert "memorias" in result.output.lower() or "memorias" in (result.stderr or "").lower()


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_json_includes_memory_sources(mock_retrieval_cls, mock_llm_cls):
    """ask --json output must include memory sources when memory notes present."""

    def _chat_turn_side_effect(messages, *, on_token):
        return "Resposta com memoria."

    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT_WITH_MEMORY
    mock_llm_cls.return_value.chat_turn.side_effect = _chat_turn_side_effect

    result = runner.invoke(app, ["ask", "o que conversamos", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "memory/2024-01.md" in data["sources"]


@patch("aurora.cli.ask.LLMService")
@patch("aurora.cli.ask.RetrievalService")
def test_ask_uses_chat_turn_when_memory_notes_present(mock_retrieval_cls, mock_llm_cls):
    """aurora ask must use LLMService.chat_turn (not ask_grounded) when memory notes present."""

    def _chat_turn_side_effect(messages, *, on_token):
        return "Resposta com memoria."

    mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT_WITH_MEMORY
    mock_llm_cls.return_value.chat_turn.side_effect = _chat_turn_side_effect

    runner.invoke(app, ["ask", "o que conversamos"])

    mock_llm_cls.return_value.chat_turn.assert_called_once()
    mock_llm_cls.return_value.ask_grounded.assert_not_called()
