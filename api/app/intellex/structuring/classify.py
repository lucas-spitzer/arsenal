"""Stage: STRUCTURE (document-structure-classify).

Turn the trimmed element stream into a clean chapter/section/body Book. This is
where the three KEEP rules are applied and where chapter grouping happens -- so
it replaces the old deconstruct-document step as well as the structural half of
prepare-document.

  H1 chapters: a heading matching the chapter pattern ("Chapter 1",
      "CHAPTER ONE", "Chapter IV"). A bare marker is merged with following
      title-line headings (and a short title-case text line, when LlamaParse
      failed to mark it as a heading) until the first ALL-CAPS subsection.
      Doctrine books keep the familiar "Chapter N Title" form; multi-line
      academic titles join with a colon.
  H2 sections: EVERY other in-body heading, regardless of LlamaParse `level`
      (which is too noisy to separate chapters from sections). A heading with
      no body before the next title-case line is treated as one section
      ("OPLAN 316: When the Cold War Almost Went Hot"), matching doctrine
      vignette titles like "ANZIO: A MODEL OF TACTICAL INDECISIVENESS".
  Body: every `text` element in reading order, attached to its section (or to
      the chapter intro before the first section). Text split by a PDF page
      boundary or an omitted visual is rejoined conservatively. Footnote/citation
      superscript markers are stripped by default because they point into a
      removed notes section and would otherwise dangle. Page-level footnote
      bodies (LlamaParse `footnote` layout, or a leading <sup>n</sup> marker),
      "Source:" citation callouts, and unlabeled photo-credit lines after a
      dropped figure are omitted the same way captions are, so they cannot
      appear in the EPUB or glue themselves onto the previous sentence.
      Chapter epigraphs stay as separate paragraphs (quote vs attribution)
      so EPUB spacing is preserved.

Non-text, non-heading elements (lists, code/diagrams, images) are not one of the
three KEEP types and are dropped, with counts reported. Standalone captions for
those omitted visuals are dropped as well; inline prose references are retained.
Omitted visuals and their captions are transparent to paragraph continuity so a
sentence interrupted by a figure can be rejoined.
"""
from __future__ import annotations

import re

from app.intellex.heading_classification import is_doctrinal_subsection_heading
from app.intellex.structuring.boundaries import DEFAULT_CHAPTER_RE, is_chapter_marker
from app.intellex.structuring.models import Book, Chapter, Element, Paragraph, Section

_SUP_TAG_RE = re.compile(r"<sup>.*?</sup>", re.IGNORECASE | re.DOTALL)
_UNICODE_SUP_RE = re.compile(r"[\u00b2\u00b3\u00b9\u2070\u2074-\u2079]+")
_VISUAL_CAPTION_RE = re.compile(
    r"^\s*(?:figure|fig\.?|table|tbl\.?|plate|exhibit|chart|diagram|"
    r"illustration|map|photo)\s+(?:\d+|[ivxlcdm]+)\s*(?:[.:\-–—]|$)",
    re.IGNORECASE,
)
_PARAGRAPH_END_RE = re.compile(r"""[.!?]["'”’)\]]*\s*$""")
_TRAILING_EMPHASIS_RE = re.compile(r"[*_]+$")
_LEADING_EMPHASIS_RE = re.compile(r"^[*_]+")
_ATTRIBUTION_LINE_RE = re.compile(r"^\s*[—–\-]\s*\S")
_ATTRIBUTION_SPLIT_RE = re.compile(r"\n+(?=\s*[*_]*[—–\-]\s*\S)")
_MAX_CAPTION_LENGTH = 200
_MAX_ORPHAN_TITLE_LENGTH = 90
_MAX_ORPHAN_TITLE_WORDS = 14
_ORPHAN_TITLE_START_RE = re.compile(r"""^["“'‘]?[A-Z]""")
_TITLE_END_PUNCT_RE = re.compile(r"""[.:?!]["“'’”]*$""")
_SMALL_TITLE_WORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at",
    "by", "from", "after", "into", "with",
})
_OMITTED_VISUAL_TYPES = frozenset(
    {"image", "figure", "diagram", "chart", "illustration", "photo", "code"}
)
_VISUAL_LAYOUT_LABELS = frozenset(
    {"image", "figure", "diagram", "chart", "illustration", "photo", "caption", "table"}
)
_NON_SECTION_LAYOUT_LABELS = _VISUAL_LAYOUT_LABELS | {
    "header",
    "footer",
    "footnote",
    "endnote",
}
_FOOTNOTE_LAYOUT_LABELS = frozenset({"footnote", "endnote"})
_FOOTNOTE_START_RE = re.compile(r"^\s*<sup>\s*\d+\s*</sup>", re.IGNORECASE)
_SOURCE_NOTE_RE = re.compile(r"^\s*[*_]*Source\s*:", re.IGNORECASE)
_MAX_VISUAL_CREDIT_WORDS = 20
_MAX_VISUAL_CREDIT_LENGTH = 160
_FRAGMENTED_VISUAL_MAX_CONFIDENCE = 0.5
_FRAGMENTED_VISUAL_MIN_BOXES = 4


