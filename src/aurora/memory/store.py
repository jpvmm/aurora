"""Episodic memory file store for Aurora long-term memory."""
from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

from aurora.runtime.paths import get_memory_dir

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "aurora-memory"
MEMORY_INDEX = "aurora-kb"


class EpisodicMemoryStore:
    """Stores and retrieves episodic memory as timestamped markdown files.

    Each memory file has YAML frontmatter with date, topic, turn_count, and
    source fields followed by a summary body.

    Files are stored in memory_dir (defaults to get_memory_dir()) and named
    using the ISO timestamp format YYYY-MM-DDTHH-MM.md.
    """

    def __init__(self, *, memory_dir: Path | None = None) -> None:
        self._memory_dir = memory_dir if memory_dir is not None else get_memory_dir()

    def write(self, *, topic: str, turn_count: int, summary: str) -> Path:
        """Create a timestamped episodic memory file with YAML frontmatter.

        Args:
            topic: Short label for what this memory covers.
            turn_count: Number of conversation turns in this session.
            summary: Prose summary of the session to persist.

        Returns:
            Path of the written markdown file.
        """
        self._memory_dir.mkdir(parents=True, exist_ok=True)

        base_stem = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M")
        path = self._resolve_collision_free_path(base_stem)

        frontmatter = {
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "topic": topic,
            "turn_count": turn_count,
            "source": "chat",
        }
        frontmatter_text = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
        content = f"---\n{frontmatter_text}---\n\n{summary}\n"
        path.write_text(content, encoding="utf-8")
        self._ensure_qmd_collection()
        self._qmd_update()
        return path

    def list_memories(self) -> list[dict]:
        """Return parsed frontmatter from all episodic memory files.

        Returns:
            List of dicts with frontmatter fields plus 'filename' key,
            sorted chronologically by filename. Empty list if directory
            does not exist.
        """
        if not self._memory_dir.exists():
            return []

        files = sorted(self._memory_dir.glob("*.md"))
        result = []
        for f in files:
            fm = self._parse_frontmatter(f)
            fm["filename"] = f.stem
            result.append(fm)
        return result

    def clear(self) -> int:
        """Delete all .md files from the memory directory.

        Returns:
            Number of files deleted. Returns 0 if directory does not exist.
        """
        if not self._memory_dir.exists():
            return 0

        count = 0
        for f in self._memory_dir.glob("*.md"):
            f.unlink()
            count += 1
        return count

    def _resolve_collision_free_path(self, base_stem: str) -> Path:
        """Return a path that does not already exist, appending -2, -3, etc. on collision."""
        candidate = self._memory_dir / f"{base_stem}.md"
        if not candidate.exists():
            return candidate

        suffix = 2
        while True:
            candidate = self._memory_dir / f"{base_stem}-{suffix}.md"
            if not candidate.exists():
                return candidate
            suffix += 1

    def _parse_frontmatter(self, path: Path) -> dict:
        """Parse YAML frontmatter from a memory markdown file.

        Returns empty dict on any parse failure (defensive).
        """
        try:
            text = path.read_text(encoding="utf-8")
            parts = text.split("---")
            if len(parts) < 3:
                return {}
            return yaml.safe_load(parts[1]) or {}
        except Exception:
            return {}

    def _ensure_qmd_collection(self) -> None:
        """Register memory directory as a QMD collection if not already registered."""
        try:
            result = subprocess.run(
                ("qmd", "--index", MEMORY_INDEX, "collection", "add",
                 str(self._memory_dir), "--name", MEMORY_COLLECTION, "--mask", "**/*.md"),
                check=False, capture_output=True, text=True,
            )
            combined = f"{result.stdout or ''} {result.stderr or ''}".lower()
            if result.returncode == 0 or "already exists" in combined:
                return
            logger.warning("QMD collection bootstrap failed: %s", combined.strip())
        except FileNotFoundError:
            logger.warning("qmd not found — memory files saved but not indexed")

    def _qmd_update(self) -> None:
        """Run qmd update + embed to index and vectorize new memory files."""
        try:
            subprocess.run(
                ("qmd", "--index", MEMORY_INDEX, "update"),
                check=False, capture_output=True, text=True,
            )
            subprocess.run(
                ("qmd", "--index", MEMORY_INDEX, "embed"),
                check=False, capture_output=True, text=True,
            )
        except FileNotFoundError:
            pass
