"""Stage: TRIM (document-body-boundaries).

Trim everything before the first real chapter (title page, foreword, preface,
table of contents) and everything from the start of back matter (notes,
glossary, bibliography, index, epilogue) onward. Replaces the front/back-matter
removal half of the old prepare-document step.

A division is a chapter or part label: bare ("Chapter 1", "CHAPTER ONE",
"Part II") or with a title on the same line ("Chapter 1: The Nature of War").
When a label repeats, the earlier cluster is the table of contents and the
body starts at the copy that is followed by prose. Documents with no division
labels still trim known front and back matter instead of failing the stage.

Boundary detection is heuristic; the slicing is deterministic. `auto_boundaries`
proposes [start, end); the executor records the proposal and the trim so a human
can audit it, and `trim` can also be driven with explicit indices when a
document needs an override.
"""
from __future__ import annotations

import re

from app.intellex.structuring.models import Element

# Arabic digits, English words through twenty-nine, or roman numerals through
# xxix. MCU Press / academic books often use "CHAPTER ONE" instead of "Chapter 1".
# Longer word forms come first so "two" does not steal the prefix of "twenty".
CHAPTER_NUMBER = (
    r"(?:[0-9]+|"
    r"twenty[- ](?:one|two|three|four|five|six|seven|eight|nine)|"
    r"twenty|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"eleven|twelve|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"xxix|xxviii|xxvii|xxvi|xxv|xxiv|xxiii|xxii|xxi|xx|"
    r"xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|"
    r"ix|viii|vii|vi|v|iv|iii|ii|i)"
)
# A same-line title is punctuated ("Chapter 1: The Nature of War") or capitalized
# ("CHAPTER ONE The Commission"). A lowercase continuation such as
# "Chapter 2 described..." is a sentence, not a title.
_SAME_LINE_TITLE = r"(?:\s*[:.\u2013\u2014-]\s+\S[^\n]*|\s+[A-Z][^\n]*)?"
DEFAULT_CHAPTER_RE = rf"^\s*(?:chapter|part)\s+{CHAPTER_NUMBER}{_SAME_LINE_TITLE}\s*$"

_DIVISION_RE = re.compile(DEFAULT_CHAPTER_RE, re.IGNORECASE)
_DIVISION_KEY_RE = re.compile(
    rf"^\s*(chapter|part)\s+({CHAPTER_NUMBER})\b",
    re.IGNORECASE,
)
_BACK_MATTER_LABELS = re.compile(
    r"^\s*(notes?|endnotes?|glossary|bibliography|references?|index|"
    r"appendix(?:\s+[a-z0-9]+)?|epilogue|afterword|about\s+the\s+author)"
    r"(?:\s*[:.\u2013\u2014-]\s+\S.*)?\s*$",
    re.IGNORECASE,
)
# LlamaParse often names the ornament instead of emitting a bare "CHAPTER ONE":
# "logo: CHAPTER ONE with decorative flourish" or "CHAPTER FOUR\nlogo: decorative flourish".
_PREFIXED_KICKER_RE = re.compile(
    rf"^(?:logo|icon|image|seal|emblem|ornament|banner|photo)\s*:\s*"
    rf"(chapter|part)\s+({CHAPTER_NUMBER})\b"
    rf"(?:\s+(?:with\s+)?(?:[a-z][\w'-]*\s*){{0,6}})?\s*$",
    re.IGNORECASE,
)
_FRONT_MATTER_LABELS = re.compile(
    r"^\s*(?:table\s+of\s+contents|contents|foreword|preface|dedication|"
    r"acknowledge?ments?)\s*$",
    re.IGNORECASE,
)
_EMBEDDED_TITLE_RE = re.compile(
    rf"^\s*(?:chapter|part)\s+{CHAPTER_NUMBER}\s*[.:\u2013\u2014-]?\s+(.+)$",
    re.IGNORECASE,
)


def _headings(elements: list[Element]) -> list[Element]:
    return [e for e in elements if e.type == "heading"]


