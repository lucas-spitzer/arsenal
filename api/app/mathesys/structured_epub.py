"""Render the structured Book to EPUB.

The Create EBook stage reuses the existing app.mathesys.epub_builder.build_epub
(already covered by tests). This module only converts the Book's markdown body
into per-chapter XHTML bodies, preserving inline emphasis (*italic* -> <em>,
**bold** -> <strong>) that the plain-text segment path would otherwise lose, and
emitting exactly the three KEEP types: <h1> chapter, <h2> section, <p> body.
"""
from __future__ import annotations

import html
import re
from typing import Any

from app.intellex.structuring.chapter_titles import display_chapter_title
from app.intellex.structuring.models import Book

_SUP_RE = re.compile(r"<sup>.*?</sup>", re.IGNORECASE | re.DOTALL)
_UNICODE_SUP_RE = re.compile(r"[\u00b2\u00b3\u00b9\u2070\u2074-\u2079]+")
_STRONG_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_EM_RE = re.compile(r"\*(.+?)\*", re.DOTALL)


def _md_to_html(md: str) -> str:
    text = _SUP_RE.sub("", md)
    text = _UNICODE_SUP_RE.sub("", text)
    text = html.escape(text, quote=False)
    text = _STRONG_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_RE.sub(r"<em>\1</em>", text)
    return re.sub(r"\s+", " ", text).strip()


def book_to_epub_chapters(book: Book) -> list[dict[str, Any]]:
    """Return [{title, xhtml_body}] for app.mathesys.epub_builder.build_epub."""
    chapters: list[dict[str, Any]] = []
    for chapter in book.chapters:
        title = display_chapter_title(chapter.title)
        parts = [f"<h1>{html.escape(title)}</h1>"]
        for para in chapter.intro:
            body = _md_to_html(para.md)
            if body:
                parts.append(f"<p>{body}</p>")
        for section in chapter.sections:
            parts.append(f"<h2>{html.escape(section.title)}</h2>")
            for para in section.body:
                body = _md_to_html(para.md)
                if body:
                    parts.append(f"<p>{body}</p>")
        chapters.append({"title": title, "xhtml_body": "".join(parts)})
    return chapters