def strip_footnote_markers(md: str) -> str:
    out = _SUP_TAG_RE.sub("", md)
    out = _UNICODE_SUP_RE.sub("", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return out.strip()


def is_standalone_visual_caption(text: str) -> bool:
    """Return whether a short text item is a label for an omitted visual.

    Requiring the identifier at the start and punctuation after its number
    deliberately preserves prose such as "As shown in Figure 1..." and
    "Figure 1 shows...".
    """
    stripped = text.strip()
    return len(stripped) <= _MAX_CAPTION_LENGTH and bool(_VISUAL_CAPTION_RE.match(stripped))


def _looks_like_fragmented_visual_text(element: Element) -> bool:
    """Detect OCR assembled from many low-confidence labels inside a visual."""
    return (
        element.type == "text"
        and set(element.layout_labels) == {"text"}
        and element.max_layout_confidence is not None
        and element.max_layout_confidence <= _FRAGMENTED_VISUAL_MAX_CONFIDENCE
        and element.layout_fragment_count >= _FRAGMENTED_VISUAL_MIN_BOXES
    )


def _fragmented_visual_pages(elements: list[Element]) -> set[int | None]:
    """Pages where a generic heading fronts fragmented map/diagram OCR."""
    ambiguous_heading_pages = {
        element.page
        for element in elements
        if element.type == "heading" and set(element.layout_labels) == {"text"}
    }
    return {
        element.page
        for element in elements
        if element.page in ambiguous_heading_pages
        and _looks_like_fragmented_visual_text(element)
    }


def _explicit_visual_pages(elements: list[Element]) -> set[int | None]:
    return {
        element.page
        for element in elements
        if element.type in _OMITTED_VISUAL_TYPES
        or set(element.layout_labels) & _VISUAL_LAYOUT_LABELS
    }


def _is_visual_description(
    element: Element,
    *,
    fragmented_visual_pages: set[int | None],
    explicit_visual_pages: set[int | None],
) -> bool:
    labels = set(element.layout_labels)
    visual_labels = labels & _VISUAL_LAYOUT_LABELS
    nonvisual_labels = labels - _VISUAL_LAYOUT_LABELS
    if visual_labels and not nonvisual_labels:
        return True
    if "image" in visual_labels and "paragraph_title" in nonvisual_labels:
        return True
    if (
        visual_labels
        and element.min_layout_confidence is not None
        and element.min_layout_confidence <= _FRAGMENTED_VISUAL_MAX_CONFIDENCE
    ):
        return True
    if (
        not labels
        and element.page in explicit_visual_pages
        and len(element.text.split()) <= 8
        and not _paragraph_looks_complete(element.text)
    ):
        return True
    return (
        element.page in fragmented_visual_pages
        and _looks_like_fragmented_visual_text(element)
    )


def _is_page_footnote(element: Element) -> bool:
    """True for bottom-of-page notes, not in-body citations."""
    if set(element.layout_labels) & _FOOTNOTE_LAYOUT_LABELS:
        return True
    source = element.md or element.text or ""
    return bool(_FOOTNOTE_START_RE.match(source))


def _is_source_note(text: str) -> bool:
    """True for boxed bibliographic callouts such as 'Source: Coram, Boyd, 45.'"""
    return bool(_SOURCE_NOTE_RE.match(text.strip()))


def _looks_like_visual_credit(text: str) -> bool:
    """Short credit line that LlamaParse emitted as body after a dropped figure."""
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return False
    if len(stripped) > _MAX_VISUAL_CREDIT_LENGTH:
        return False
    if len(stripped.split()) > _MAX_VISUAL_CREDIT_WORDS:
        return False
    if _paragraph_looks_complete(stripped) or stripped[:1].islower():
        return False
    return True


def _is_visual_heading(
    element: Element,
    *,
    fragmented_visual_pages: set[int | None],
) -> bool:
    """Return whether parser provenance contradicts a section heading."""
    if is_standalone_visual_caption(element.text):
        return True

    labels = set(element.layout_labels)
    if not labels or "paragraph_title" in labels:
        return False
    if labels & _NON_SECTION_LAYOUT_LABELS:
        return True
    return labels == {"text"} and element.page in fragmented_visual_pages


def _paragraph_looks_complete(md: str) -> bool:
    """True when md ends a sentence after ignoring trailing markdown emphasis."""
    stripped = _TRAILING_EMPHASIS_RE.sub("", md.strip()).rstrip()
    return bool(_PARAGRAPH_END_RE.search(stripped))


def _is_attribution_line(text: str) -> bool:
    stripped = _LEADING_EMPHASIS_RE.sub("", text.strip()).lstrip()
    return bool(_ATTRIBUTION_LINE_RE.match(stripped))


def _split_epigraph_markdown(md: str) -> list[str]:
    """Split quote + attribution that LlamaParse packed into one text item."""
    parts = [part.strip() for part in _ATTRIBUTION_SPLIT_RE.split(md) if part.strip()]
    return parts if len(parts) > 1 else [md]


def _continues_paragraph(previous: Element, current: Element) -> bool:
    """Detect one paragraph split by a page break and/or omitted visual."""
    if not isinstance(previous.page, int) or not isinstance(current.page, int):
        return False
    if current.page not in (previous.page, previous.page + 1):
        return False
    previous_md = previous.md or previous.text
    current_md = (current.md or current.text).strip()
    # Epigraph attributions are their own paragraphs; never glue them to
    # neighboring quotes or body text.
    if _is_attribution_line(previous_md) or _is_attribution_line(previous.text):
        return False
    if _is_attribution_line(current_md) or _is_attribution_line(current.text):
        return False
    return not _paragraph_looks_complete(previous_md)


def _join_markdown(left: str, right: str) -> str:
    return f"{left.rstrip()} {right.lstrip()}"


def _title_end_has_punct(text: str) -> bool:
    return bool(_TITLE_END_PUNCT_RE.search(text.rstrip()))


def _join_title_parts(parts: list[str], *, chapter_re: str) -> str:
    """Join a chapter/section marker with following title lines.

    Bare doctrine markers keep a space ("Chapter 1 The Nature of War").
    Extra title lines that are not the first after a chapter marker join with
    a colon, matching MCU Press TOC form ("Tending to Produce: John Boyd...").
    """
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return ""
    title = cleaned[0]
    rest = cleaned[1:]
    if not rest:
        return title
    first, *more = rest
    if is_chapter_marker(cleaned[0], chapter_re) or _title_end_has_punct(title):
        title = f"{title} {first}"
    else:
        title = f"{title}: {first}"
    for part in more:
        if _title_end_has_punct(title):
            title = f"{title} {part}"
        else:
            title = f"{title}: {part}"
    return title


def _is_title_continuation_heading(
    element: Element,
    *,
    chapter_re: str,
    fragmented_visual_pages: set[int | None],
) -> bool:
    """True for a title-case heading that belongs to the previous title."""
    if element.type != "heading" or not element.text.strip():
        return False
    if is_chapter_marker(element.text, chapter_re):
        return False
    if _is_visual_heading(element, fragmented_visual_pages=fragmented_visual_pages):
        return False
    return not is_doctrinal_subsection_heading(element.text)


def _looks_like_title_case(text: str) -> bool:
    """True when most significant words are capitalized, as in a chapter subtitle."""
    words = [
        word.strip("\"“”'’")
        for word in re.split(r"\s+", text.replace("—", " "))
        if word.strip("\"“”'’")
    ]
    if len(words) < 2:
        return False
    significant = [word for word in words if word.lower() not in _SMALL_TITLE_WORDS]
    if not significant:
        return False
    capitalized = sum(1 for word in significant if word[:1].isupper())
    return capitalized / len(significant) >= 0.7


def _is_orphan_title_text(element: Element) -> bool:
    """Short title-case prose that LlamaParse emitted as `text`, not a heading."""
    if element.type != "text":
        return False
    text = (element.text or "").strip()
    if not text or "\n" in text or len(text) > _MAX_ORPHAN_TITLE_LENGTH:
        return False
    if len(text.split()) > _MAX_ORPHAN_TITLE_WORDS:
        return False
    if _paragraph_looks_complete(text) or _is_attribution_line(text):
        return False
    if is_standalone_visual_caption(text):
        return False
    if _is_source_note(text) or _is_page_footnote(element):
        return False
    if not _ORPHAN_TITLE_START_RE.match(text):
        return False
    return _looks_like_title_case(text)


def _collect_heading_title(
    elements: list[Element],
    start_index: int,
    *,
    chapter_re: str,
    fragmented_visual_pages: set[int | None],
    absorb_orphan_title_text: bool,
) -> tuple[str, int]:
    """Return (joined title, last consumed index)."""
    parts = [elements[start_index].text]
    index = start_index + 1
    count = len(elements)
    while index < count and _is_title_continuation_heading(
        elements[index],
        chapter_re=chapter_re,
        fragmented_visual_pages=fragmented_visual_pages,
    ):
        parts.append(elements[index].text)
        index += 1
    if absorb_orphan_title_text:
        while index < count and _is_orphan_title_text(elements[index]):
            parts.append(elements[index].text)
            index += 1
    return _join_title_parts(parts, chapter_re=chapter_re), index - 1


def _append_paragraph(
    *,
    chapter: Chapter,
    section: Section | None,
    md: str,
    page: int | None,
) -> Paragraph:
    para = Paragraph(md=md, page=page)
    if section is None:
        chapter.intro.append(para)
    else:
        section.body.append(para)
    return para


def classify(
    elements: list[Element],
    *,
    chapter_re: str = DEFAULT_CHAPTER_RE,
    strip_markers: bool = True,
) -> Book:
    book = Book()
    current_chapter: Chapter | None = None
    current_section: Section | None = None
    consumed_through = -1
    previous_body_element: Element | None = None
    previous_paragraph: Paragraph | None = None
    after_omitted_visual = False
    fragmented_visual_pages = _fragmented_visual_pages(elements)
    explicit_visual_pages = _explicit_visual_pages(elements)

    for idx, el in enumerate(elements):
        if idx <= consumed_through:
            continue
        if el.type == "heading":
            if is_chapter_marker(el.text, chapter_re):
                title, consumed_through = _collect_heading_title(
                    elements,
                    idx,
                    chapter_re=chapter_re,
                    fragmented_visual_pages=fragmented_visual_pages,
                    absorb_orphan_title_text=True,
                )
                previous_body_element = None
                previous_paragraph = None
                after_omitted_visual = False
                current_chapter = Chapter(title=title, page=el.page)
                current_section = None
                book.chapters.append(current_chapter)
            else:
                if _is_visual_heading(
                    el,
                    fragmented_visual_pages=fragmented_visual_pages,
                ):
                    book.dropped_nontext["visual_heading"] = (
                        book.dropped_nontext.get("visual_heading", 0) + 1
                    )
                    # Like an omitted caption, a visual heading does not break
                    # the surrounding authored reading flow.
                    after_omitted_visual = True
                    continue
                title, consumed_through = _collect_heading_title(
                    elements,
                    idx,
                    chapter_re=chapter_re,
                    fragmented_visual_pages=fragmented_visual_pages,
                    absorb_orphan_title_text=False,
                )
                previous_body_element = None
                previous_paragraph = None
                after_omitted_visual = False
                if current_chapter is None:  # safety net (shouldn't happen post-trim)
                    current_chapter = Chapter(title="(untitled)", page=el.page)
                    book.chapters.append(current_chapter)
                current_section = Section(title=title, page=el.page)
                current_chapter.sections.append(current_section)

        elif el.type == "text":
            if _is_page_footnote(el):
                book.dropped_nontext["footnote"] = (
                    book.dropped_nontext.get("footnote", 0) + 1
                )
                # Page notes sit between halves of a sentence; keep continuity.
                continue
            md = el.md or el.text
            if strip_markers:
                md = strip_footnote_markers(md)
            if not md.strip() or current_chapter is None:
                previous_body_element = None
                previous_paragraph = None
                after_omitted_visual = False
                continue
            if _is_visual_description(
                el,
                fragmented_visual_pages=fragmented_visual_pages,
                explicit_visual_pages=explicit_visual_pages,
            ):
                book.dropped_nontext["visual_description"] = (
                    book.dropped_nontext.get("visual_description", 0) + 1
                )
                # Generated descriptions of omitted visuals are not source
                # prose and remain transparent to reading order.
                after_omitted_visual = True
                continue
            if is_standalone_visual_caption(el.text or md):
                book.dropped_nontext["caption"] = book.dropped_nontext.get("caption", 0) + 1
                # Captions for omitted visuals are transparent to continuity.
                after_omitted_visual = True
                continue
            if _is_source_note(md):
                book.dropped_nontext["reference"] = (
                    book.dropped_nontext.get("reference", 0) + 1
                )
                continue
            if after_omitted_visual and _looks_like_visual_credit(el.text or md):
                book.dropped_nontext["caption"] = (
                    book.dropped_nontext.get("caption", 0) + 1
                )
                continue
            if (
                previous_body_element is not None
                and previous_paragraph is not None
                and _continues_paragraph(previous_body_element, el)
            ):
                previous_paragraph.md = _join_markdown(previous_paragraph.md, md)
                previous_body_element = el
                continue

            parts = _split_epigraph_markdown(md)
            last_para: Paragraph | None = None
            for part in parts:
                last_para = _append_paragraph(
                    chapter=current_chapter,
                    section=current_section,
                    md=part,
                    page=el.page,
                )
            previous_body_element = el
            previous_paragraph = last_para
            after_omitted_visual = False

        else:  # list / code / image / etc -- not a KEEP type
            book.dropped_nontext[el.type] = book.dropped_nontext.get(el.type, 0) + 1
            if el.type in _OMITTED_VISUAL_TYPES:
                after_omitted_visual = True
            else:
                previous_body_element = None
                previous_paragraph = None
                after_omitted_visual = False

    return book
