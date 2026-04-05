"""Unit tests for EpisodicMemoryStore."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path):
    """Return an EpisodicMemoryStore scoped to a temporary directory."""
    from aurora.memory.store import EpisodicMemoryStore

    return EpisodicMemoryStore(memory_dir=tmp_path / "memory")


# ---------------------------------------------------------------------------
# MEMORY_COLLECTION constant
# ---------------------------------------------------------------------------


def test_memory_collection_constant_exists():
    """MEMORY_COLLECTION constant must be 'aurora-memory'."""
    from aurora.memory.store import MEMORY_COLLECTION

    assert MEMORY_COLLECTION == "aurora-memory"


# ---------------------------------------------------------------------------
# write() tests
# ---------------------------------------------------------------------------


def test_write_creates_markdown_file_in_memory_dir(tmp_path):
    """write() creates a .md file inside the memory directory."""
    store = _make_store(tmp_path)
    path = store.write(topic="Daily standup", turn_count=3, summary="We discussed goals.")

    assert path.exists()
    assert path.suffix == ".md"
    assert path.parent == tmp_path / "memory"


def test_write_creates_directory_if_not_exists(tmp_path):
    """write() creates memory directory with parents=True if missing."""
    memory_dir = tmp_path / "new" / "deep" / "memory"
    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=memory_dir)
    path = store.write(topic="test", turn_count=1, summary="summary")

    assert path.exists()
    assert memory_dir.is_dir()


def test_write_filename_follows_timestamp_format(tmp_path):
    """write() filename follows YYYY-MM-DDTHH-MM.md format."""
    store = _make_store(tmp_path)
    path = store.write(topic="test", turn_count=2, summary="content")

    name = path.stem
    # Should be 16 chars like 2026-04-03T14-30
    assert len(name) == 16 or name[-2:].isdigit()
    # Must contain date-like pattern
    parts = name.split("T")
    assert len(parts) == 2
    date_part, time_part = parts
    assert len(date_part) == 10  # YYYY-MM-DD
    assert len(time_part) == 5  # HH-MM


def test_write_file_has_yaml_frontmatter(tmp_path):
    """write() creates a file with valid YAML frontmatter between --- delimiters."""
    store = _make_store(tmp_path)
    path = store.write(topic="memory test", turn_count=4, summary="Summary text here.")

    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    parts = content.split("---")
    # parts[0] = '', parts[1] = frontmatter, parts[2] = body
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert "date" in fm
    assert "topic" in fm
    assert "turn_count" in fm
    assert "source" in fm


def test_write_frontmatter_has_correct_field_values(tmp_path):
    """write() frontmatter contains correct date, topic, turn_count, source values."""
    store = _make_store(tmp_path)
    path = store.write(topic="my topic", turn_count=7, summary="my summary")

    content = path.read_text(encoding="utf-8")
    parts = content.split("---")
    fm = yaml.safe_load(parts[1])

    assert fm["topic"] == "my topic"
    assert fm["turn_count"] == 7
    assert fm["source"] == "chat"
    # date should be a date string
    assert fm["date"] is not None


def test_write_body_matches_summary(tmp_path):
    """write() file body contains the summary text."""
    store = _make_store(tmp_path)
    summary = "This is the summary of our conversation."
    path = store.write(topic="test", turn_count=1, summary=summary)

    content = path.read_text(encoding="utf-8")
    # Body is after the second --- delimiter
    body = content.split("---", 2)[2].strip()
    assert body == summary


def test_write_collision_appends_suffix(tmp_path):
    """write() with filename collision appends -2, -3 suffixes."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=memory_dir)

    # Manually create a file with expected timestamp to force collision
    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M")
    existing = memory_dir / f"{now_str}.md"
    existing.write_text("---\ndate: 2026-01-01\ntopic: x\nturn_count: 1\nsource: chat\n---\n\nbody\n")

    path = store.write(topic="collision test", turn_count=2, summary="new summary")

    # Should be either -2 suffix or a different minute
    assert path.exists()
    assert path != existing


