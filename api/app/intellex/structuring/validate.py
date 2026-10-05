"""Stage: VALIDATE (pdf-structure-validation).

The earlier stages decide structure from the LlamaParse output alone; this stage
independently checks that decision against the source PDF so a parsing quirk
can't silently corrupt the book. It runs fully automatically and RAISES on
failure so a bad run stops loudly instead of shipping a broken EPUB.

Checks (by re-reading the PDF text layer with PyMuPDF):
  1. Every chapter/section title appears on or near its recorded page.
     A long heading may differ by one letter in a single word. That
     spelling is replaced with the PDF's.
  2. No known front/back-matter label (FOREWORD, NOTES, GLOSSARY, INDEX...)
     survives as a chapter or section.
  3. The body carries real text.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

import fitz  # PyMuPDF

from app.intellex.structuring.models import Book, Chapter, Section

_FRONT_BACK_LABELS = re.compile(
    r"^(table of contents|contents|foreword|preface|dedication|acknowledge?ments?|"
    r"notes?|endnotes?|glossary|bibliography|references?|index|appendix\b|epilogue|"
    r"afterword|about the author)",
    re.IGNORECASE,
)

# LlamaParse page numbers and the PDF's own page indices can drift by a page.
PAGE_SLACK = 2
# One substituted letter is a parser typo ("Roughhead" / "Roughead").
# Shorter headings stay exact so a changed chapter number still fails.
_MIN_TOKENS_FOR_TYPO = 4
_MIN_TYPO_TOKEN_LEN = 6
_SUP_TAG_RE = re.compile(r"<sup>.*?</sup>", re.IGNORECASE | re.DOTALL)
_WORD_RE = re.compile(r"\S+")
_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")


class StructureValidationError(RuntimeError):
    """Raised when the structured book disagrees with the source PDF."""


def _norm(text: str) -> str:
    text = _SUP_TAG_RE.sub("", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def layer_norm(text: str) -> str:
    """Normalize PDF or parser text for an image-transcription check.

    A hyphen at a line break is joined away, so a word split across lines
    still matches the parser's dehyphenated text.
    """
    text = re.sub(r"-\s*\n\s*", "", text)
    return _norm(text)


def pdf_text_layer(pdf_bytes: bytes) -> list[str]:
    """Return one normalized string per PDF page, index 0 for page 1."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [layer_norm(page.get_text("text")) for page in doc]
    finally:
        doc.close()


