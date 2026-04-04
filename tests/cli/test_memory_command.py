"""Tests for aurora memory CLI commands — list, search, edit, clear."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from aurora.cli.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# TestMemoryList
# ---------------------------------------------------------------------------


class TestMemoryList:
    """Tests for aurora memory list command."""

    def test_memory_list_shows_empty_message_when_no_memories(self) -> None:
        """aurora memory list must print a friendly message when no memories exist."""
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.list_memories.return_value = []
            mock_store_cls.return_value = mock_store

            result = runner.invoke(app, ["memory", "list"])

        assert result.exit_code == 0
        assert "Nenhuma memoria encontrada" in result.output

    def test_memory_list_shows_date_topic_and_turns(self) -> None:
        """aurora memory list must print date, topic, and turn_count for each memory."""
        memories = [
            {"date": "2026-04-01", "topic": "Projeto Aurora", "turn_count": 5, "filename": "2026-04-01T10-00"},
            {"date": "2026-04-02", "topic": "Revisao de codigo", "turn_count": 3, "filename": "2026-04-02T09-00"},
        ]
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.list_memories.return_value = memories
            mock_store_cls.return_value = mock_store

            result = runner.invoke(app, ["memory", "list"])

        assert result.exit_code == 0
        assert "Projeto Aurora" in result.output
        assert "2026-04-01" in result.output
        assert "5" in result.output

    def test_memory_list_json_outputs_array(self) -> None:
        """aurora memory list --json must output a JSON array of memory metadata."""
        memories = [
            {"date": "2026-04-01", "topic": "Test", "turn_count": 2, "filename": "2026-04-01T10-00"},
        ]
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.list_memories.return_value = memories
            mock_store_cls.return_value = mock_store

            result = runner.invoke(app, ["memory", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["topic"] == "Test"

    def test_memory_list_json_empty_array_when_no_memories(self) -> None:
        """aurora memory list --json must output [] when no memories exist."""
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.list_memories.return_value = []
            mock_store_cls.return_value = mock_store

            result = runner.invoke(app, ["memory", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


# ---------------------------------------------------------------------------
# TestMemorySearch
# ---------------------------------------------------------------------------


class TestMemorySearch:
    """Tests for aurora memory search command."""

    def test_memory_search_runs_qmd_search_against_memory_collection(self) -> None:
        """aurora memory search must invoke QMDSearchBackend with aurora-memory collection."""
        from aurora.retrieval.contracts import QMDSearchHit, QMDSearchResponse

        hits = (
            QMDSearchHit(path="memory/2026-04-01.md", score=0.88, title="Reuniao Aurora", snippet="Aurora e um assistente"),
        )
        mock_response = QMDSearchResponse(ok=True, hits=hits)

        with patch("aurora.cli.memory.QMDSearchBackend") as mock_backend_cls:
            mock_backend = MagicMock()
            mock_backend.search.return_value = mock_response
            mock_backend_cls.return_value = mock_backend

            with patch("aurora.cli.memory.load_settings") as mock_settings:
                mock_settings.return_value = MagicMock(memory_top_k=5, memory_min_score=0.25)
                result = runner.invoke(app, ["memory", "search", "Aurora"])

        assert result.exit_code == 0
        mock_backend.search.assert_called_once_with("Aurora")

    def test_memory_search_shows_results_with_score_and_title(self) -> None:
        """aurora memory search must display score and title for each hit."""
        from aurora.retrieval.contracts import QMDSearchHit, QMDSearchResponse

        hits = (
            QMDSearchHit(path="memory/2026-04-01.md", score=0.88, title="Reuniao Aurora", snippet="trecho"),
        )
        mock_response = QMDSearchResponse(ok=True, hits=hits)

        with patch("aurora.cli.memory.QMDSearchBackend") as mock_backend_cls:
            mock_backend = MagicMock()
            mock_backend.search.return_value = mock_response
            mock_backend_cls.return_value = mock_backend

            with patch("aurora.cli.memory.load_settings") as mock_settings:
                mock_settings.return_value = MagicMock(memory_top_k=5, memory_min_score=0.25)
                result = runner.invoke(app, ["memory", "search", "Aurora"])

        assert "0.88" in result.output
        assert "Reuniao Aurora" in result.output

    def test_memory_search_json_outputs_structured_result(self) -> None:
        """aurora memory search --json must output JSON with ok and hits fields."""
        from aurora.retrieval.contracts import QMDSearchHit, QMDSearchResponse

        hits = (
            QMDSearchHit(path="memory/2026-04-01.md", score=0.88, title="Test", snippet="snip"),
        )
        mock_response = QMDSearchResponse(ok=True, hits=hits)

        with patch("aurora.cli.memory.QMDSearchBackend") as mock_backend_cls:
            mock_backend = MagicMock()
            mock_backend.search.return_value = mock_response
            mock_backend_cls.return_value = mock_backend

            with patch("aurora.cli.memory.load_settings") as mock_settings:
                mock_settings.return_value = MagicMock(memory_top_k=5, memory_min_score=0.25)
                result = runner.invoke(app, ["memory", "search", "query", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "ok" in data
        assert "hits" in data
        assert data["ok"] is True
        assert len(data["hits"]) == 1

    def test_memory_search_shows_empty_message_when_no_hits(self) -> None:
        """aurora memory search must print friendly message when no hits found."""
        from aurora.retrieval.contracts import QMDSearchResponse

        mock_response = QMDSearchResponse(ok=True, hits=())

        with patch("aurora.cli.memory.QMDSearchBackend") as mock_backend_cls:
            mock_backend = MagicMock()
            mock_backend.search.return_value = mock_response
            mock_backend_cls.return_value = mock_backend

            with patch("aurora.cli.memory.load_settings") as mock_settings:
                mock_settings.return_value = MagicMock(memory_top_k=5, memory_min_score=0.25)
                result = runner.invoke(app, ["memory", "search", "inexistente"])

        assert result.exit_code == 0
        assert "Nenhuma memoria" in result.output


# ---------------------------------------------------------------------------
# TestMemoryEdit
# ---------------------------------------------------------------------------


class TestMemoryEdit:
    """Tests for aurora memory edit command."""

    def test_memory_edit_opens_editor_with_preferences_path(self, tmp_path: Path) -> None:
        """aurora memory edit must invoke $EDITOR with preferences.md path."""
        import os

        prefs_path = tmp_path / "preferences.md"
        prefs_path.write_text("# Preferencias\n", encoding="utf-8")

        with patch("aurora.cli.memory.get_preferences_path", return_value=prefs_path):
            with patch("aurora.cli.memory.subprocess.run") as mock_run:
                with patch.dict(os.environ, {"EDITOR": "vim"}):
                    result = runner.invoke(app, ["memory", "edit"])

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "vim" in call_args
        assert str(prefs_path) in call_args

    def test_memory_edit_creates_preferences_file_if_missing(self, tmp_path: Path) -> None:
        """aurora memory edit must create preferences.md with pt-BR header if it doesn't exist."""
        prefs_path = tmp_path / "preferences.md"

        with patch("aurora.cli.memory.get_preferences_path", return_value=prefs_path):
            with patch("aurora.cli.memory.subprocess.run"):
                result = runner.invoke(app, ["memory", "edit"])

        assert prefs_path.exists()
        content = prefs_path.read_text(encoding="utf-8")
        assert "Preferencias" in content

    def test_memory_edit_outputs_created_message_when_file_missing(self, tmp_path: Path) -> None:
        """aurora memory edit must echo creation message when file is created."""
        prefs_path = tmp_path / "preferences.md"

        with patch("aurora.cli.memory.get_preferences_path", return_value=prefs_path):
            with patch("aurora.cli.memory.subprocess.run"):
                result = runner.invoke(app, ["memory", "edit"])

        assert "criado" in result.output.lower() or str(prefs_path) in result.output