def test_write_collision_creates_dash_2_file(tmp_path):
    """write() with collision creates -2 variant when base name is taken."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=memory_dir)

    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M")
    base_file = memory_dir / f"{now_str}.md"
    base_file.write_text("---\ndate: 2026-01-01\ntopic: x\nturn_count: 1\nsource: chat\n---\n\noriginal\n")

    path = store.write(topic="collision test", turn_count=2, summary="second write")

    # The new path should be -2 variant
    expected = memory_dir / f"{now_str}-2.md"
    assert path == expected


# ---------------------------------------------------------------------------
# list_memories() tests
# ---------------------------------------------------------------------------


def test_list_memories_returns_empty_when_dir_missing(tmp_path):
    """list_memories() returns [] when memory directory doesn't exist."""
    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=tmp_path / "nonexistent")
    result = store.list_memories()

    assert result == []


def test_list_memories_returns_parsed_frontmatter(tmp_path):
    """list_memories() returns list of dicts with frontmatter fields and filename."""
    store = _make_store(tmp_path)
    store.write(topic="first note", turn_count=2, summary="summary 1")
    store.write(topic="second note", turn_count=3, summary="summary 2")

    memories = store.list_memories()

    assert len(memories) == 2
    for m in memories:
        assert "date" in m
        assert "topic" in m
        assert "turn_count" in m
        assert "source" in m
        assert "filename" in m


def test_list_memories_returns_sorted_chronologically(tmp_path):
    """list_memories() returns results sorted chronologically by filename."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)

    # Create files with known names
    file_a = memory_dir / "2026-01-01T09-00.md"
    file_b = memory_dir / "2026-01-02T09-00.md"
    file_c = memory_dir / "2026-01-03T09-00.md"
    frontmatter_template = "---\ndate: {date}\ntopic: note {n}\nturn_count: 1\nsource: chat\n---\n\nbody\n"

    file_a.write_text(frontmatter_template.format(date="2026-01-01", n="a"))
    file_c.write_text(frontmatter_template.format(date="2026-01-03", n="c"))
    file_b.write_text(frontmatter_template.format(date="2026-01-02", n="b"))

    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=memory_dir)
    memories = store.list_memories()

    filenames = [m["filename"] for m in memories]
    assert filenames == sorted(filenames)


def test_list_memories_filename_key_is_stem(tmp_path):
    """list_memories() includes filename key (stem without extension)."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    file = memory_dir / "2026-04-01T10-00.md"
    file.write_text("---\ndate: 2026-04-01\ntopic: test\nturn_count: 1\nsource: chat\n---\n\nbody\n")

    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=memory_dir)
    memories = store.list_memories()

    assert len(memories) == 1
    assert memories[0]["filename"] == "2026-04-01T10-00"


# ---------------------------------------------------------------------------
# clear() tests
# ---------------------------------------------------------------------------


def test_clear_returns_0_when_dir_missing(tmp_path):
    """clear() returns 0 when memory directory doesn't exist."""
    from aurora.memory.store import EpisodicMemoryStore

    store = EpisodicMemoryStore(memory_dir=tmp_path / "nonexistent")
    assert store.clear() == 0


def test_clear_deletes_all_md_files(tmp_path):
    """clear() deletes all .md files and returns count."""
    store = _make_store(tmp_path)
    store.write(topic="a", turn_count=1, summary="one")
    store.write(topic="b", turn_count=2, summary="two")

    count = store.clear()

    assert count == 2
    memory_dir = tmp_path / "memory"
    remaining = list(memory_dir.glob("*.md"))
    assert remaining == []


def test_clear_returns_correct_count(tmp_path):
    """clear() returns the exact number of deleted files."""
    store = _make_store(tmp_path)
    for i in range(5):
        store.write(topic=f"topic {i}", turn_count=i + 1, summary=f"summary {i}")

    # Manually force different timestamps by pre-creating
    count = store.clear()
    assert count == 5


# ---------------------------------------------------------------------------
# Structured summary body tests (Task 2)
# ---------------------------------------------------------------------------


def test_write_body_with_structured_summary(tmp_path):
    """write() stores structured summary body with ## sections and date line correctly."""
    store = _make_store(tmp_path)
    structured_summary = (
        "Data da sessao: 2026-04-03\n\n"
        "## Topicos\n"
        "Discutimos arquitetura de software.\n\n"
        "## Decisoes\n"
        "Optamos por usar Python 3.13.\n\n"
        "## Contexto\n"
        "Projeto Aurora - assistente privado."
    )
    path = store.write(topic="Arquitetura de Software", turn_count=4, summary=structured_summary)

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    body = content.split("---", 2)[2].strip()
    assert "Data da sessao: 2026-04-03" in body
    assert "## Topicos" in body
    assert "## Decisoes" in body
    assert "## Contexto" in body