def _first_nonempty_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _prefixed_kicker(text: str) -> re.Match[str] | None:
    for line in (text or "").splitlines():
        match = _PREFIXED_KICKER_RE.match(line.strip())
        if match:
            return match
    return None


def is_division_label(text: str) -> bool:
    """True when text is a chapter or part kicker.

    The first line may be the label ("CHAPTER TWO", "Chapter 1: Title").
    A parser ornament line also counts: "logo: CHAPTER ONE with decorative flourish".
    A sentence that merely begins with "Chapter 2 described..." does not.
    """
    if _prefixed_kicker(text) is not None:
        return True
    first = _first_nonempty_line(text)
    match = _DIVISION_KEY_RE.match(first)
    if not match:
        return False
    rest = first[match.end():]
    if not rest.strip():
        return True
    if re.match(r"\s*[:.\u2013\u2014-]\s+\S", rest):
        return True
    # Case-sensitive: the title's first word is capitalized. IGNORECASE would
    # also accept "Chapter 2 described...".
    return re.match(r"\s+[A-Z]", rest) is not None


def chapter_heading_label(text: str) -> str | None:
    """Return the chapter or part label to show, without the ornament description."""
    if not is_division_label(text):
        return None
    first = _first_nonempty_line(text)
    if _DIVISION_RE.match(first):
        return first
    prefixed = _prefixed_kicker(text)
    if prefixed:
        return f"{prefixed.group(1)} {prefixed.group(2)}"
    return None


def is_back_matter_heading(text: str) -> bool:
    """True for an exact back-matter label such as Notes, Appendix A, or Index."""
    return bool(_BACK_MATTER_LABELS.match(_first_nonempty_line(text)))


def is_chapter_marker(text: str, chapter_re: str = DEFAULT_CHAPTER_RE) -> bool:
    if chapter_re == DEFAULT_CHAPTER_RE:
        return is_division_label(text)
    return bool(re.match(chapter_re, _first_nonempty_line(text), re.IGNORECASE))


def _division_key(text: str) -> str:
    match = _DIVISION_KEY_RE.match(_first_nonempty_line(text))
    if match:
        return f"{match.group(1).lower()} {match.group(2).lower()}"
    prefixed = _prefixed_kicker(text)
    if prefixed:
        return f"{prefixed.group(1).lower()} {prefixed.group(2).lower()}"
    return _first_nonempty_line(text).lower()


def _chapter_titles(
    elements: list[Element],
    markers: list[Element],
    chapter_re: str,
) -> set[str]:
    """Lowercased chapter title strings, used to recognize the endnotes-by-chapter
    pattern where chapter titles reappear as note dividers in the back matter."""
    headings = _headings(elements)
    heading_position = {id(heading): index for index, heading in enumerate(headings)}
    titles: set[str] = set()
    for marker in markers:
        embedded = _EMBEDDED_TITLE_RE.match(_first_nonempty_line(marker.text or ""))
        if embedded and embedded.group(1).strip():
            titles.add(embedded.group(1).strip().lower())
            continue
        position = heading_position.get(id(marker))
        if position is None or position + 1 >= len(headings):
            continue
        following = headings[position + 1]
        if is_chapter_marker(following.text, chapter_re):
            continue
        titles.add(following.text.strip().lower())
    return titles


def _has_body_text(
    elements: list[Element],
    marker: Element,
    following_marker: Element | None,
) -> bool:
    """True when prose sits between this division and the next one."""
    end_index = following_marker.index if following_marker is not None else None
    for element in elements:
        if element.index <= marker.index:
            continue
        if end_index is not None and element.index >= end_index:
            break
        if element.type == "text" and (element.text or "").strip():
            return True
    return False


def _first_with_body(elements: list[Element], markers: list[Element]) -> Element | None:
    for index, marker in enumerate(markers):
        following = markers[index + 1] if index + 1 < len(markers) else None
        if _has_body_text(elements, marker, following):
            return marker
    return None


def _first_repeat_index(markers: list[Element]) -> int | None:
    seen: set[str] = set()
    for index, marker in enumerate(markers):
        key = _division_key(marker.text)
        if key in seen:
            return index
        seen.add(key)
    return None


