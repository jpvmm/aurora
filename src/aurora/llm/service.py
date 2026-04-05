"""LLMService — grounded Q&A, free chat, and intent classification via llama.cpp."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from aurora.llm.prompts import INTENT_PROMPT, SUMMARIZE_SESSION_PROMPT, get_system_prompt_grounded
from aurora.llm.streaming import chat_completion_sync, stream_chat_completions
from aurora.runtime.settings import RuntimeSettings, load_settings


class LLMService:
    """Generates responses via local llama.cpp using streaming or sync completions."""

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        model_id: str | None = None,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
        stream_fn: Callable | None = None,
        sync_fn: Callable | None = None,
    ) -> None:
        if endpoint_url is None or model_id is None:
            settings = settings_loader()
            self._endpoint_url = endpoint_url if endpoint_url is not None else settings.endpoint_url
            self._model_id = model_id if model_id is not None else settings.model_id
        else:
            self._endpoint_url = endpoint_url
            self._model_id = model_id
        self._stream_fn = stream_fn or stream_chat_completions
        self._sync_fn = sync_fn or chat_completion_sync

    def ask_grounded(
        self,
        query: str,
        context_text: str,
        *,
        on_token: Callable[[str], None],
    ) -> str:
        """Generate a grounded response using vault context.

        Builds message array: [system_prompt_grounded, user(context + query)].
        Streams tokens via on_token callback.
        Returns full response text.
        """
        messages = [
            {"role": "system", "content": get_system_prompt_grounded()},
            {
                "role": "user",
                "content": f"Contexto do vault:\n{context_text}\n\nPergunta: {query}",
            },
        ]
        return self._stream_fn(
            endpoint_url=self._endpoint_url,
            model_id=self._model_id,
            messages=messages,
            on_token=on_token,
        )

    def chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        on_token: Callable[[str], None],
    ) -> str:
        """Stream a chat response using the provided message history.

        System prompt must be included by caller (supports both grounded and free chat).
        Returns full response text.
        """
        return self._stream_fn(
            endpoint_url=self._endpoint_url,
            model_id=self._model_id,
            messages=messages,
            on_token=on_token,
        )

    def summarize_session(self, turns: list[dict[str, str]]) -> str:
        """Generate a compact summary of conversation turns for episodic memory.

        Uses sync (non-streaming) call — no user-facing output needed.
        Returns raw LLM response text (topic line + summary body).
        """
        conversation = "\n".join(
            f"{t['role']}: {t['content']}" for t in turns
        )
        messages = [
            {
                "role": "user",
                "content": SUMMARIZE_SESSION_PROMPT.format(
                    conversation=conversation,
                    date=date.today().isoformat(),
                ),
            },
        ]
        return self._sync_fn(
            endpoint_url=self._endpoint_url,
            model_id=self._model_id,
            messages=messages,
        )

    def classify_intent(self, message: str) -> "IntentResult":
        """Classify user message intent and determine search strategy.

        Returns an IntentResult with intent, search strategy, and search terms.
        The LLM decides the best approach for each query.
        """
        messages = [
            {"role": "user", "content": INTENT_PROMPT.format(message=message)},
        ]
        result = self._sync_fn(
            endpoint_url=self._endpoint_url,
            model_id=self._model_id,
            messages=messages,
        )
        return _parse_intent_result(result)


@dataclass(frozen=True)
class IntentResult:
    """Structured result from intent classification."""

    intent: str  # "vault", "memory", or "chat"
    search: str  # "hybrid", "keyword", "both", or "none"
    terms: list[str]  # search terms extracted by the LLM


def _parse_intent_result(raw: str) -> IntentResult:
    """Parse structured intent response from LLM.

    Expected format:
        intent: vault|memory|chat
        search: hybrid|keyword|both|none
        terms: term1, term2
    """
    lines = raw.strip().splitlines()
    intent = "chat"
    search = "hybrid"
    terms: list[str] = []

    for line in lines:
        lower_line = line.strip().lower()
        if lower_line.startswith("intent:"):
            value = lower_line.split(":", 1)[1].strip()
            if "memory" in value:
                intent = "memory"
            elif "vault" in value:
                intent = "vault"
            else:
                intent = "chat"
        elif lower_line.startswith("search:"):
            value = lower_line.split(":", 1)[1].strip()
            if "both" in value:
                search = "both"
            elif "keyword" in value:
                search = "keyword"
            elif "hybrid" in value:
                search = "hybrid"
            else:
                search = "none"
        elif lower_line.startswith("terms:"):
            # Preserve original case for terms (names, proper nouns)
            value = line.strip().split(":", 1)[1].strip()
            if value and value.lower() != "none":
                terms = [t.strip() for t in value.split(",") if t.strip()]

    return IntentResult(intent=intent, search=search, terms=terms)


__all__ = ["LLMService", "IntentResult", "_parse_intent_result"]
