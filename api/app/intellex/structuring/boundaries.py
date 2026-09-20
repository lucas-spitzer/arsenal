"""Stage: TRIM (document-body-boundaries).

Trim everything before the first real chapter (title page, foreword, preface,
table of contents) and everything from the start of back matter (notes,
glossary, bibliography, index, epilogue) onward. Replaces the front/back-matter
removal half of the old prepare-document step.

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
DEFAULT_CHAPTER_RE = rf"^\s*chapter\s+{CHAPTER_NUMBER}\s*$"

_BACK_MATTER_LABELS = re.compile(
    r"^\s*(notes?|endnotes?|glossary|bibliography|references?|index|"
    r"appendix(?:\s+[a-z0-9]+)?|epilogue|afterword|about\s+the\s+author)\s*$",
    re.IGNORECASE,
)
_EMBEDDED_TITLE_RE = re.compile(
    rf"^\s*chapter\s+{CHAPTER_NUMBER}\s*[.:\-]?\s+(.+)$",
    re.IGNORECASE,
)


def _headings(elements: list[Element]) -> list[Element]:
    return [e for e in elements if e.type == "heading"]


def is_chapter_marker(text: str, chapter_re: str) -> bool:
    return bool(re.match(chapter_re, text or "", re.IGNORECASE))


def _chapter_titles(elements: list[Element], chapter_re: str) -> set[str]:
    """Lowercased chapter title strings, used to recognize the endnotes-by-chapter
    pattern where chapter titles reappear as note dividers in the back matter."""
    titles: set[str] = set()
    hs = _headings(elements)
    for i, h in enumerate(hs):
        if not is_chapter_marker(h.text, chapter_re):
            continue
        m = _EMBEDDED_TITLE_RE.match(h.text)
        if m and m.group(1).strip():
            titles.add(m.group(1).strip().lower())
        elif i + 1 < len(hs):
            titles.add(hs[i + 1].text.strip().lower())
    return titles


def auto_boundaries(
    elements: list[Element],
    *,
    chapter_re: str = DEFAULT_CHAPTER_RE,
) -> tuple[int | None, int | None, dict[str, str]]:
    """Propose (start_index inclusive, end_index exclusive, reasons)."""
    hs = _headings(elements)
    markers = [h for h in hs if is_chapter_marker(h.text, chapter_re)]
    if not markers:
        return None, None, {"error": "no chapter markers found; pass explicit indices"}

    start_i = markers[0].index
    last_marker = markers[-1]
    titles = _chapter_titles(elements, chapter_re)

    # The last chapter's own title sits right after its marker; scan past it so it
    # isn't mistaken for back matter.
    scan_from = hs.index(last_marker) + 2

    end_i: int | None = None
    reason_end = "no back matter detected; kept to end of document"
    for h in hs[scan_from:]:
        if _BACK_MATTER_LABELS.match(h.text or ""):
            end_i = h.index
            reason_end = f"back-matter label {h.text!r} at element {h.index} (p{h.page})"
            break
        if (h.text or "").strip().lower() in titles:
            end_i = h.index
            reason_end = (f"repeated chapter title {h.text!r} at element {h.index} "
                          f"(p{h.page}); start of endnotes-by-chapter")
            break

    reasons = {
        "start": f"first bare chapter marker {markers[0].text!r} at element {start_i} "
                 f"(p{markers[0].page})",
        "end": reason_end,
    }
    return start_i, end_i, reasons


def trim(
    elements: list[Element],
    *,
    start_index: int,
    end_index: int,
) -> list[Element]:
    """Keep elements whose index is in [start_index, end_index)."""
    return [e for e in elements if start_index <= e.index < end_index]
