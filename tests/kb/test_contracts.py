from __future__ import annotations

import pytest
from pydantic import ValidationError

from aurora.kb.contracts import (
    KBFileDiagnostic,
    KBOperationCounters,
    KBOperationSummary,
    KBScopeConfig,
)


def test_scope_config_normalizes_lists_and_uses_default_excludes() -> None:
    scope = KBScopeConfig(
        vault_root="/vault",
        include=[" notes/** ", "daily/*.md", "notes/**", ""],
        exclude=[".obsidian/**", " notes/private/** ", ".obsidian/**"],
    )

    assert scope.vault_root == "/vault"
    assert scope.include == ("daily/*.md", "notes/**")
    assert scope.exclude == (".obsidian/**", "notes/private/**")
    assert ".obsidian/**" in scope.default_excludes


def test_operation_counters_require_all_fields() -> None:
    with pytest.raises(ValidationError):
        KBOperationCounters(indexed=0, updated=0, removed=0, skipped=0, errors=0)

    counters = KBOperationCounters(
        read=1,
        indexed=2,
        updated=3,
        removed=4,
        skipped=5,
        errors=6,
    )
    assert counters.model_dump() == {
        "read": 1,
        "indexed": 2,
        "updated": 3,
        "removed": 4,
        "skipped": 5,
        "errors": 6,
    }


def test_operation_summary_dump_and_json_are_deterministic() -> None:
    summary = KBOperationSummary(
        operation="ingest",
        dry_run=True,
        duration_seconds=1.25,
        counters=KBOperationCounters(
            read=10,
            indexed=8,
            updated=0,
            removed=0,
            skipped=2,
            errors=1,
        ),
        scope=KBScopeConfig(
            vault_root="/vault",
            include=["zeta/**", "alpha/**"],
            exclude=["tmp/**", ".obsidian/**"],
            default_excludes=[".DS_Store", ".obsidian/**"],
        ),
        diagnostics=[
            KBFileDiagnostic(
                path="notes/error.md",
                category="parse_error",
                recovery_hint="Corrija o markdown e execute `aurora kb update`.",
            )
        ],
    )

    expected = {
        "operation": "ingest",
        "dry_run": True,
        "duration_seconds": 1.25,
        "counters": {
            "read": 10,
            "indexed": 8,
            "updated": 0,
            "removed": 0,
            "skipped": 2,
            "errors": 1,
        },
        "scope": {
            "vault_root": "/vault",
            "include": ("alpha/**", "zeta/**"),
            "exclude": (".obsidian/**", "tmp/**"),
            "default_excludes": (".DS_Store", ".obsidian/**"),
        },
        "diagnostics": (
            {
                "path": "notes/error.md",
                "category": "parse_error",
                "recovery_hint": "Corrija o markdown e execute `aurora kb update`.",
            },
        ),
    }

    assert summary.model_dump() == expected
    assert summary.to_json() == summary.to_json()
