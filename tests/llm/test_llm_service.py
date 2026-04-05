"""Tests for LLMService — ask_grounded, chat_turn, and classify_intent."""
from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock

import pytest

from aurora.llm.service import LLMService


def _make_settings(endpoint_url: str = "http://127.0.0.1:8080", model_id: str = "test-model"):
    settings = MagicMock()
    settings.endpoint_url = endpoint_url
    settings.model_id = model_id
    return settings


def _service(
    stream_fn=None,
    sync_fn=None,
    endpoint_url: str = "http://127.0.0.1:8080",
    model_id: str = "test-model",
) -> LLMService:
    return LLMService(
        endpoint_url=endpoint_url,
        model_id=model_id,
        stream_fn=stream_fn,
        sync_fn=sync_fn,
    )


# ---------------------------------------------------------------------------
# ask_grounded() tests
# ---------------------------------------------------------------------------


def test_ask_grounded_builds_messages_with_system_prompt_and_context():
    """ask_grounded() must build messages with system prompt + context + user query."""
    captured_messages = []

    def _stream_fn(*, endpoint_url, model_id, messages, on_token, **kwargs):
        captured_messages.extend(messages)
        on_token("answer")
        return "answer"

    service = _service(stream_fn=_stream_fn)
    result = service.ask_grounded("What is X?", "vault context here", on_token=lambda t: None)

    assert result == "answer"
    assert len(captured_messages) == 2
    assert captured_messages[0]["role"] == "system"
    assert captured_messages[1]["role"] == "user"
    assert "vault context here" in captured_messages[1]["content"]
    assert "What is X?" in captured_messages[1]["content"]


def test_ask_grounded_calls_stream_fn():
    """ask_grounded() must use the streaming function."""
    stream_called = []

    def _stream_fn(*, endpoint_url, model_id, messages, on_token, **kwargs):
        stream_called.append(True)
        return "response text"

    service = _service(stream_fn=_stream_fn)
    service.ask_grounded("query", "context", on_token=lambda t: None)

    assert stream_called == [True]


# ---------------------------------------------------------------------------
# chat_turn() tests
# ---------------------------------------------------------------------------


def test_chat_turn_passes_messages_to_stream_fn():
    """chat_turn() must pass the provided messages directly to stream_fn."""
    captured_messages = []

    def _stream_fn(*, endpoint_url, model_id, messages, on_token, **kwargs):
        captured_messages.extend(messages)
        return "chat response"

    service = _service(stream_fn=_stream_fn)
    test_messages = [
        {"role": "system", "content": "You are Aurora."},
        {"role": "user", "content": "Hello"},
    ]
    result = service.chat_turn(test_messages, on_token=lambda t: None)

    assert result == "chat response"
    assert captured_messages == test_messages


# ---------------------------------------------------------------------------
# classify_intent() tests
# ---------------------------------------------------------------------------


def test_classify_intent_returns_vault_when_response_contains_vault():
    """classify_intent() must return IntentResult with intent='vault'."""
    service = _service(sync_fn=lambda **kwargs: "intent: vault\nsearch: hybrid\nterms: notas")
    result = service.classify_intent("What does my note say?")
    assert result.intent == "vault"


def test_classify_intent_returns_chat_for_non_vault_response():
    """classify_intent() must return intent='chat' for general queries."""
    service = _service(sync_fn=lambda **kwargs: "intent: chat\nsearch: none\nterms: none")
    result = service.classify_intent("How's the weather?")
    assert result.intent == "chat"


def test_classify_intent_returns_memory_when_response_contains_memory():
    """classify_intent() must return intent='memory' for memory queries."""
    service = _service(sync_fn=lambda **kwargs: "intent: memory\nsearch: hybrid\nterms: conversa ontem")
    result = service.classify_intent("o que conversamos ontem?")
    assert result.intent == "memory"


def test_classify_intent_returns_chat_for_garbage_output():
    """classify_intent() must return intent='chat' as fallback for unrecognized output."""
    service = _service(sync_fn=lambda **kwargs: "asdfgh")
    result = service.classify_intent("some question")
    assert result.intent == "chat"


def test_classify_intent_parses_search_strategy():
    """classify_intent() must parse search strategy from structured response."""
    service = _service(sync_fn=lambda **kwargs: "intent: vault\nsearch: keyword\nterms: Rosely")
    result = service.classify_intent("find Rosely")
    assert result.intent == "vault"
    assert result.search == "keyword"
    assert result.terms == ["Rosely"]


def test_classify_intent_parses_both_strategy():
    """classify_intent() must parse 'both' search strategy."""
    service = _service(sync_fn=lambda **kwargs: "intent: vault\nsearch: both\nterms: Rosely, notas mencionei")
    result = service.classify_intent("find notes mentioning Rosely")
    assert result.search == "both"
    assert "Rosely" in result.terms


def test_classify_intent_uses_sync_fn_not_streaming():
    """classify_intent() must call sync_fn, not stream_fn."""
    stream_called = []
    sync_called = []

    def _stream_fn(**kwargs):
        stream_called.append(True)
        return "stream"

    def _sync_fn(**kwargs):
        sync_called.append(True)
        return "intent: chat\nsearch: none\nterms: none"

    service = _service(stream_fn=_stream_fn, sync_fn=_sync_fn)
    service.classify_intent("some message")

    assert stream_called == []
    assert sync_called == [True]


def test_classify_intent_sends_only_latest_message():
    """classify_intent() must send only the single message to classify."""
    captured_messages = []

    def _sync_fn(*, messages, **kwargs):
        captured_messages.extend(messages)
        return "intent: vault\nsearch: hybrid\nterms: notas"

    service = _service(sync_fn=_sync_fn)
    service.classify_intent("What is in my notes?")

    assert len(captured_messages) == 1
    assert captured_messages[0]["role"] == "user"


def test_classify_intent_case_insensitive():
    """classify_intent() must handle uppercase in LLM response."""
    service = _service(sync_fn=lambda **kwargs: "intent: VAULT\nsearch: HYBRID\nterms: test")
    result = service.classify_intent("msg")
    assert result.intent == "vault"


def test_llm_service_resolves_endpoint_from_settings_when_not_provided():
    """LLMService must use settings.endpoint_url when endpoint_url not explicitly provided."""
    settings = _make_settings(endpoint_url="http://127.0.0.1:9999", model_id="my-model")

    captured = {}

    def _stream_fn(*, endpoint_url, model_id, messages, on_token, **kwargs):
        captured["endpoint_url"] = endpoint_url
        captured["model_id"] = model_id
        return "ok"

    service = LLMService(settings_loader=lambda: settings, stream_fn=_stream_fn)
    service.ask_grounded("q", "ctx", on_token=lambda t: None)

    assert captured["endpoint_url"] == "http://127.0.0.1:9999"
    assert captured["model_id"] == "my-model"
