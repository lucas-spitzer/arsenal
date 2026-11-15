"""One-shot reader term definitions (contextual passage quote or general sense)."""

from __future__ import annotations

import asyncio
import re

from app.models.reader_define import ReaderDefineRequest, ReaderDefineResponse
from app.services.api_pricing import cost_llm_usage
from app.services.llm import get_llm_client
from app.services.llm.base import LLMClient, LLMCompletionResult


class ReaderDefineError(ValueError):
    """Raised when a define request is invalid or the model returns unusable output."""


CONTEXTUAL_SYSTEM_PROMPT = """\
You copy a short definition for a term from the passage. The definition must be a contiguous quote of words already written in the supplied paragraphs or sentence.

Rules:
- Copy the author's words exactly. Do not paraphrase, swap synonyms, or add knowledge from outside the passage.
- Prefer the shortest clause in the current paragraph that says what the term means.
- If the passage uses the term without defining it, quote the sentence that contains the term.
- Return JSON only: {"definition": string}
"""

GENERAL_SYSTEM_PROMPT = """\
You write short general (dictionary-style) definitions for a term, guided by its sentence.

Rules:
- Give the common meaning that fits the sentence, not a passage-specific gloss.
- Keep the definition to a single concise sentence whenever possible.
- Do not claim the definition is grounded in a specific source passage.
- Return JSON only: {"definition": string}
"""


_SMALL_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "nor",
        "for",
        "of",
        "on",
        "in",
        "to",
        "as",
        "at",
        "by",
    },
)


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _quote_body(definition: str) -> str:
    """Drop one trailing sentence mark so a punctuated quote still matches the passage."""
    text = definition.strip()
    if text.endswith((".", "!", "?")):
        text = text[:-1].rstrip()
    return text


def _quote_sources(request: ReaderDefineRequest) -> list[str]:
    candidates = (
        request.prev_paragraph,
        request.current_paragraph,
        request.next_paragraph,
        request.sentence,
    )
    return [text.strip() for text in candidates if text and text.strip()]


def _is_contiguous_quote(definition: str, sources: list[str]) -> bool:
    normalized = _normalized_text(_quote_body(definition))
    if not normalized:
        return False
    return any(normalized in _normalized_text(source) for source in sources)


def _as_sentence(text: str) -> str:
    sentence = text.strip()
    if not sentence:
        return sentence
    sentence = sentence[0].upper() + sentence[1:]
    if sentence[-1] in ",;:":
        sentence = sentence[:-1].rstrip()
    if sentence and sentence[-1] not in ".!?":
        sentence += "."
    return sentence


def _title_case_word(word: str, *, is_edge: bool) -> str:
    letters = "".join(char for char in word if char.isalpha())
    if len(letters) >= 2 and letters.isupper():
        return word
    lower = word.lower()
    if not is_edge and lower in _SMALL_WORDS:
        return lower
    if not word:
        return word
    return word[0].upper() + word[1:].lower()


def _title_case_term(term: str) -> str:
    words = term.split()
    if not words:
        return term
    last = len(words) - 1
    return " ".join(
        _title_case_word(word, is_edge=index in {0, last})
        for index, word in enumerate(words)
    )


def _contextual_user_prompt(
    request: ReaderDefineRequest,
    term: str,
    current: str,
    *,
    rejected: str | None,
) -> str:
    sentence = (request.sentence or "").strip()
    prompt = (
        f"TERM: {term}\n\n"
        f"SENTENCE:\n{sentence or '(not provided)'}\n\n"
        f"PREVIOUS PARAGRAPH:\n{(request.prev_paragraph or '').strip() or '(none)'}\n\n"
        f"CURRENT PARAGRAPH:\n{current}\n\n"
        f"NEXT PARAGRAPH:\n{(request.next_paragraph or '').strip() or '(none)'}"
    )
    if rejected is None:
        return prompt
    return (
        f"{prompt}\n\n"
        "The previous definition was not a contiguous quote from the passage:\n"
        f"{rejected}\n\n"
        "Copy a contiguous span from the paragraphs or sentence. Do not paraphrase."
    )


def _record_usage(result: LLMCompletionResult) -> None:
    usage = result.token_usage or {}
    cost_llm_usage(
        provider=getattr(result, "provider", "openai") or "openai",
        model=result.model,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
    )


class ReaderDefineService:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client("reader_define")
        return self._llm_client

    async def define(self, request: ReaderDefineRequest) -> ReaderDefineResponse:
        term = _title_case_term(request.term.strip())
        if not term:
            raise ReaderDefineError("Term is required.")

        quote_sources: list[str] = []
        user_prompt = ""
        max_attempts = 1
        if request.mode == "contextual":
            current = (request.current_paragraph or "").strip()
            if not current:
                raise ReaderDefineError(
                    "Contextual definitions require the current paragraph.",
                )
            system_prompt = CONTEXTUAL_SYSTEM_PROMPT
            quote_sources = _quote_sources(request)
            max_attempts = 2
        else:
            current = ""
            system_prompt = GENERAL_SYSTEM_PROMPT
            sentence = (request.sentence or "").strip()
            user_prompt = (
                f"TERM: {term}\n\n"
                f"SENTENCE:\n{sentence or '(not provided)'}\n\n"
                f"CURRENT PARAGRAPH:\n{(request.current_paragraph or '').strip() or '(none)'}"
            )

        rejected: str | None = None
        for _attempt in range(max_attempts):
            prompt = (
                _contextual_user_prompt(request, term, current, rejected=rejected)
                if request.mode == "contextual"
                else user_prompt
            )
            result = await asyncio.to_thread(
                self.llm_client.complete_json,
                system_prompt=system_prompt,
                user_prompt=prompt,
            )
            raw_definition = result.content.get("definition")
            if not isinstance(raw_definition, str) or not raw_definition.strip():
                raise ReaderDefineError("The model returned no definition.")

            definition = raw_definition.strip()
            _record_usage(result)
            if request.mode != "contextual" or _is_contiguous_quote(definition, quote_sources):
                return ReaderDefineResponse(
                    term=term,
                    definition=_as_sentence(definition),
                    mode=request.mode,
                    provenance=request.mode,
                )
            rejected = definition

        raise ReaderDefineError(
            "The model did not return a definition copied from the passage.",
        )


def get_reader_define_service() -> ReaderDefineService:
    return ReaderDefineService()
