"""Display form for a chapter title the structure stage assembled.

The source keeps "CHAPTER ONE" plus the following title line. The book shows
that as "Chapter 1: The Commission and the Oath". PDF validation still uses
the source spelling.
"""

from __future__ import annotations

import re

from app.intellex.structuring.boundaries import CHAPTER_NUMBER

_CHAPTER_DISPLAY_RE = re.compile(
    rf"^(chapter)\s+({CHAPTER_NUMBER})(?:\s*[:.\u2013\u2014-]\s+|\s+)?(.*)$",
    re.IGNORECASE,
)

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}

_ROMAN_NUMERALS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
    "xi": 11,
    "xii": 12,
    "xiii": 13,
    "xiv": 14,
    "xv": 15,
    "xvi": 16,
    "xvii": 17,
    "xviii": 18,
    "xix": 19,
    "xx": 20,
    "xxi": 21,
    "xxii": 22,
    "xxiii": 23,
    "xxiv": 24,
    "xxv": 25,
    "xxvi": 26,
    "xxvii": 27,
    "xxviii": 28,
    "xxix": 29,
}


def _arabic(token: str) -> int | None:
    normalized = token.lower().replace(" ", "-")
    if normalized.isdigit():
        return int(normalized)
    if normalized in _WORD_NUMBERS:
        return _WORD_NUMBERS[normalized]
    if normalized.startswith("twenty-"):
        rest = _WORD_NUMBERS.get(normalized.split("-", 1)[1])
        if rest is not None and rest < 10:
            return 20 + rest
    return _ROMAN_NUMERALS.get(normalized)


def display_chapter_title(title: str) -> str:
    """Turn an assembled chapter heading into "Chapter N: Title"."""
    match = _CHAPTER_DISPLAY_RE.match(title.strip())
    if match is None:
        return title
    number = _arabic(match.group(2))
    if number is None:
        return title
    rest = match.group(3).strip()
    if rest and not rest[:1].isupper():
        return title
    if not rest:
        return f"Chapter {number}"
    return f"Chapter {number}: {rest}"
