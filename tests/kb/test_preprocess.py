from __future__ import annotations

from aurora.kb.preprocess import preprocess_markdown


def test_preprocess_keeps_text_unchanged_when_no_templater_snippets_exist() -> None:
    source = "# Nota\nConteudo normal.\n"

    result = preprocess_markdown(relative_path="notes/plain.md", markdown_text=source)

    assert result.relative_path == "notes/plain.md"
    assert result.cleaned_text == source
    assert result.cleaned_snippet_count == 0
    assert result.cleaned_span_count == 0
    assert result.cleaned_spans == ()


def test_preprocess_removes_multiple_templater_blocks() -> None:
    source = "Linha 1\n<% tp.date.now() %>\nLinha 2\n<%* tR += \"OK\" %>\n"

    result = preprocess_markdown(relative_path="notes/multi.md", markdown_text=source)

    assert result.cleaned_text == "Linha 1\n\nLinha 2\n\n"
    assert result.cleaned_snippet_count == 2
    assert result.cleaned_span_count == 2
    assert len(result.cleaned_spans) == 2


def test_preprocess_removes_related_templater_variants_only() -> None:
    source = (
        "Header\n"
        "<%_ if (true) { _%>\n"
        "body\n"
        "<%-* tR += \"x\" -%>\n"
        "Footer\n"
    )

    result = preprocess_markdown(relative_path="notes/variants.md", markdown_text=source)

    assert result.cleaned_text == "Header\n\nbody\n\nFooter\n"
    assert result.cleaned_snippet_count == 2
    assert result.cleaned_span_count == 2