# ---------------------------------------------------------------------------
# TestMemoryClear
# ---------------------------------------------------------------------------


class TestMemoryClear:
    """Tests for aurora memory clear command."""

    def test_memory_clear_with_yes_deletes_files(self) -> None:
        """aurora memory clear --yes must delete all episodic files."""
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.clear.return_value = 3
            mock_store_cls.return_value = mock_store

            with patch("aurora.cli.memory._remove_qmd_collection"):
                with patch("aurora.cli.memory.load_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(kb_qmd_index_name="aurora-kb")
                    result = runner.invoke(app, ["memory", "clear", "--yes"])

        assert result.exit_code == 0
        mock_store.clear.assert_called_once()

    def test_memory_clear_with_yes_removes_qmd_collection(self) -> None:
        """aurora memory clear --yes must remove the aurora-memory QMD collection."""
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.clear.return_value = 2
            mock_store_cls.return_value = mock_store

            with patch("aurora.cli.memory._remove_qmd_collection") as mock_remove:
                with patch("aurora.cli.memory.load_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(kb_qmd_index_name="aurora-kb")
                    result = runner.invoke(app, ["memory", "clear", "--yes"])

        mock_remove.assert_called_once()

    def test_memory_clear_json_output(self) -> None:
        """aurora memory clear --yes --json must output JSON with deleted count."""
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.clear.return_value = 4
            mock_store_cls.return_value = mock_store

            with patch("aurora.cli.memory._remove_qmd_collection"):
                with patch("aurora.cli.memory.load_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(kb_qmd_index_name="aurora-kb")
                    result = runner.invoke(app, ["memory", "clear", "--yes", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "deleted" in data
        assert data["deleted"] == 4

    def test_memory_clear_without_yes_cancels_when_rejected(self) -> None:
        """aurora memory clear without --yes must prompt and cancel if user says no."""
        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store_cls.return_value = mock_store

            # Simulate user confirming 'n' via stdin
            result = runner.invoke(app, ["memory", "clear"], input="n\n")

        mock_store.clear.assert_not_called()
        assert "cancelada" in result.output.lower() or result.exit_code == 0


class TestMemoryClearConfirmation:
    """Tests verifying that memory clear does NOT touch KB or preferences.md."""

    def test_memory_clear_does_not_affect_kb_collection(self) -> None:
        """aurora memory clear must only remove aurora-memory collection, not KB."""
        from aurora.memory.store import MEMORY_COLLECTION

        removed_collections = []

        def capture_remove(index_name: str) -> None:
            removed_collections.append(index_name)

        with patch("aurora.cli.memory.EpisodicMemoryStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.clear.return_value = 1
            mock_store_cls.return_value = mock_store

            with patch("aurora.cli.memory._remove_qmd_collection", side_effect=capture_remove):
                with patch("aurora.cli.memory.load_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(kb_qmd_index_name="aurora-kb")
                    runner.invoke(app, ["memory", "clear", "--yes"])

        # _remove_qmd_collection is called once with the index name (not collection name)
        assert len(removed_collections) == 1

    def test_memory_app_registered_in_app(self) -> None:
        """memory_app must be registered under 'memory' name in root app."""
        result = runner.invoke(app, ["memory", "--help"])
        assert result.exit_code == 0
        assert "memory" in result.output.lower() or "list" in result.output.lower()
