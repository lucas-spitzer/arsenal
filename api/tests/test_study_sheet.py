from __future__ import annotations

from typing import Any

import fitz
import pytest

from app.mathesys.study_sheet.generate import (
    StudySheetError,
    StudySheetFitError,
    StudySheetSource,
    generate_study_sheet,
)
from app.mathesys.study_sheet.html import sanitize_body_html, wrap_sheet_html
from app.mathesys.study_sheet.prompts import SYSTEM_PROMPT
from app.services.llm.base import LLMCompletionResult


def _pdf_bytes(pages: int) -> bytes:
    document = fitz.open()
    for _ in range(pages):
        document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


class ScriptedPrinter:
    def __init__(self, page_counts: list[int]) -> None:
        self.page_counts = list(page_counts)
        self.htmls: list[str] = []

    def print_html(self, html: str) -> bytes:
        self.htmls.append(html)
        if not self.page_counts:
            raise AssertionError("Printer asked for more PDFs than scripted.")
        return _pdf_bytes(self.page_counts.pop(0))

    def page_count(self, pdf: bytes) -> int:
        document = fitz.open(stream=pdf, filetype="pdf")
        try:
            return int(document.page_count)
        finally:
            document.close()


class ScriptedCompleter:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.prompts: list[str] = []

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> LLMCompletionResult:
        del system_prompt, model
        self.prompts.append(user_prompt)
        if not self.payloads:
            raise AssertionError("Completer asked for more completions than scripted.")
        return LLMCompletionResult(
            content=self.payloads.pop(0),
            model="gemini-3.7-flash",
            provider="google",
            token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )

    def complete_json_with_document(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        document_bytes: bytes,
        document_mime: str,
        model: str | None = None,
    ) -> LLMCompletionResult:
        del document_bytes, document_mime
        return self.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
        )


def test_sanitize_strips_script_and_keeps_lists() -> None:
    cleaned = sanitize_body_html(
        '<section class="section"><h2>Rules</h2>'
        "<ul class=\"list-compact\"><li>Treat every weapon as loaded.</li></ul>"
        '<script>alert(1)</script>'
        '<img src="http://evil.example/x.png" />'
        "</section>"
    )
    assert "script" not in cleaned.lower()
    assert "img" not in cleaned.lower()
    assert "Treat every weapon as loaded." in cleaned
    assert 'class="section"' in cleaned
    assert 'class="list-compact"' in cleaned


def test_wrap_includes_owned_chrome_and_print_css() -> None:
    html = wrap_sheet_html(title="OCS Review", body_html="<p>BAMCIS</p>")
    assert "Arsenal study sheet" in html
    assert "OCS Review" in html
    assert "@page" in html
    assert "size: letter" in html
    assert "#940000" in html


def test_prompt_does_not_overfit_to_numbered_lists() -> None:
    assert "Do not force numbered lists onto prose" in SYSTEM_PROMPT
    assert "HTML blocks" in SYSTEM_PROMPT
    assert "Do not add facts" in SYSTEM_PROMPT


def test_generate_accepts_one_or_two_pages() -> None:
    source = StudySheetSource(
        filename="ocs.md",
        mime_type="text/markdown",
        content=b"## Orders\n\n1. Take charge of this post.",
    )
    result = generate_study_sheet(
        source=source,
        completer=ScriptedCompleter(
            [{"title": "OCS", "body_html": "<section class='section'><h2>Orders</h2><ol><li>Take charge.</li></ol></section>"}]
        ),
        printer=ScriptedPrinter([2]),
    )
    assert result.page_count == 2
    assert result.attempt_count == 1
    assert "Orders" in result.html


def test_generate_prose_html_is_not_forced_into_lists() -> None:
    source = StudySheetSource(
        filename="essay.md",
        mime_type="text/markdown",
        content=b"A long chapter about terrain analysis and why cover matters.",
    )
    result = generate_study_sheet(
        source=source,
        completer=ScriptedCompleter(
            [
                {
                    "title": "Terrain",
                    "body_html": "<section class='section'><h2>Cover</h2><p>Cover stops enemy fire. Concealment only hides.</p></section>",
                }
            ]
        ),
        printer=ScriptedPrinter([1]),
    )
    assert "<ol" not in result.html
    assert "Cover stops enemy fire." in result.html
    assert result.page_count == 1


def test_generate_retries_then_fails_when_over_two_pages() -> None:
    source = StudySheetSource(
        filename="manual.md",
        mime_type="text/markdown",
        content=b"# Manual\n\n" + b"paragraph\n" * 20,
    )
    completer = ScriptedCompleter(
        [
            {"title": "Manual", "body_html": "<p>too long one</p>"},
            {"title": "Manual", "body_html": "<p>too long two</p>"},
            {"title": "Manual", "body_html": "<p>too long three</p>"},
        ]
    )
    with pytest.raises(StudySheetFitError, match="3 pages"):
        generate_study_sheet(
            source=source,
            completer=completer,
            printer=ScriptedPrinter([3, 3, 3]),
            max_attempts=3,
        )
    assert "budget is 2 pages" in completer.prompts[1]


def test_generate_retry_can_succeed() -> None:
    source = StudySheetSource(
        filename="manual.md",
        mime_type="text/markdown",
        content=b"# Manual\n\nLots of text.",
    )
    result = generate_study_sheet(
        source=source,
        completer=ScriptedCompleter(
            [
                {"title": "Manual", "body_html": "<p>long</p>"},
                {"title": "Manual", "body_html": "<p>short</p>"},
            ]
        ),
        printer=ScriptedPrinter([3, 2]),
        max_attempts=3,
    )
    assert result.page_count == 2
    assert result.attempt_count == 2


def test_weasyprint_letter_page_count() -> None:
    pytest.importorskip("weasyprint")
    from app.mathesys.study_sheet.printer import WeasyPrintPdfPrinter

    html = wrap_sheet_html(
        title="Print check",
        body_html="<section class='section'><h2>Cover</h2><p>Short body.</p></section>",
    )
    printer = WeasyPrintPdfPrinter()
    pdf = printer.print_html(html)
    assert printer.page_count(pdf) == 1
    assert pdf.startswith(b"%PDF")


def test_generate_rejects_empty_body() -> None:
    source = StudySheetSource(
        filename="empty.md",
        mime_type="text/markdown",
        content=b"# Empty",
    )
    with pytest.raises(StudySheetError, match="HTML"):
        generate_study_sheet(
            source=source,
            completer=ScriptedCompleter([{"title": "Empty", "body_html": "<script>x</script>"}]),
            printer=ScriptedPrinter([1]),
        )
