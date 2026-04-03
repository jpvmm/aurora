"""Tests for LLM system prompts and intent classification prompt."""
from __future__ import annotations

from aurora.llm.prompts import (
    INSUFFICIENT_EVIDENCE_MSG,
    INTENT_PROMPT,
    SYSTEM_PROMPT_CHAT,
    SYSTEM_PROMPT_GROUNDED,
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
