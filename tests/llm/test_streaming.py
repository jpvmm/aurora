"""Tests for SSE streaming parser for llama.cpp /v1/chat/completions."""
from __future__ import annotations

import io
import json
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from aurora.llm.streaming import STREAM_TIMEOUT_SECONDS, chat_completion_sync, stream_chat_completions


def _sse_line(content: str) -> bytes:
    """Build a Server-Sent Events data line with a chat completion chunk."""
    chunk = {"choices": [{"delta": {"content": content}}]}
    return f"data: {json.dumps(chunk)}\n".encode("utf-8")


def _sse_done() -> bytes:
    return b"data: [DONE]\n"


def _sse_empty() -> bytes:
    return b"\n"


def _sse_non_data() -> bytes:
    return b"event: heartbeat\n"


def _make_urlopen(lines: list[bytes]):
    """Create a mock urlopen context manager that yields the given byte lines."""
    response = MagicMock()
    response.__iter__ = MagicMock(return_value=iter(lines))
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)

    def _urlopen(request, timeout=None):
        return response

    return _urlopen


# ---------------------------------------------------------------------------
# stream_chat_completions tests
# ---------------------------------------------------------------------------


def test_stream_yields_tokens_from_sse_lines():
    """stream_chat_completions must yield tokens from SSE data lines."""
    lines = [_sse_line("Hello"), _sse_line(" world"), _sse_done()]
    tokens: list[str] = []

    result = stream_chat_completions(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[{"role": "user", "content": "hi"}],
        on_token=tokens.append,
        urlopen_fn=_make_urlopen(lines),
    )

    assert tokens == ["Hello", " world"]
    assert result == "Hello world"


def test_stream_handles_done_sentinel():
    """stream_chat_completions must stop processing after [DONE] sentinel."""
    # Lines after [DONE] should be ignored
    lines = [_sse_line("tok"), _sse_done(), _sse_line("ignored")]
    tokens: list[str] = []

    stream_chat_completions(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[{"role": "user", "content": "hi"}],
        on_token=tokens.append,
        urlopen_fn=_make_urlopen(lines),
    )

    assert tokens == ["tok"]


def test_stream_skips_empty_lines():
    """stream_chat_completions must skip blank lines."""
    lines = [_sse_empty(), _sse_line("token"), _sse_done()]
    tokens: list[str] = []

    stream_chat_completions(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[{"role": "user", "content": "hi"}],
        on_token=tokens.append,
        urlopen_fn=_make_urlopen(lines),
    )

    assert tokens == ["token"]


def test_stream_skips_non_data_lines():
    """stream_chat_completions must skip non-data: SSE lines."""
    lines = [_sse_non_data(), _sse_line("tok"), _sse_done()]
    tokens: list[str] = []

    stream_chat_completions(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[{"role": "user", "content": "hi"}],
        on_token=tokens.append,
        urlopen_fn=_make_urlopen(lines),
    )

    assert tokens == ["tok"]


def test_stream_uses_120_second_timeout():
    """stream_chat_completions must use 120s timeout (separate from 3s health probe)."""
    assert STREAM_TIMEOUT_SECONDS == 120

    captured_timeout = []

    def _urlopen(request, timeout=None):
        captured_timeout.append(timeout)
        response = MagicMock()
        response.__iter__ = MagicMock(return_value=iter([_sse_done()]))
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response

    stream_chat_completions(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[],
        on_token=lambda t: None,
        urlopen_fn=_urlopen,
    )

    assert captured_timeout[0] == 120


def test_stream_posts_to_chat_completions_endpoint():
    """stream_chat_completions must call /v1/chat/completions endpoint."""
    captured_url = []

    def _urlopen(request, timeout=None):
        captured_url.append(request.full_url)
        response = MagicMock()
        response.__iter__ = MagicMock(return_value=iter([_sse_done()]))
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response

    stream_chat_completions(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[],
        on_token=lambda t: None,
        urlopen_fn=_urlopen,
    )

    assert captured_url[0].endswith("/v1/chat/completions")


# ---------------------------------------------------------------------------
# chat_completion_sync tests
# ---------------------------------------------------------------------------


def _sync_response(content: str) -> MagicMock:
    """Create a mock response for a non-streaming chat completion."""
    payload = {"choices": [{"message": {"content": content}}]}
    raw = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = raw
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_sync_returns_stripped_content():
    """chat_completion_sync must return stripped message content."""
    response = _sync_response("  vault  ")

    def _urlopen(request, timeout=None):
        return response

    result = chat_completion_sync(
        endpoint_url="http://127.0.0.1:8080",
        model_id="test-model",
        messages=[{"role": "user", "content": "classify this"}],
        urlopen_fn=_urlopen,
    )

    assert result == "vault"
