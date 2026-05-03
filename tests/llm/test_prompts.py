"""Tests for LLM system prompts and intent classification prompt."""
from __future__ import annotations

from aurora.llm.prompts import (
    INSUFFICIENT_EVIDENCE_MSG,
    INTENT_PROMPT,
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_GROUNDED,
    SYSTEM_PROMPT_MEMORY_FIRST,
    get_system_prompt_memory_first,
)


def test_system_prompt_grounded_contains_pt_br():
    """SYSTEM_PROMPT_GROUNDED must mandate pt-BR language (CLI-03)."""
    assert "pt-BR" in SYSTEM_PROMPT_GROUNDED


def test_system_prompt_grounded_contains_citation_format():
    """SYSTEM_PROMPT_GROUNDED must specify inline citation format (RET-02, D-08)."""
    assert "[caminho/nota.md]" in SYSTEM_PROMPT_GROUNDED


def test_system_prompt_grounded_contains_grounding_constraint():
    """SYSTEM_PROMPT_GROUNDED must restrict answers to vault context only (D-06)."""
    assert "SOMENTE com base nas notas" in SYSTEM_PROMPT_GROUNDED


def test_system_prompt_grounded_contains_deduplication_instruction():
    """SYSTEM_PROMPT_GROUNDED must instruct to deduplicate citations (D-09)."""
    assert "Deduplique" in SYSTEM_PROMPT_GROUNDED


def test_system_prompt_chat_exists():
    """SYSTEM_PROMPT_CHAT must be a non-empty string."""
    assert isinstance(SYSTEM_PROMPT_CHAT, str)
    assert len(SYSTEM_PROMPT_CHAT) > 0


def test_intent_prompt_contains_vault_classification():
    """INTENT_PROMPT must have 'vault' as a classification option (D-14)."""
    assert "vault" in INTENT_PROMPT


def test_intent_prompt_contains_chat_classification():
    """INTENT_PROMPT must have 'chat' as a classification option (D-14)."""
    assert "chat" in INTENT_PROMPT


def test_insufficient_evidence_msg_content():
    """INSUFFICIENT_EVIDENCE_MSG must contain expected pt-BR refusal text."""
    assert "Nao encontrei evidencia suficiente" in INSUFFICIENT_EVIDENCE_MSG


# ---------------------------------------------------------------------------
# Three-way intent classification tests (Task 1)
# ---------------------------------------------------------------------------


def test_intent_prompt_contains_memory_classification():
    """INTENT_PROMPT must have 'memory' as a classification option."""
    assert "memory" in INTENT_PROMPT


def test_intent_prompt_has_three_categories():
    """INTENT_PROMPT must have all three categories: vault, memory, chat."""
    assert "vault" in INTENT_PROMPT
    assert "memory" in INTENT_PROMPT
    assert "chat" in INTENT_PROMPT


def test_intent_prompt_has_memory_examples():
    """INTENT_PROMPT must include example memory-pattern phrases."""
    assert any(phrase in INTENT_PROMPT for phrase in ["conversamos", "lembra", "ultima sessao"])


def test_intent_prompt_clarifies_diary_is_vault_not_memory():
    """INTENT_PROMPT must explicitly state that dated diary/journal queries are vault, not memory.

    Previous symptom: 'o que fiz no dia 06-04-2026?' was classified as memory intent
    by the LLM, routing the query to the (separately broken) aurora-memory QMD
    collection instead of aurora-kb-managed where diario notes live.
    """
    assert "diario" in INTENT_PROMPT.lower() or "journal" in INTENT_PROMPT.lower(), (
        "Vault description must mention diario/journal so the classifier doesn't "
        "treat dated daily-note lookups as memory recall."
    )
    # The memory description must explicitly disclaim diary lookups
    assert "diario" in INTENT_PROMPT.lower(), (
        "Memory description must disclaim diary lookups to prevent intent mis-routing."
    )


def test_intent_prompt_has_dated_diary_example():
    """INTENT_PROMPT must include at least one example of a date-stamped query routing to vault.

    Without an explicit example, the LLM falls back to keyword matching against the
    'sobre o que conversamos ontem?' memory example and mis-routes diary lookups.
    """
    # An example with intent: vault and a date pattern (DD-MM-YYYY style)
    import re
    has_dated_vault_example = bool(
        re.search(r'"[^"]*\d{2}-\d{2}-\d{4}[^"]*"', INTENT_PROMPT)
    )
    assert has_dated_vault_example, (
        "INTENT_PROMPT needs an example with a DD-MM-YYYY date pattern showing "
        "the classifier routes such queries to vault, not memory."
    )


def test_intent_prompt_three_way_response_instruction():
    """INTENT_PROMPT must instruct structured response with intent, search, and terms."""
    assert "vault" in INTENT_PROMPT and "memory" in INTENT_PROMPT and "chat" in INTENT_PROMPT
    assert "intent:" in INTENT_PROMPT
    assert "search:" in INTENT_PROMPT
    assert "terms:" in INTENT_PROMPT


# ---------------------------------------------------------------------------
# Memory-first system prompt tests (Task 1)
# ---------------------------------------------------------------------------


def test_system_prompt_memory_first_exists():
    """SYSTEM_PROMPT_MEMORY_FIRST must be a non-empty string."""
    assert isinstance(SYSTEM_PROMPT_MEMORY_FIRST, str)
    assert len(SYSTEM_PROMPT_MEMORY_FIRST) > 0


def test_system_prompt_memory_first_has_temporal_emphasis():
    """Memory-first prompt must emphasize past conversations and memories."""
    assert "conversas anteriores" in SYSTEM_PROMPT_MEMORY_FIRST or "Priorize as memorias" in SYSTEM_PROMPT_MEMORY_FIRST


def test_system_prompt_memory_first_has_memory_citation_format():
    """Memory-first prompt must include [memoria: ...] citation format."""
    assert "[memoria:" in SYSTEM_PROMPT_MEMORY_FIRST


def test_get_system_prompt_memory_first_returns_nonempty_string():
    """get_system_prompt_memory_first() must return a non-empty string."""
    result = get_system_prompt_memory_first()
    assert isinstance(result, str)
    assert len(result) > 0
