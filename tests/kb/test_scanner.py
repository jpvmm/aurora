from __future__ import annotations

from pathlib import Path

import pytest

from aurora.kb.contracts import KBScopeConfig
from aurora.kb.scanner import scan_markdown_files
from aurora.kb.scope import ScopeRules


def _write(path: Path, content: str = "content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_scope(vault_root: Path) -> ScopeRules:
    config = KBScopeConfig(
        vault_root=str(vault_root),
        include=("notes/*.md",),
        exclude=("notes/private.md",),
        default_excludes=(".obsidian/**",),
    )
    return ScopeRules.from_config(config)


def test_scanner_finds_only_scoped_markdown_and_reports_skip_reasons(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    _write(vault_root / "notes" / "a.md")
    _write(vault_root / "notes" / "z.md")
    _write(vault_root / "notes" / "private.md")
    _write(vault_root / "notes" / "todo.txt")
    _write(vault_root / "notes" / "UPPER.MD")
    _write(vault_root / ".obsidian" / "workspace.md")

    symlink_path = vault_root / "notes" / "linked.md"
    try:
        symlink_path.symlink_to(vault_root / "notes" / "a.md")
    except OSError:
        pytest.skip("Symlink not supported on this filesystem.")

    result = scan_markdown_files(vault_root=vault_root, scope=_build_scope(vault_root))

    assert result.indexed == ("notes/a.md", "notes/z.md")
    skipped = {(item.path, item.reason) for item in result.skipped}
    assert ("notes/private.md", "scope") in skipped
    assert ("notes/todo.txt", "extension") in skipped
    assert ("notes/UPPER.MD", "extension") in skipped
    assert (".obsidian/workspace.md", "hidden_system_exclusion") in skipped
    assert ("notes/linked.md", "symlink") in skipped


def test_scanner_returns_deterministic_order_for_indexed_and_skipped_files(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    _write(vault_root / "notes" / "c.md")
    _write(vault_root / "notes" / "a.md")
    _write(vault_root / "notes" / "b.txt")
    _write(vault_root / ".obsidian" / "x.md")

    result = scan_markdown_files(vault_root=vault_root, scope=_build_scope(vault_root))

    assert result.indexed == ("notes/a.md", "notes/c.md")
    assert [item.path for item in result.skipped] == [
        ".obsidian/x.md",
        "notes/b.txt",
    ]