def _pdf_pages(pdf_bytes: bytes) -> list[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [_norm(page.get_text("text")) for page in doc]
    finally:
        doc.close()


def _page_bounds(page: int | None, page_count: int) -> tuple[int, int]:
    lo = max(0, (page or 1) - 1 - PAGE_SLACK)
    hi = min(page_count, (page or 1) - 1 + PAGE_SLACK + 1)
    return lo, hi


def _edit_distance(left: str, right: str, limit: int = 1) -> int:
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for index, char in enumerate(left, start=1):
        current = [index]
        row_min = index
        for other_index, other in enumerate(right, start=1):
            cost = 0 if char == other else 1
            current.append(min(
                previous[other_index] + 1,
                current[other_index - 1] + 1,
                previous[other_index - 1] + cost,
            ))
            row_min = min(row_min, current[-1])
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _one_letter_off(left: str, right: str) -> bool:
    if left == right or left.isdigit() or right.isdigit():
        return False
    if len(left) < _MIN_TYPO_TOKEN_LEN or len(right) < _MIN_TYPO_TOKEN_LEN:
        return False
    return _edit_distance(left, right) <= 1


def _typo_window(needle_tokens: list[str], haystack_tokens: list[str]) -> list[str] | None:
    """Return the haystack tokens aligned to the title, if only one word is a typo."""
    if len(needle_tokens) < _MIN_TOKENS_FOR_TYPO:
        return None
    width = len(needle_tokens)
    for start in range(0, len(haystack_tokens) - width + 1):
        window = haystack_tokens[start:start + width]
        mismatches = [
            (left, right)
            for left, right in zip(needle_tokens, window, strict=True)
            if left != right
        ]
        if len(mismatches) == 1 and _one_letter_off(*mismatches[0]):
            return window
    return None


def _contains_title(needle: str, haystack: str) -> bool:
    if needle in haystack:
        return True
    return _typo_window(needle.split(), haystack.split()) is not None


def _match_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _replace_typo_word(title: str, bad: str, good: str) -> str:
    found = next(
        (match for match in _WORD_RE.finditer(title) if _norm(match.group(0)) == bad),
        None,
    )
    if found is None:
        return title
    word = found.group(0)
    core = _LETTER_RUN_RE.search(word)
    if core is None:
        return title
    fixed_core = _match_case(core.group(0), good)
    fixed_word = word[:core.start()] + fixed_core + word[core.end():]
    return title[:found.start()] + fixed_word + title[found.end():]


def _snap_title(title: str, needle: str, haystack: str) -> str | None:
    window = _typo_window(needle.split(), haystack.split())
    if window is None:
        return None
    fixed = title
    for left, right in zip(needle.split(), window, strict=True):
        if left != right:
            fixed = _replace_typo_word(fixed, left, right)
    return fixed


def _correct_title(title: str, page: int | None, pages: list[str]) -> str:
    needle = _norm(title)
    if not needle:
        return title
    lo, hi = _page_bounds(page, len(pages))
    for index in range(lo, hi):
        if needle in pages[index]:
            return title
        fixed = _snap_title(title, needle, pages[index])
        if fixed is not None:
            return fixed
    return title


def _near(title: str, page: int | None, pages: list[str]) -> bool:
    needle = _norm(title)
    if not needle:
        return True
    lo, hi = _page_bounds(page, len(pages))
    return any(_contains_title(needle, pages[index]) for index in range(lo, hi))


def _anywhere(title: str, pages: list[str]) -> bool:
    needle = _norm(title)
    return any(_contains_title(needle, page) for page in pages) if needle else True


def validate_against_pdf(book: Book, pdf_bytes: bytes) -> dict[str, Any]:
    """Return a report dict; raise StructureValidationError on hard failure."""
    pages = _pdf_pages(pdf_bytes)
    errors: list[str] = []
    warnings: list[str] = []
    title_corrections: list[dict[str, Any]] = []

    if not book.chapters:
        raise StructureValidationError("Structured book has no chapters.")

    def adopt_pdf_spelling(kind: str, heading: Chapter | Section) -> None:
        corrected = _correct_title(heading.title, heading.page, pages)
        if corrected == heading.title:
            return
        title_corrections.append({
            "kind": kind,
            "page": heading.page,
            "from": heading.title,
            "to": corrected,
        })
        heading.title = corrected

    for c in book.chapters:
        adopt_pdf_spelling("chapter", c)
        for s in c.sections:
            adopt_pdf_spelling("section", s)

    for c in book.chapters:
        if _FRONT_BACK_LABELS.match(c.title.strip()):
            errors.append(f"Front/back-matter heading leaked as a CHAPTER: {c.title!r}")
        if not _near(c.title, c.page, pages):
            (warnings if _anywhere(c.title, pages) else errors).append(
                f"Chapter {c.title!r} not found near p{c.page}"
                + ("" if _anywhere(c.title, pages) else " in the PDF at all")
            )
        for s in c.sections:
            if _FRONT_BACK_LABELS.match(s.title.strip()):
                errors.append(f"Front/back-matter heading leaked as a SECTION: {s.title!r}")
            if not _near(s.title, s.page, pages):
                (warnings if _anywhere(s.title, pages) else errors).append(
                    f"Section {s.title!r} not found near p{s.page}"
                    + ("" if _anywhere(s.title, pages) else " in the PDF at all")
                )

    n_headings = sum(1 + len(c.sections) for c in book.chapters)
    body = book.body_paragraph_count()
    if body < max(3, n_headings):
        errors.append(f"Body looks too thin ({body} paragraphs for {n_headings} headings).")

    report = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "title_corrections": title_corrections,
        "checked": {
            "chapters": len(book.chapters),
            "sections": sum(len(c.sections) for c in book.chapters),
            "body_paragraphs": body,
            "pdf_pages": len(pages),
        },
    }
    if errors:
        raise StructureValidationError(
            "Structure validation failed: " + "; ".join(errors)
        )
    return report
