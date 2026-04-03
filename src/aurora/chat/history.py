"""ChatHistory — JSONL-persisted conversation history for Aurora chat sessions."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from aurora.runtime.paths import get_config_dir

HISTORY_FILENAME = "chat_history.jsonl"


class ChatHistory:
    """Persists conversation turns as JSONL records with role, content, and timestamp."""

    def __init__(self, *, path: Path | None = None) -> None:
        self.path = path or (get_config_dir() / HISTORY_FILENAME)

    def append_turn(self, role: str, content: str) -> None:
        """Append a single turn to the JSONL file.

        Creates parent directories if they don't exist.
        Each record has role, content, and ts (ISO 8601 UTC timestamp).
        """
        record = {"role": role, "content": content, "ts": datetime.now(UTC).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load(self) -> list[dict[str, str]]:
        """Load all records from JSONL file.

        Returns empty list if file does not exist.
        Skips empty lines.
        """
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    def get_recent(self, *, max_turns: int = 10) -> list[dict[str, str]]:
        """Return last max_turns user+assistant pairs as messages for LLM context.

        Each turn = 1 user + 1 assistant = 2 messages.
        So max_messages = max_turns * 2.
        Returns only role and content fields (strips ts for LLM consumption).
        """
        all_records = self.load()
        max_messages = max_turns * 2
        recent = all_records[-max_messages:] if len(all_records) > max_messages else all_records
        return [{"role": r["role"], "content": r["content"]} for r in recent]

    def clear(self) -> None:
        """Remove the JSONL history file if it exists."""
        if self.path.exists():
            self.path.unlink()


__all__ = ["ChatHistory", "HISTORY_FILENAME"]
