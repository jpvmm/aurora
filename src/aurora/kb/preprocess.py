from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


TEMPLATER_SNIPPET_PATTERN = re.compile(r"<%[-_+*~]*[\s\S]*?[-_+*~]?%>")


@dataclass(frozen=True)
class PreprocessResult:
    """Output contract reused by ingest/update/rebuild preprocessing steps."""

    relative_path: str
    cleaned_text: str
    cleaned_snippet_count: int
    cleaned_span_count: int
    cleaned_spans: tuple[tuple[int, int], ...]


def preprocess_markdown(*, relative_path: str, markdown_text: str) -> PreprocessResult:
    """Remove templater snippets and report privacy-safe cleanup metadata."""
    normalized_relative_path = _normalize_relative_path(relative_path)
    spans: list[tuple[int, int]] = []
    cleaned_chunks: list[str] = []
    last_end = 0

    for match in TEMPLATER_SNIPPET_PATTERN.finditer(markdown_text):
        start, end = match.span()
        spans.append((start, end))
        cleaned_chunks.append(markdown_text[last_end:start])
        last_end = end

    if not spans:
        return PreprocessResult(
            relative_path=normalized_relative_path,
            cleaned_text=markdown_text,
            cleaned_snippet_count=0,
            cleaned_span_count=0,
            cleaned_spans=(),
        )

    cleaned_chunks.append(markdown_text[last_end:])
    cleaned_text = "".join(cleaned_chunks)
    cleaned_spans = tuple(spans)
    return PreprocessResult(
        relative_path=normalized_relative_path,
        cleaned_text=cleaned_text,
        cleaned_snippet_count=len(cleaned_spans),
        cleaned_span_count=len(cleaned_spans),
        cleaned_spans=cleaned_spans,
    )


def _normalize_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return PurePosixPath(normalized).as_posix()

