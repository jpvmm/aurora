"""ChatSession — per-turn intent routing loop for Aurora chat sessions."""
from __future__ import annotations

import logging
from typing import Callable

from aurora.chat.history import ChatHistory
from aurora.llm.prompts import (
    INSUFFICIENT_EVIDENCE_MSG,
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_GROUNDED,
    SYSTEM_PROMPT_GROUNDED_WITH_MEMORY,
    build_system_prompt_with_preferences,
)
from aurora.llm.service import LLMService
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.retrieval.service import RetrievalService
from aurora.runtime.paths import get_preferences_path
from aurora.runtime.settings import RuntimeSettings, load_settings

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a multi-turn chat session with intent-based routing.

    Each user message is classified as 'vault' or 'chat':
    - vault: triggers KB retrieval + grounded response (per D-13, D-14)
    - chat: free-form response using conversation history

    History is persisted to disk after each turn (per D-12).
    Context window is capped to max_turns pairs (Pitfall 6).
    """

    def __init__(
        self,
        *,
        history: ChatHistory | None = None,
        retrieval: RetrievalService | None = None,
        llm: LLMService | None = None,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
        on_token: Callable[[str], None] | None = None,
        on_insufficient: Callable[[str], None] | None = None,
        memory_backend: QMDSearchBackend | None = None,
    ) -> None:
        settings = settings_loader()
        self._history = history or ChatHistory()
        if retrieval is not None:
            self._retrieval = retrieval
        else:
            self._retrieval = RetrievalService(memory_backend=memory_backend)
        self._llm = llm or LLMService()
        self._max_turns = settings.chat_history_max_turns
        self._on_token = on_token or (lambda t: print(t, end="", flush=True))
        self._on_insufficient = on_insufficient or (lambda msg: print(msg))
        self._turn_count: int = 0
        # Snapshot history length at session start to isolate current session turns (per Pitfall 8)
        self._session_start_index: int = len(self._history.load())
        self._preferences_path = get_preferences_path()

    @property
    def turn_count(self) -> int:
        """Number of completed turns in this session (incremented after each process_turn)."""
        return self._turn_count

    @property
    def session_start_index(self) -> int:
        """Index into history marking the start of this session (per Pitfall 8)."""
        return self._session_start_index

    @property
    def history(self) -> ChatHistory:
        """Public access to conversation history."""
        return self._history

    @property
    def llm(self) -> LLMService:
        """Public access to LLM service (for background save in CLI)."""
        return self._llm

    def get_session_turns(self) -> list[dict[str, str]]:
        """Return only the turns from the current session (post session_start_index).

        Filters out historical turns from prior sessions.
        Returns role + content only (strips ts field).
        """
        all_turns = self._history.load()
        return [
            {"role": t["role"], "content": t["content"]}
            for t in all_turns[self._session_start_index:]
        ]

    def process_turn(self, user_message: str) -> str:
        """Process a single user turn through intent classification and routing.

        Classifies intent using only the latest message (per Pitfall 5, D-14).
        Vault turns trigger fresh KB retrieval (per D-13).
        Both user message and assistant response are persisted to history (per D-12).

        Returns the assistant response text.
        """
        # Classify intent using only the latest message (per Pitfall 5, D-14)
        intent = self._llm.classify_intent(user_message)
        logger.debug("Intent classification: message=%r -> %s", user_message[:50], intent)

        if intent == "vault":
            response = self._handle_vault_turn(user_message)
        else:
            response = self._handle_chat_turn(user_message)

        # Persist both turns to history (per D-12)
        self._history.append_turn("user", user_message)
        self._history.append_turn("assistant", response)

        self._turn_count += 1
        return response

    def _handle_vault_turn(self, user_message: str) -> str:
        """Handle a vault-intent turn: retrieve from KB (+memory if configured) then generate grounded response."""
        # Use dual retrieval if memory_backend is configured (per D-15)
        if self._retrieval._memory_backend is not None:
            result = self._retrieval.retrieve_with_memory(user_message)
        else:
            result = self._retrieval.retrieve(user_message)

        logger.debug(
            "Vault retrieval: %d notes, paths=%s",
            len(result.notes),
            [(n.path, n.score) for n in result.notes],
        )

        if result.insufficient_evidence:
            self._on_insufficient(INSUFFICIENT_EVIDENCE_MSG)
            return INSUFFICIENT_EVIDENCE_MSG

        # Select prompt based on whether memory notes are present (per D-16)
        has_memory = any(n.source == "memory" for n in result.notes)
        if has_memory:
            base_prompt = SYSTEM_PROMPT_GROUNDED_WITH_MEMORY
        else:
            base_prompt = SYSTEM_PROMPT_GROUNDED

        # Inject preferences if available (Pitfall 5)
        system_prompt = build_system_prompt_with_preferences(base_prompt, self._preferences_path)

        # Build messages manually so we control the system prompt
        context_msg = f"Contexto do vault:\n\n{result.context_text}\n\nPergunta: {user_message}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg},
        ]

        response = self._llm.chat_turn(messages, on_token=self._on_token)
        print()  # final newline after streaming
        return response

    def _handle_chat_turn(self, user_message: str) -> str:
        """Handle a chat-intent turn: free-form response using conversation history."""
        # Build messages with SYSTEM_PROMPT_CHAT + recent history + current message
        recent = self._history.get_recent(max_turns=self._max_turns)
        messages = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]
        messages.extend(recent)
        messages.append({"role": "user", "content": user_message})

        response = self._llm.chat_turn(messages, on_token=self._on_token)
        print()  # final newline after streaming
        return response


__all__ = ["ChatSession"]
