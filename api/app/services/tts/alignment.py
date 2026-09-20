from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.services.tts.types import WordTiming

_TOKEN_RE = re.compile(r"\S+")
_CONTENT_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class TextToken:
    index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class RawTiming:
    value: str
    start: float
    end: float
    start_char: int | None = None
    end_char: int | None = None


def tokenize_with_spans(text: str) -> list[TextToken]:
    return [
        TextToken(index, match.group(), match.start(), match.end())
        for index, match in enumerate(_TOKEN_RE.finditer(text))
    ]


def normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def _interpolate_unmapped(
    tokens: list[TextToken],
    mapped: list[WordTiming | None],
    duration_seconds: float,
) -> list[WordTiming]:
    result: list[WordTiming] = []
    for index, token in enumerate(tokens):
        timing = mapped[index]
        if timing is not None:
            result.append(timing)
            continue

        previous_end = result[-1].end if result else 0.0
        next_start = duration_seconds
        next_index = index + 1
        while next_index < len(mapped):
            if mapped[next_index] is not None:
                next_start = mapped[next_index].start
                break
            next_index += 1
        missing_count = max(1, next_index - index)
        slot = max(0.0, next_start - previous_end) / missing_count
        start = previous_end
        end = start + slot
        result.append(
            WordTiming(
                index=index,
                word=token.text,
                start=start,
                end=end,
                start_char=token.start_char,
                end_char=token.end_char,
            )
        )
    return result


def align_offset_timings(
    text: str,
    raw_timings: list[RawTiming],
    duration_seconds: float,
) -> list[WordTiming]:
    """Map provider marks to source tokens using source character overlap."""
    tokens = tokenize_with_spans(text)
    mapped: list[WordTiming | None] = [None] * len(tokens)

    for token in tokens:
        starts: list[float] = []
        ends: list[float] = []
        for mark in raw_timings:
            if mark.start_char is None or mark.end_char is None:
                continue
            overlap_start = max(token.start_char, mark.start_char)
            overlap_end = min(token.end_char, mark.end_char)
            if overlap_end <= overlap_start:
                continue

            char_length = max(1, mark.end_char - mark.start_char)
            time_length = max(0.0, mark.end - mark.start)
            starts.append(
                mark.start
                + time_length * ((overlap_start - mark.start_char) / char_length)
            )
            ends.append(
                mark.start
                + time_length * ((overlap_end - mark.start_char) / char_length)
            )

        if starts and ends:
            mapped[token.index] = WordTiming(
                index=token.index,
                word=token.text,
                start=min(starts),
                end=max(ends),
                start_char=token.start_char,
                end_char=token.end_char,
            )

    return _interpolate_unmapped(tokens, mapped, duration_seconds)


def _expand_mark_words(raw_timings: list[RawTiming]) -> list[RawTiming]:
    expanded: list[RawTiming] = []
    for mark in raw_timings:
        pieces = list(_CONTENT_RE.finditer(mark.value))
        if not pieces:
            continue
        value_length = max(1, len(mark.value))
        time_length = max(0.0, mark.end - mark.start)
        for piece in pieces:
            expanded.append(
                RawTiming(
                    value=piece.group(),
                    start=mark.start + time_length * (piece.start() / value_length),
                    end=mark.start + time_length * (piece.end() / value_length),
                )
            )
    return expanded


def align_ordered_timings(
    text: str,
    raw_timings: list[RawTiming],
    duration_seconds: float,
) -> list[WordTiming]:
    """Map ordered provider words to source tokens without blind positional zip."""
    tokens = tokenize_with_spans(text)
    expanded = _expand_mark_words(raw_timings)
    source_values = [normalize_token(token.text) for token in tokens]
    mark_values = [normalize_token(mark.value) for mark in expanded]
    matcher = SequenceMatcher(a=source_values, b=mark_values, autojunk=False)
    mapped: list[WordTiming | None] = [None] * len(tokens)

    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            token = tokens[block.a + offset]
            mark = expanded[block.b + offset]
            mapped[token.index] = WordTiming(
                index=token.index,
                word=token.text,
                start=mark.start,
                end=mark.end,
                start_char=token.start_char,
                end_char=token.end_char,
            )

    return _interpolate_unmapped(tokens, mapped, duration_seconds)


def timing_quality(
    text: str,
    words: list[WordTiming],
    duration_seconds: float,
) -> dict[str, Any]:
    tokens = tokenize_with_spans(text)
    identity_matches = sum(
        normalize_token(token.text) == normalize_token(word.word)
        for token, word in zip(tokens, words, strict=False)
    )
    count = len(tokens)
    finite = all(
        math.isfinite(word.start)
        and math.isfinite(word.end)
        and word.start >= 0
        and word.end >= word.start
        for word in words
    )
    monotonic = all(
        current.start >= previous.start
        for previous, current in zip(words, words[1:], strict=False)
    )
    positive_intervals = all(word.end > word.start for word in words)
    in_bounds = all(
        word.end <= duration_seconds + 0.25 for word in words
    ) if duration_seconds > 0 else not words
    identity_ratio = identity_matches / count if count else 1.0
    last_word_end = words[-1].end if words else 0.0
    media_end_difference = duration_seconds - last_word_end
    short_word_fraction = (
        sum(word.end - word.start < 0.25 for word in words) / len(words)
        if words
        else 0.0
    )
    valid = (
        len(words) == count
        and finite
        and monotonic
        and positive_intervals
        and in_bounds
        and identity_ratio >= 0.98
    )
    return {
        "valid": valid,
        "expected_words": count,
        "timing_words": len(words),
        "identity_ratio": round(identity_ratio, 4),
        "finite": finite,
        "monotonic": monotonic,
        "positive_intervals": positive_intervals,
        "in_bounds": in_bounds,
        "media_end_difference": round(media_end_difference, 4),
        "short_word_fraction": round(short_word_fraction, 4),
    }
