from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import re
from typing import Literal

from aurora.kb.contracts import DEFAULT_SCOPE_EXCLUDES, KBScopeConfig


Reason = Literal["included", "excluded", "not_included", "outside_vault"]

_GLOB_CHARS = set("*?[")
_WINDOWS_DRIVE_ABS = re.compile(r"^[A-Za-z]:[\\/]")


class ScopeConfigurationError(ValueError):
    """Raised when include/exclude rules cannot be safely applied."""


class ScopeNoMatchesError(ValueError):
    """Raised when include rules yield zero eligible files."""


@dataclass(frozen=True)
class ScopeDecision:
    """Result of checking whether a relative path is eligible for indexing."""

    path: str
    allowed: bool
    reason: Reason
    matched_include: str | None = None
    matched_exclude: str | None = None


@dataclass(frozen=True)
class ScopePreviewItem:
    """Skipped path metadata for dry-run previews."""

    path: str
    reason: Reason
    matched_rule: str | None = None


@dataclass(frozen=True)
class ScopePreview:
    """Effective scope details used by dry-run command output."""

    vault_root: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    default_excludes: tuple[str, ...]
    effective_excludes: tuple[str, ...]
    eligible: tuple[str, ...]
    skipped: tuple[ScopePreviewItem, ...]


@dataclass(frozen=True)
class ScopeRules:
    """Case-sensitive include/exclude evaluator for vault-relative paths."""

    vault_root: Path
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    default_excludes: tuple[str, ...]
    effective_excludes: tuple[str, ...]

    @classmethod
    def from_config(cls, config: KBScopeConfig) -> ScopeRules:
        vault_root = Path(config.vault_root).expanduser().resolve()
        include = tuple(config.include)
        exclude = tuple(config.exclude)
        default_excludes = tuple(config.default_excludes or DEFAULT_SCOPE_EXCLUDES)

        for rule in include:
            _validate_rule_bound_to_vault(
                rule=rule,
                vault_root=vault_root,
                rule_group="include",
            )
        for rule in (*exclude, *default_excludes):
            _validate_rule_bound_to_vault(
                rule=rule,
                vault_root=vault_root,
                rule_group="exclude",
            )

        effective_excludes = tuple(dict.fromkeys((*default_excludes, *exclude)))
        return cls(
            vault_root=vault_root,
            include=include,
            exclude=exclude,
            default_excludes=default_excludes,
            effective_excludes=effective_excludes,
        )

    def evaluate(self, path: str | Path) -> ScopeDecision:
        normalized = _normalize_candidate_path(path=path, vault_root=self.vault_root)
        if normalized is None:
            return ScopeDecision(path=str(path), allowed=False, reason="outside_vault")

        matched_exclude = _match_first(normalized, self.effective_excludes)
        if matched_exclude:
            return ScopeDecision(
                path=normalized,
                allowed=False,
                reason="excluded",
                matched_exclude=matched_exclude,
            )

        if self.include:
            matched_include = _match_first(normalized, self.include)
            if matched_include is None:
                return ScopeDecision(path=normalized, allowed=False, reason="not_included")
            return ScopeDecision(
                path=normalized,
                allowed=True,
                reason="included",
                matched_include=matched_include,
            )

        return ScopeDecision(path=normalized, allowed=True, reason="included")

    def should_index(self, path: str | Path) -> bool:
        return self.evaluate(path).allowed

    def preview(self, candidates: list[str] | tuple[str, ...]) -> ScopePreview:
        eligible: list[str] = []
        skipped: list[ScopePreviewItem] = []

        for candidate in candidates:
            decision = self.evaluate(candidate)
            if decision.allowed:
                eligible.append(decision.path)
                continue

            matched_rule = decision.matched_exclude or decision.matched_include
            skipped.append(
                ScopePreviewItem(
                    path=decision.path,
                    reason=decision.reason,
                    matched_rule=matched_rule,
                )
            )

        if self.include and not eligible:
            raise ScopeNoMatchesError(
                "Nenhum arquivo correspondeu aos includes configurados. "
                "Revise os padroes e valide com `aurora kb ingest <vault_path> --dry-run`."
            )

        return ScopePreview(
            vault_root=self.vault_root.as_posix(),
            include=self.include,
            exclude=self.exclude,
            default_excludes=self.default_excludes,
            effective_excludes=self.effective_excludes,
            eligible=tuple(sorted(eligible)),
            skipped=tuple(sorted(skipped, key=lambda item: item.path)),
        )


def _validate_rule_bound_to_vault(
    *,
    rule: str,
    vault_root: Path,
    rule_group: str,
) -> None:
    normalized = rule.strip().replace("\\", "/")
    if not normalized:
        return

    if _is_absolute_pattern(normalized):
        raise ScopeConfigurationError(
            f"Regra `{rule_group}` fora do vault: `{rule}`. "
            f"Use caminhos relativos dentro de `{vault_root.as_posix()}` "
            "e valide com `aurora kb ingest <vault_path> --dry-run`."
        )

    static_prefix = _extract_static_prefix(normalized)
    resolved = (vault_root / static_prefix).resolve()
    if not resolved.is_relative_to(vault_root):
        raise ScopeConfigurationError(
            f"Regra `{rule_group}` fora do vault: `{rule}`. "
            f"Use caminhos relativos dentro de `{vault_root.as_posix()}` "
            "e valide com `aurora kb ingest <vault_path> --dry-run`."
        )


def _extract_static_prefix(pattern: str) -> Path:
    parts = [part for part in PurePosixPath(pattern).parts if part not in ("", ".")]
    static_parts: list[str] = []
    for part in parts:
        if any(char in part for char in _GLOB_CHARS):
            break
        static_parts.append(part)

    if not static_parts:
        return Path(".")
    return Path(*static_parts)


def _is_absolute_pattern(pattern: str) -> bool:
    return pattern.startswith("/") or bool(_WINDOWS_DRIVE_ABS.match(pattern))


def _normalize_candidate_path(*, path: str | Path, vault_root: Path) -> str | None:
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.expanduser().resolve()
        if not resolved.is_relative_to(vault_root):
            return None
        return resolved.relative_to(vault_root).as_posix()

    normalized = str(path).replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return None
    pure_path = PurePosixPath(normalized)
    if any(part == ".." for part in pure_path.parts):
        return None
    return pure_path.as_posix()


def _match_first(relative_path: str, rules: tuple[str, ...]) -> str | None:
    for rule in rules:
        if fnmatchcase(relative_path, rule):
            return rule
    return None
