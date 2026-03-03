from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aurora.kb.scope import ScopeRules


@dataclass(frozen=True)
class ScanSkippedPath:
    """A vault-relative path skipped during scanning with a privacy-safe reason."""

    path: str
    reason: str


@dataclass(frozen=True)
class ScanResult:
    """Deterministic scanner output used by ingest/update/rebuild flows."""

    indexed: tuple[str, ...]
    skipped: tuple[ScanSkippedPath, ...]


def scan_markdown_files(*, vault_root: Path | str, scope: ScopeRules) -> ScanResult:
    """Enumerate in-scope markdown files without reading note content."""
    root = Path(vault_root).expanduser().resolve()
    indexed: list[str] = []
    skipped: list[ScanSkippedPath] = []

    for candidate in root.rglob("*"):
        if candidate.is_dir():
            continue

        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink():
            skipped.append(ScanSkippedPath(path=relative, reason="symlink"))
            continue

        if candidate.suffix != ".md":
            skipped.append(ScanSkippedPath(path=relative, reason="extension"))
            continue

        decision = scope.evaluate(relative)
        if decision.allowed:
            indexed.append(relative)
            continue

        if (
            decision.reason == "excluded"
            and decision.matched_exclude in scope.default_excludes
        ):
            reason = "hidden_system_exclusion"
        else:
            reason = "scope"
        skipped.append(ScanSkippedPath(path=relative, reason=reason))

    return ScanResult(
        indexed=tuple(sorted(indexed)),
        skipped=tuple(sorted(skipped, key=lambda item: item.path)),
    )

