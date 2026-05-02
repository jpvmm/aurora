"""Unit tests for ChatHistory JSONL persistence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aurora.chat.history import ChatHistory, HISTORY_FILENAME


class TestChatHistoryAppend:
    """Tests for ChatHistory.append_turn."""

    def test_append_writes_jsonl_line(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "hello")
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["role"] == "user"
        assert record["content"] == "hello"
        assert "ts" in record

    def test_append_multiple_turns_each_on_own_line(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "first")
        history.append_turn("assistant", "response")
        history.append_turn("user", "second")
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["role"] == "user"
        assert json.loads(lines[1])["role"] == "assistant"
        assert json.loads(lines[2])["content"] == "second"

    def test_append_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "subdir" / "nested" / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "hi")
        assert path.exists()

    def test_append_record_has_role_content_ts_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("assistant", "response text")
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert set(record.keys()) >= {"role", "content", "ts"}
        assert record["role"] == "assistant"
        assert record["content"] == "response text"

    def test_append_uses_ensure_ascii_false(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "olá")
        raw = path.read_text(encoding="utf-8")
        # ensure_ascii=False means the actual UTF-8 chars are stored, not escaped
        assert "olá" in raw


class TestChatHistoryLoad:
    """Tests for ChatHistory.load."""

    def test_load_returns_empty_list_when_file_does_not_exist(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "nonexistent.jsonl")
        assert history.load() == []

    def test_load_returns_list_of_dicts(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "hello")
        history.append_turn("assistant", "world")
        records = history.load()
        assert len(records) == 2
        assert records[0]["role"] == "user"
        assert records[0]["content"] == "hello"
        assert records[1]["role"] == "assistant"

    def test_load_records_have_role_content_ts(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "test")
        records = history.load()
        assert "role" in records[0]
        assert "content" in records[0]
        assert "ts" in records[0]

    def test_load_skips_empty_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        path.write_text(
            '{"role":"user","content":"a","ts":"2024-01-01T00:00:00+00:00"}\n\n'
            '{"role":"assistant","content":"b","ts":"2024-01-01T00:00:01+00:00"}\n',
            encoding="utf-8",
        )
        history = ChatHistory(path=path)
        records = history.load()
        assert len(records) == 2


class TestChatHistoryGetRecent:
    """Tests for ChatHistory.get_recent context window capping."""

    def test_get_recent_returns_last_n_pairs(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        # Write 5 user+assistant pairs (10 messages total)
        for i in range(5):
            history.append_turn("user", f"question {i}")
            history.append_turn("assistant", f"answer {i}")
        recent = history.get_recent(max_turns=3)
        # 3 pairs = 6 messages
        assert len(recent) == 6
        # Should be the last 3 pairs
        assert recent[0]["content"] == "question 2"
        assert recent[-1]["content"] == "answer 4"

    def test_get_recent_caps_to_max_turns_pairs(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        # Write 15 user+assistant pairs (30 messages total)
        for i in range(15):
            history.append_turn("user", f"q{i}")
            history.append_turn("assistant", f"a{i}")
        recent = history.get_recent(max_turns=10)
        # max_turns=10 means max 20 messages
        assert len(recent) == 20

    def test_get_recent_returns_all_when_fewer_than_max(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "hello")
        history.append_turn("assistant", "hi")
        recent = history.get_recent(max_turns=10)
        assert len(recent) == 2

    def test_get_recent_omits_ts_field(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "test")
        history.append_turn("assistant", "reply")
        recent = history.get_recent(max_turns=10)
        for msg in recent:
            assert set(msg.keys()) == {"role", "content"}

    def test_get_recent_returns_empty_when_no_history(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "nonexistent.jsonl")
        assert history.get_recent(max_turns=10) == []


class TestChatHistoryDefaultPath:
    """Test default path uses get_config_dir."""

    def test_default_path_uses_config_dir_and_history_filename(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path))
        history = ChatHistory()
        assert history.path == tmp_path / HISTORY_FILENAME

    def test_history_filename_constant(self) -> None:
        assert HISTORY_FILENAME == "chat_history.jsonl"


class TestChatHistoryClear:
    """Tests for ChatHistory.clear."""

    def test_clear_removes_file(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        history = ChatHistory(path=path)
        history.append_turn("user", "hello")
        assert path.exists()
        history.clear()
        assert not path.exists()

    def test_clear_does_not_error_when_file_missing(self, tmp_path: Path) -> None:
        history = ChatHistory(path=tmp_path / "nonexistent.jsonl")
        # Should not raise
        history.clear()


class TestGetRecentFiltersReformulations:
    """D-10 + RESEARCH §7: reformulation entries persist but never reach LLM context."""

    def test_reformulation_appears_in_jsonl_after_thin_then_thick(self, tmp_path: Path) -> None:
        """[reformulation] system entry persists to disk (D-10 part a)."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        history.append_turn("user", "primeira pergunta")
        history.append_turn("system", "[reformulation] segunda forma da pergunta")
        history.append_turn("assistant", "resposta")
        records = history.load()
        assert any(
            r["role"] == "system" and r["content"].startswith("[reformulation] ")
            for r in records
        )

    def test_get_recent_excludes_reformulation_entries(self, tmp_path: Path) -> None:
        """get_recent never returns [reformulation] system records (D-10 part b)."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        history.append_turn("user", "q1")
        history.append_turn("system", "[reformulation] q1 reformulada")
        history.append_turn("assistant", "a1")
        recent = history.get_recent(max_turns=10)
        assert all(
            not (m["role"] == "system" and m["content"].startswith("[reformulation] "))
            for m in recent
        )

    def test_filter_happens_before_slice(self, tmp_path: Path) -> None:
        """Reformulations must NOT steal slots from real pairs (RESEARCH §7).

        Write 5 user/assistant pairs interleaved with 3 reformulation system
        entries; max_turns=3 must yield exactly 3 user + 3 assistant records
        (the 3 LAST pairs), zero reformulation records.
        """
        history = ChatHistory(path=tmp_path / "h.jsonl")
        for i in range(5):
            history.append_turn("user", f"q{i}")
            history.append_turn("assistant", f"a{i}")
            if i in (1, 2, 3):
                history.append_turn("system", f"[reformulation] q{i} reformulada")
        recent = history.get_recent(max_turns=3)
        user_msgs = [m for m in recent if m["role"] == "user"]
        assistant_msgs = [m for m in recent if m["role"] == "assistant"]
        assert len(user_msgs) == 3
        assert len(assistant_msgs) == 3
        assert user_msgs[-1]["content"] == "q4"
        assert all(
            not (m["role"] == "system" and m["content"].startswith("[reformulation] "))
            for m in recent
        )

    def test_no_reformulations_present_returns_unchanged(self, tmp_path: Path) -> None:
        """Pure-additive: no reformulations -> behavior identical to today."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        history.append_turn("user", "q")
        history.append_turn("assistant", "a")
        recent = history.get_recent(max_turns=10)
        assert len(recent) == 2
        assert recent[0]["content"] == "q"
        assert recent[1]["content"] == "a"
