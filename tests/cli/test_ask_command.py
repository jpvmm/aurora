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


@pytest.fixture(autouse=True)
def _disable_iterative_loop_in_existing_tests(request):
    """Pin existing aurora ask tests to disable-path orchestrator behavior.

    Phase 7 wires IterativeRetrievalOrchestrator into aurora ask. Existing
    tests pre-date the loop and don't script reformulate_query / judge_sufficiency
    on the mocked LLMService. Patch the orchestrator class so it acts as a
    pass-through that just calls retrieve_fn once and emits a one-attempt trace.

    Tests that EXPLICITLY exercise the loop (TestAskTrace) opt out via the
    `loop_enabled` marker.
    """
    if request.node.get_closest_marker("loop_enabled"):
        yield
        return

    from aurora.retrieval.contracts import AttemptTrace, IterativeRetrievalTrace

    class _PassThroughOrch:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, query, *, intent, retrieve_fn, search_strategy,
                search_terms, first_attempt=None):
            result = first_attempt if first_attempt is not None else retrieve_fn(
                query, search_strategy=search_strategy, search_terms=search_terms,
            )
            trace = IterativeRetrievalTrace(
                attempts=(
                    AttemptTrace(
                        attempt_number=1, query=query, intent=intent,
                        hit_count=len(result.notes),
                        top_score=max(
                            (n.score for n in result.notes if n.origin == "hybrid"),
                            default=0.0,
                        ),
                        sufficient=True, reason="",
                        paths=tuple(n.path for n in result.notes),
                    ),
                ),
                judge_enabled=False,
                early_exit_reason="disabled",
            )
            return result, trace

    with patch("aurora.cli.ask.IterativeRetrievalOrchestrator", _PassThroughOrch):
        yield


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


# ---------------------------------------------------------------------------
# Phase 7 Plan 03: --trace flag, status line, PRIV-03 leak tests
# ---------------------------------------------------------------------------

_SECRET = "SECRET_TOKEN_DO_NOT_LEAK_42"


def _result_with_secret_in_content() -> RetrievalResult:
    """Retrieval result whose note content embeds a SECRET token.

    Used to prove that --trace rendering NEVER leaks note content to either
    stderr (text mode) or stdout JSON envelope (--json mode). The trace
    surface is paths/scores/counts/queries only by construction (PRIV-03).
    """
    note = RetrievedNote(
        path="notas/secret-bearer.md",
        score=0.92,
        content=f"some prefix {_SECRET} some suffix " * 20,
        source="vault",
        origin="hybrid",
    )
    return RetrievalResult(
        ok=True,
        notes=(note,),
        # Even the context_text contains the SECRET — the trace must NOT pull from it
        context_text=f"--- notas/secret-bearer.md ---\n{_SECRET}\n",
        insufficient_evidence=False,
    )


