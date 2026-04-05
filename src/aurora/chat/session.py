"""ChatSession — per-turn intent routing loop for Aurora chat sessions."""
from __future__ import annotations

import logging
from typing import Callable

from aurora.chat.history import ChatHistory
from aurora.llm.prompts import (
    INSUFFICIENT_EVIDENCE_MSG,
    build_system_prompt_with_preferences,
    get_system_prompt_chat,
    get_system_prompt_grounded,
    get_system_prompt_grounded_with_memory,
    get_system_prompt_memory_first,
)
from aurora.llm.service import LLMService
from aurora.retrieval.contracts import RetrievalResult, RetrievedNote
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.retrieval.service import RetrievalService
from aurora.runtime.paths import get_preferences_path
from aurora.runtime.settings import RuntimeSettings, load_settings

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a multi-turn chat session with intent-based routing.

    Each user message is classified as 'vault', 'memory', or 'chat':
    - vault: triggers KB retrieval + grounded response (per D-13, D-14)
    - memory: triggers memory-first retrieval + memory-focused response (per D-04, D-15)
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
        on_status: Callable[[str], None] | None = None,
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
        self._on_status = on_status or (lambda _msg: None)
        self._turn_count: int = 0
        # Snapshot history length at session start to isolate current session turns (per Pitfall 8)
        self._session_start_index: int = len(self._history.load())
        self._preferences_path = get_preferences_path()
        # Carry-forward state: paths from the previous vault/memory turn (per D-08, D-09, D-10)
        self._last_retrieved_paths: list[str] = []

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

    def _apply_carry_forward(self, result: RetrievalResult) -> RetrievalResult:
        """Supplement fresh retrieval results with notes from the previous turn (per D-09).

        If _last_retrieved_paths is empty or result.insufficient_evidence is True,
        returns result unchanged.

        For each carry-forward path not already in fresh results, fetches content
        via self._retrieval._backend.fetch and appends as a supplementary note.
        Carry-forward supplements are capped at 3 notes.
        """
        if not self._last_retrieved_paths:
            return result
        if result.insufficient_evidence:
            return result

        fresh_paths = {n.path for n in result.notes}
        missing_paths = [p for p in self._last_retrieved_paths if p not in fresh_paths][:3]

        if not missing_paths:
            return result

        supplements: list[RetrievedNote] = []
        for path in missing_paths:
            content = self._retrieval._backend.fetch(path)
            if content is None:
                logger.debug("_apply_carry_forward: skipping %s (fetch returned None)", path)
                continue
            supplements.append(RetrievedNote(path=path, score=0.0, content=content, source="vault"))

        if not supplements:
            return result

        all_notes = list(result.notes) + supplements
        context_text = self._retrieval._assemble_context(all_notes)
        return RetrievalResult(
            ok=True,
            notes=tuple(all_notes),
            context_text=context_text,
            insufficient_evidence=False,
        )

    def process_turn(self, user_message: str) -> str:
        """Process a single user turn through intent classification and routing.

        Classifies intent using only the latest message (per Pitfall 5, D-14).
        Vault turns trigger fresh KB retrieval (per D-13).
        Both user message and assistant response are persisted to history (per D-12).

        Returns the assistant response text.
        """
        # Classify intent using only the latest message (per Pitfall 5, D-14)
        self._on_status("Classificando pergunta...")
        intent = self._llm.classify_intent(user_message)
        logger.debug("Intent classification: message=%r -> %s", user_message[:50], intent)

        if intent == "vault":
            response = self._handle_vault_turn(user_message)
        elif intent == "memory":
            response = self._handle_memory_turn(user_message)
        else:
            self._on_status("Pensando...")
            response = self._handle_chat_turn(user_message)

        # Persist both turns to history (per D-12)
        self._history.append_turn("user", user_message)
        self._history.append_turn("assistant", response)

        self._turn_count += 1
        return response

    def _handle_vault_turn(self, user_message: str) -> str:
        """Handle a vault-intent turn: retrieve from KB (+memory if configured) then generate grounded response."""
        self._on_status("Buscando no vault...")
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

        # Apply carry-forward supplements from previous turn (per D-09), before insufficient check
        result = self._apply_carry_forward(result)

        # Update carry-forward state (per D-08, D-10): cap at 3, even if insufficient (empty notes)
        self._last_retrieved_paths = [n.path for n in result.notes][:3]

        if result.insufficient_evidence:
            self._on_insufficient(INSUFFICIENT_EVIDENCE_MSG)
            return INSUFFICIENT_EVIDENCE_MSG

        # Select prompt based on whether memory notes are present (per D-16)
        has_memory = any(n.source == "memory" for n in result.notes)
        if has_memory:
            base_prompt = get_system_prompt_grounded_with_memory()
        else:
            base_prompt = get_system_prompt_grounded()

        # Inject preferences if available (Pitfall 5)
        system_prompt = build_system_prompt_with_preferences(base_prompt, self._preferences_path)

        self._on_status(f"Encontrei {len(result.notes)} nota(s). Gerando resposta...")
        # Build messages manually so we control the system prompt
        context_msg = f"Contexto do vault:\n\n{result.context_text}\n\nPergunta: {user_message}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg},
        ]

        response = self._llm.chat_turn(messages, on_token=self._on_token)
        print()  # final newline after streaming
        return response

    def _handle_memory_turn(self, user_message: str) -> str:
        """Handle a memory-intent turn: retrieve from memory (+vault supplement) then generate response."""
        self._on_status("Buscando nas memorias...")
        result = self._retrieval.retrieve_memory_first(user_message)

        logger.debug(
            "Memory retrieval: %d notes, paths=%s",
            len(result.notes),
            [(n.path, n.score) for n in result.notes],
        )

        # Apply carry-forward supplements from previous turn (per D-09), before insufficient check
        result = self._apply_carry_forward(result)

        # Update carry-forward state (per D-08, D-10): cap at 3, even if insufficient (empty notes)
        self._last_retrieved_paths = [n.path for n in result.notes][:3]

        if result.insufficient_evidence:
            self._on_insufficient(INSUFFICIENT_EVIDENCE_MSG)
            return INSUFFICIENT_EVIDENCE_MSG

        base_prompt = get_system_prompt_memory_first()
        system_prompt = build_system_prompt_with_preferences(base_prompt, self._preferences_path)

        self._on_status(f"Encontrei {len(result.notes)} fonte(s). Gerando resposta...")
        context_msg = f"Contexto das memorias e vault:\n\n{result.context_text}\n\nPergunta: {user_message}"
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
        messages = [{"role": "system", "content": get_system_prompt_chat()}]
        messages.extend(recent)
        messages.append({"role": "user", "content": user_message})

        response = self._llm.chat_turn(messages, on_token=self._on_token)
        print()  # final newline after streaming

        # Clear carry-forward state after chat turns (per D-11)
        self._last_retrieved_paths = []

        return response


__all__ = ["ChatSession"]
