from __future__ import annotations

import pytest

from aurora.kb.contracts import KBScopeConfig
from aurora.kb.scope import (
    ScopeConfigurationError,
    ScopeNoMatchesError,
    ScopeRules,
)


def _build_scope(tmp_path, **kwargs) -> ScopeRules:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    config = KBScopeConfig(vault_root=str(vault_root), **kwargs)
    return ScopeRules.from_config(config)


def test_scope_is_case_sensitive_and_exclude_wins_over_include(tmp_path) -> None:
    scope = _build_scope(
        tmp_path,
        include=("notes/*.md",),
        exclude=("notes/Secret.md",),
        default_excludes=(),
    )

    excluded = scope.evaluate("notes/Secret.md")
    assert excluded.allowed is False
    assert excluded.reason == "excluded"
    assert excluded.matched_exclude == "notes/Secret.md"

    allowed = scope.evaluate("notes/secret.md")
    assert allowed.allowed is True
    assert allowed.reason == "included"

    wrong_case = scope.evaluate("Notes/secret.md")
    assert wrong_case.allowed is False
    assert wrong_case.reason == "not_included"


def test_scope_rejects_out_of_vault_include_rules(tmp_path) -> None:
    with pytest.raises(ScopeConfigurationError) as error:
        _build_scope(
            tmp_path,
            include=("../outside.md",),
            exclude=(),
            default_excludes=(),
        )

    message = str(error.value).lower()
    assert "fora do vault" in message
    assert "--dry-run" in message


def test_scope_dry_run_preview_reports_effective_scope(tmp_path) -> None:
    scope = _build_scope(
        tmp_path,
        include=("notes/*.md",),
        exclude=("notes/private.md",),
        default_excludes=(".obsidian/**",),
    )

    preview = scope.preview(
        [
            "notes/public.md",
            "notes/private.md",
            ".obsidian/workspace.md",
        ]
    )

    assert preview.vault_root.endswith("/vault")
    assert preview.include == ("notes/*.md",)
    assert preview.exclude == ("notes/private.md",)
    assert preview.default_excludes == (".obsidian/**",)
    assert preview.effective_excludes == (".obsidian/**", "notes/private.md")
    assert preview.eligible == ("notes/public.md",)
    assert {item.path for item in preview.skipped} == {
        "notes/private.md",
        ".obsidian/workspace.md",
    }


def test_scope_dry_run_with_includes_fails_when_no_files_match(tmp_path) -> None:
    scope = _build_scope(
        tmp_path,
        include=("daily/*.md",),
        exclude=(),
        default_excludes=(),
    )

    with pytest.raises(ScopeNoMatchesError) as error:
        scope.preview(["notes/public.md"])

    message = str(error.value).lower()
    assert "nenhum arquivo correspondeu" in message
    assert "aurora kb ingest" in message
