"""MemorySummarizer — orchestrates LLM session summarization and episodic file storage."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from aurora.llm.service import LLMService
from aurora.memory.store import EpisodicMemoryStore


class MemorySummarizer:
    """Orchestrates LLM session summarization and episodic file storage."""

    def __init__(self, *, llm: LLMService, store: EpisodicMemoryStore) -> None:
        self._llm = llm
        self._store = store

    def summarize_and_save(
        self, *, history_turns: list[dict[str, str]], turn_count: int
    ) -> Path | None:
        """Summarize session turns and write episodic memory file.

        Returns the path of the written file, or None if skipped.
        Skips if turn_count < 2 (per D-11) or if turns are empty.
        """
        if turn_count < 2 or not history_turns:
            return None

        raw = self._llm.summarize_session(history_turns)
        topic, summary = self._parse_response(raw)
        # Safety net: ensure "Data da sessao:" is always present in the body,
        # even if the LLM omitted it despite being instructed to include it.
        if "Data da sessao:" not in summary:
            summary = f"Data da sessao: {date.today().isoformat()}\n\n{summary}"
        return self._store.write(topic=topic, turn_count=turn_count, summary=summary)

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, str]:
        """Parse LLM response into (topic, summary_body).

        First line = topic (max 60 chars). Remaining lines = summary body.
        """
        lines = raw.strip().splitlines()
        if not lines:
            return ("sessao sem titulo", "")
        topic = lines[0].strip()[:60]
        summary = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        return (topic or "sessao sem titulo", summary)


__all__ = ["MemorySummarizer"]
