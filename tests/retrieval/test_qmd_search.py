"""Tests for QMDSearchBackend - shell-out to qmd query and qmd get commands."""
from __future__ import annotations

import json
from typing import Protocol
from unittest.mock import MagicMock

import pytest

from aurora.retrieval.contracts import QMDSearchDiagnostic, QMDSearchHit, QMDSearchResponse
from aurora.retrieval.qmd_search import QMDSearchBackend


class _FakeResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


def _make_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> _FakeResult:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _make_settings(
    index_name: str = "aurora-kb",
    collection_name: str = "aurora-kb-managed",
    top_k: int = 7,
    min_score: float = 0.30,
):
    settings = MagicMock()
    settings.kb_qmd_index_name = index_name
    settings.kb_qmd_collection_name = collection_name
    settings.retrieval_top_k = top_k
    settings.retrieval_min_score = min_score
    return settings


def _backend(runner, *, top_k=7, min_score=0.30) -> QMDSearchBackend:
    return QMDSearchBackend(
        command_runner=runner,
        settings_loader=lambda: _make_settings(top_k=top_k, min_score=min_score),
    )


# ---------------------------------------------------------------------------
# search() tests
# ---------------------------------------------------------------------------


def test_search_calls_subprocess_with_correct_args():
    """search() must pass all required qmd query flags in the correct order."""
    runner = MagicMock(return_value=_make_result(stdout="[]"))

    backend = _backend(runner)
    backend.search("test query")

    runner.assert_called_once_with(
        (
            "qmd",
            "--index",
            "aurora-kb",
            "query",
            "--json",
            "-n",
            "7",
            "-c",
            "aurora-kb-managed",
            "--min-score",
            "0.30",
            "test query",
        )
    )


def test_search_parses_hits_into_dataclasses():
    """search() must parse JSON hits into QMDSearchHit dataclasses."""
    hits_json = json.dumps(
        [
            {
                "file": "notes/alpha.md",
                "score": 0.85,
                "title": "Alpha Note",
                "snippet": "First snippet",
            },
            {
                "file": "notes/beta.md",
                "score": 0.72,
                "title": "Beta Note",
                "snippet": "Second snippet",
            },
        ]
    )
    runner = MagicMock(return_value=_make_result(stdout=hits_json))

    response = _backend(runner).search("query")

    assert response.ok is True
    assert len(response.hits) == 2
    assert response.hits[0] == QMDSearchHit(
        path="notes/alpha.md", score=0.85, title="Alpha Note", snippet="First snippet"
    )
    assert response.hits[1] == QMDSearchHit(
        path="notes/beta.md", score=0.72, title="Beta Note", snippet="Second snippet"
    )


def test_search_accepts_display_path_field():
    """search() must also map displayPath -> path when file field is absent."""
    hits_json = json.dumps(
        [{"displayPath": "notes/gamma.md", "score": 0.91, "title": "Gamma", "snippet": "snip"}]
    )
    runner = MagicMock(return_value=_make_result(stdout=hits_json))

    response = _backend(runner).search("query")

    assert response.ok is True
    assert response.hits[0].path == "notes/gamma.md"


def test_search_returns_empty_hits_on_empty_json_array():
    """search() must return empty hits when qmd returns empty array."""
    runner = MagicMock(return_value=_make_result(stdout="[]"))

    response = _backend(runner).search("no results query")

    assert response.ok is True
    assert response.hits == ()


def test_search_returns_error_when_qmd_not_found():
    """search() must handle FileNotFoundError and return backend_unavailable diagnostic."""

    def _runner(_argv):
        raise FileNotFoundError("qmd not found")

    response = _backend(_runner).search("some query")

    assert response.ok is False
    assert len(response.diagnostics) == 1
    diag = response.diagnostics[0]
    assert diag.category == "backend_unavailable"
    assert "qmd" in diag.recovery_hint.lower()


def test_search_returns_error_on_non_zero_exit_code():
    """search() must return error response when qmd exits with non-zero code."""
    runner = MagicMock(return_value=_make_result(returncode=1, stderr="some error"))

    response = _backend(runner).search("broken query")

    assert response.ok is False
    assert len(response.diagnostics) >= 1


def test_search_uses_configured_min_score_as_string():
    """search() must pass min_score as formatted string with two decimal places."""
    runner = MagicMock(return_value=_make_result(stdout="[]"))

    _backend(runner, min_score=0.50).search("query")

    call_args = runner.call_args[0][0]
    # --min-score flag should appear in the argv tuple
    min_score_idx = list(call_args).index("--min-score")
    assert call_args[min_score_idx + 1] == "0.50"


# ---------------------------------------------------------------------------
# fetch() tests
# ---------------------------------------------------------------------------


def test_fetch_calls_subprocess_with_correct_path():
    """fetch() must pass the collection-prefixed path to qmd get."""
    runner = MagicMock(return_value=_make_result(stdout="note content here"))

    backend = _backend(runner)
    result = backend.fetch("notes/alpha.md")

    runner.assert_called_once_with(
        ("qmd", "--index", "aurora-kb", "get", "aurora-kb-managed/notes/alpha.md")
    )
    assert result == "note content here"


def test_fetch_returns_none_on_non_zero_exit_code():
    """fetch() must return None when qmd exits with non-zero code."""
    runner = MagicMock(return_value=_make_result(returncode=1, stderr="not found"))

    result = _backend(runner).fetch("notes/missing.md")

    assert result is None


def test_fetch_returns_none_when_qmd_not_found():
    """fetch() must return None (not raise) when qmd command is missing."""

    def _runner(_argv):
        raise FileNotFoundError("qmd not found")

    result = _backend(_runner).fetch("notes/alpha.md")

    assert result is None