def _body_division(elements: list[Element], markers: list[Element]) -> Element | None:
    """Pick the division that opens the body, skipping a contents cluster.

    A repeated label means the first cluster is the table of contents. Prefer
    the later copy when it is followed by prose. Otherwise take the first
    division that has prose before the next division.
    """
    if not markers:
        return None
    repeat_at = _first_repeat_index(markers)
    if repeat_at is not None:
        repeated = _first_with_body(elements, markers[repeat_at:])
        if repeated is not None:
            return repeated
    return _first_with_body(elements, markers)


def _scan_headings_after(elements: list[Element], last_marker: Element, chapter_re: str) -> list[Element]:
    """Headings after the last chapter, skipping that chapter's own title line."""
    following = [heading for heading in _headings(elements) if heading.index > last_marker.index]
    embedded = _EMBEDDED_TITLE_RE.match(last_marker.text or "")
    if embedded and embedded.group(1).strip():
        return following
    if not following or is_chapter_marker(following[0].text, chapter_re):
        return following
    if _BACK_MATTER_LABELS.match(following[0].text or ""):
        return following
    return following[1:]


def _bounds_without_divisions(
    elements: list[Element],
) -> tuple[int, int | None, dict[str, str]]:
    """Keep the middle when the document has no chapter or part labels."""
    start_i = elements[0].index
    headings = _headings(elements)
    for position, heading in enumerate(headings):
        if not _FRONT_MATTER_LABELS.match(heading.text or ""):
            break
        if position + 1 < len(headings):
            start_i = headings[position + 1].index
        else:
            start_i = elements[-1].index + 1
    if start_i > elements[-1].index:
        start_i = elements[0].index
        start_reason = "no division markers; front matter filled the document; kept everything"
    else:
        start_reason = f"no division markers; kept from element {start_i} after front matter"

    end_i: int | None = None
    end_reason = "no back matter detected; kept to end of document"
    for heading in headings:
        if heading.index < start_i:
            continue
        if _BACK_MATTER_LABELS.match(heading.text or ""):
            end_i = heading.index
            end_reason = f"back-matter label {heading.text!r} at element {heading.index} (p{heading.page})"
            break
    return start_i, end_i, {"start": start_reason, "end": end_reason}


def auto_boundaries(
    elements: list[Element],
    *,
    chapter_re: str = DEFAULT_CHAPTER_RE,
) -> tuple[int | None, int | None, dict[str, str]]:
    """Propose (start_index inclusive, end_index exclusive, reasons)."""
    if not elements:
        return 0, 0, {"start": "empty document", "end": "empty document"}

    markers = [element for element in elements if is_chapter_marker(element.text, chapter_re)]
    body_marker = _body_division(elements, markers)
    if body_marker is None:
        return _bounds_without_divisions(elements)

    start_i = body_marker.index
    body_markers = [marker for marker in markers if marker.index >= start_i]
    last_marker = body_markers[-1]
    titles = _chapter_titles(elements, body_markers, chapter_re)

    end_i: int | None = None
    reason_end = "no back matter detected; kept to end of document"
    for heading in _scan_headings_after(elements, last_marker, chapter_re):
        if _BACK_MATTER_LABELS.match(heading.text or ""):
            end_i = heading.index
            reason_end = f"back-matter label {heading.text!r} at element {heading.index} (p{heading.page})"
            break
        if (heading.text or "").strip().lower() in titles:
            end_i = heading.index
            reason_end = (
                f"repeated chapter title {heading.text!r} at element {heading.index} "
                f"(p{heading.page}); start of endnotes-by-chapter"
            )
            break

    start_reason = (
        f"first bare chapter marker {body_marker.text!r} at element {start_i} "
        f"(p{body_marker.page})"
    )
    if body_marker is not markers[0]:
        start_reason += "; skipped earlier contents cluster"
    return start_i, end_i, {"start": start_reason, "end": reason_end}


def trim(
    elements: list[Element],
    *,
    start_index: int,
    end_index: int,
) -> list[Element]:
    """Keep elements whose index is in [start_index, end_index)."""
    return [e for e in elements if start_index <= e.index < end_index]