class TestAskTrace:
    """--trace flag rendering, status line, PRIV-03 leak guards."""

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_text_does_not_appear_without_flag(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """No --trace flag -> 'retrieval trace' string never appears in stderr."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
        _mock_ask_grounded_streaming(mock_llm_cls.return_value)

        result = runner.invoke(app, ["ask", "pergunta"])
        assert result.exit_code == 0
        assert "retrieval trace" not in (result.stderr or "")

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_text_appears_with_flag_text_mode(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """--trace (text mode) emits trace summary to stderr."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
        _mock_ask_grounded_streaming(mock_llm_cls.return_value)

        result = runner.invoke(app, ["ask", "pergunta", "--trace"])
        assert result.exit_code == 0
        assert "retrieval trace" in (result.stderr or "")

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_key_present_in_json_envelope_with_flag(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """--trace --json adds a `trace` key to the JSON envelope."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
        _mock_ask_grounded_streaming(mock_llm_cls.return_value)

        result = runner.invoke(app, ["ask", "pergunta", "--json", "--trace"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "trace" in data
        assert "attempts" in data["trace"]
        assert isinstance(data["trace"]["attempts"], list)

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_key_absent_in_json_envelope_without_flag(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """--json without --trace preserves today's envelope shape (no trace key)."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _GOOD_RESULT
        _mock_ask_grounded_streaming(mock_llm_cls.return_value)

        result = runner.invoke(app, ["ask", "pergunta", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "trace" not in data

    @pytest.mark.loop_enabled
    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_status_line_emitted_on_loop_fire(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """When the loop fires (thin->thick), 'Revisando busca...' appears in stderr.

        Marked loop_enabled to opt out of the autouse pass-through orchestrator.
        Uses real IterativeRetrievalOrchestrator + mocked LLMService where
        reformulate_query is scripted to return a totally different query so
        the diversity guard does not exit early.
        """
        from aurora.llm.service import IntentResult

        # Thin attempt 1, thick attempt 2
        thin = RetrievalResult(
            ok=True,
            notes=(RetrievedNote(
                path="notas/weak.md", score=0.18, content="x" * 50,
                source="vault", origin="hybrid",
            ),),
            context_text="--- notas/weak.md ---\n" + ("x" * 50),
            insufficient_evidence=False,
        )
        thick = RetrievalResult(
            ok=True,
            notes=tuple(
                RetrievedNote(
                    path=f"notas/strong_{i}.md", score=0.85 - i * 0.05,
                    content="conteudo substantivo " * 80,
                    source="vault", origin="hybrid",
                )
                for i in range(3)
            ),
            context_text="--- ctx ---\n" + ("c" * 1500),
            insufficient_evidence=False,
        )
        mock_retrieval_cls.return_value.retrieve_with_memory.side_effect = [thin, thick]
        mock_llm_cls.return_value.classify_intent.return_value = IntentResult(
            intent="vault", search="hybrid", terms=[],
        )
        mock_llm_cls.return_value.reformulate_query.return_value = (
            "consulta totalmente diferente refinada"
        )

        def _ask_grounded(query, ctx, *, on_token):
            on_token("ok")
            return "ok"

        mock_llm_cls.return_value.ask_grounded.side_effect = _ask_grounded

        result = runner.invoke(app, ["ask", "pergunta vaga"])
        assert result.exit_code == 0
        assert "Revisando busca..." in (result.stderr or "")

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_does_not_leak_note_content_in_stderr(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """PRIV-03: SECRET in note.content never appears on stderr under --trace."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = (
            _result_with_secret_in_content()
        )
        _mock_ask_grounded_streaming(mock_llm_cls.return_value)

        result = runner.invoke(app, ["ask", "pergunta", "--trace"])
        assert result.exit_code == 0
        assert _SECRET not in (result.stderr or ""), (
            "PRIV-03 violation: secret leaked to stderr via --trace"
        )

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_does_not_leak_note_content_in_json_envelope(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """PRIV-03: SECRET in note.content never appears on stdout/stderr under --trace --json.

        Closes the JSON-envelope smuggle path — render_trace_json operates only
        on AttemptTrace fields (paths/scores/counts/queries/reasons) which are
        structurally content-free (pinned by Wave 1 _FORBIDDEN_TRACE_FIELDS).
        """
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = (
            _result_with_secret_in_content()
        )
        _mock_ask_grounded_streaming(mock_llm_cls.return_value)

        result = runner.invoke(app, ["ask", "pergunta", "--trace", "--json"])
        assert result.exit_code == 0
        assert _SECRET not in (result.stdout or ""), (
            "PRIV-03 violation: secret leaked to stdout JSON envelope via --trace"
        )
        assert _SECRET not in (result.stderr or ""), (
            "PRIV-03 violation: secret leaked to stderr via --trace --json"
        )

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_emitted_on_insufficient_evidence_path_text_mode(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """NIT 2 / symmetry: --trace shows the trace even on insufficient_evidence path (text mode)."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _INSUFFICIENT_RESULT

        result = runner.invoke(app, ["ask", "pergunta sem evidencia", "--trace"])
        assert result.exit_code == 0
        # Insufficient message goes to stdout
        assert INSUFFICIENT_EVIDENCE_MSG in (result.stdout or "")
        # Trace must STILL appear on stderr (parity with happy path)
        assert "retrieval trace" in (result.stderr or "")

    @patch("aurora.cli.ask.LLMService")
    @patch("aurora.cli.ask.RetrievalService")
    def test_trace_emitted_on_insufficient_evidence_path_json_mode(
        self, mock_retrieval_cls, mock_llm_cls,
    ):
        """NIT 2 / symmetry: --trace --json includes `trace` key on insufficient_evidence path."""
        mock_retrieval_cls.return_value.retrieve_with_memory.return_value = _INSUFFICIENT_RESULT

        result = runner.invoke(app, ["ask", "pergunta sem evidencia", "--trace", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["insufficient_evidence"] is True
        assert "trace" in data
        assert "attempts" in data["trace"]
