from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HuggingFaceTarget:
    """Parsed Hugging Face target in Aurora locked format."""

    repo_id: str
    filename: str
    source: str


class ModelSourceValidationError(ValueError):
    """Raised when model source input does not match required format."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        details = "\n".join(f"- {error}" for error in self.errors)
        message = (
            "Fonte de modelo inválida.\n"
            f"{details}\n"
            "Use: aurora model set --source repo/model:arquivo.gguf"
        )
        super().__init__(message)


def parse_hf_target(source: str) -> HuggingFaceTarget:
    """Parse and validate an HF source in `repo/model:arquivo.gguf` format."""
    normalized = source.strip()
    errors: list[str] = []

    if not normalized:
        errors.append("Informe uma origem no formato repo/model:arquivo.gguf.")
        raise ModelSourceValidationError(errors)

    if ":" not in normalized:
        errors.append("Use o formato repo/model:arquivo.gguf com um único ':'.")
        raise ModelSourceValidationError(errors)

    if normalized.count(":") != 1:
        errors.append("Use o formato repo/model:arquivo.gguf com um único ':'.")

    repo_id, filename = normalized.split(":", 1)
    _validate_repo(repo_id, errors)
    _validate_filename(filename, errors)

    if errors:
        raise ModelSourceValidationError(errors)

    return HuggingFaceTarget(repo_id=repo_id, filename=filename, source=normalized)


def _validate_repo(repo_id: str, errors: list[str]) -> None:
    parts = repo_id.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        errors.append("Informe o repo no formato org/modelo (ex.: Qwen/Qwen3-8B-GGUF).")
        return

    for part in parts:
        if part.startswith("-") or part.endswith("-"):
            errors.append("O repo não pode iniciar ou terminar com '-'.")
            return


def _validate_filename(filename: str, errors: list[str]) -> None:
    if not filename:
        errors.append("Informe o nome do arquivo GGUF após ':'.")
        return

    if "/" in filename or "\\" in filename:
        errors.append("Informe somente o nome do arquivo GGUF, sem diretórios.")

    if not filename.lower().endswith(".gguf"):
        errors.append("O arquivo precisa terminar com .gguf.")
