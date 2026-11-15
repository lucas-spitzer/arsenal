from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.models.reader_define import ReaderDefineRequest
from app.services.llm.base import LLMCompletionResult
from app.services.reader_define import ReaderDefineError, ReaderDefineService


class FakeLLM:
    provider = "openai"
    model = "gpt-test"

    def __init__(self, definition: str | list[str] = "A short definition.") -> None:
        self.definitions = [definition] if isinstance(definition, str) else definition
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str, model: str | None = None):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "model": model,
            },
        )
        index = min(len(self.calls) - 1, len(self.definitions) - 1)
        return LLMCompletionResult(
            content={"definition": self.definitions[index]},
            model=self.model,
            provider=self.provider,
            token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


def test_contextual_define_requires_current_paragraph() -> None:
    service = ReaderDefineService(llm_client=FakeLLM())  # type: ignore[arg-type]
    request = ReaderDefineRequest(term="tempo", mode="contextual", current_paragraph="  ")

    with pytest.raises(ReaderDefineError, match="current paragraph"):
        asyncio.run(service.define(request))


def test_contextual_define_includes_neighbors_in_prompt() -> None:
    llm = FakeLLM("They increased tempo in the fight.")
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="contextual",
        prev_paragraph="Earlier context.",
        current_paragraph="They increased tempo in the fight.",
        next_paragraph="Later result.",
    )

    result = asyncio.run(service.define(request))

    assert result.definition == "They increased tempo in the fight."
    assert result.mode == "contextual"
    assert result.provenance == "contextual"
    assert "PREVIOUS PARAGRAPH:\nEarlier context." in llm.calls[0]["user_prompt"]
    assert "CURRENT PARAGRAPH:\nThey increased tempo in the fight." in llm.calls[0]["user_prompt"]
    assert "NEXT PARAGRAPH:\nLater result." in llm.calls[0]["user_prompt"]
    assert "passage" in llm.calls[0]["system_prompt"]


def test_contextual_define_returns_a_passage_span() -> None:
    span = "the speed of decision cycles relative to the enemy"
    llm = FakeLLM(f"  {span}  ")
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="contextual",
        current_paragraph=(
            "Tempo is the speed of decision cycles relative to the enemy. "
            "They increased tempo in the fight."
        ),
    )

    result = asyncio.run(service.define(request))

    assert result.definition == "The speed of decision cycles relative to the enemy."
    assert len(llm.calls) == 1


def test_contextual_define_formats_a_fragment_as_a_sentence() -> None:
    fragment = "the force that resists all action and saps energy"
    llm = FakeLLM(fragment)
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="friction",
        mode="contextual",
        current_paragraph=f"Friction is {fragment} in war.",
    )

    result = asyncio.run(service.define(request))

    assert result.definition == "The force that resists all action and saps energy."


def test_contextual_define_accepts_a_quote_that_already_has_a_period() -> None:
    fragment = "the force that resists all action and saps energy"
    llm = FakeLLM(f"{fragment}.")
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="friction",
        mode="contextual",
        current_paragraph=f"Friction is {fragment} in war.",
    )

    result = asyncio.run(service.define(request))

    assert result.definition == "The force that resists all action and saps energy."
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("essence of war", "Essence of War"),
        ("the fog of war", "The Fog of War"),
        ("MAGTF", "MAGTF"),
    ],
)
def test_define_title_cases_the_term(raw: str, expected: str) -> None:
    llm = FakeLLM("A general pace or rate.")
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(term=raw, mode="general", sentence="The term appears here.")

    result = asyncio.run(service.define(request))

    assert result.term == expected


def test_contextual_define_retries_then_rejects_a_paraphrase() -> None:
    llm = FakeLLM(["Speed of decision cycles.", "How fast one decides."])
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="contextual",
        sentence="They increased tempo in the fight.",
        current_paragraph="They increased tempo in the fight.",
    )

    with pytest.raises(ReaderDefineError, match="copied from the passage"):
        asyncio.run(service.define(request))

    assert len(llm.calls) == 2
    assert "Speed of decision cycles." in llm.calls[1]["user_prompt"]
    assert "Do not paraphrase." in llm.calls[1]["user_prompt"]


def test_contextual_define_accepts_a_quote_after_one_retry() -> None:
    quote = "They increased tempo in the fight."
    llm = FakeLLM(["Speed of decision cycles.", quote])
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="contextual",
        current_paragraph=quote,
    )

    result = asyncio.run(service.define(request))

    assert result.definition == quote
    assert len(llm.calls) == 2


def test_contextual_define_prompt_requires_a_quote_and_includes_the_sentence() -> None:
    sentence = "They increased tempo in the fight."
    llm = FakeLLM(sentence)
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="contextual",
        sentence=sentence,
        prev_paragraph="Earlier context.",
        current_paragraph=sentence,
        next_paragraph="Later result.",
    )

    asyncio.run(service.define(request))

    system_prompt = llm.calls[0]["system_prompt"]
    assert "contiguous quote" in system_prompt
    assert "Do not paraphrase" in system_prompt
    assert f"SENTENCE:\n{sentence}" in llm.calls[0]["user_prompt"]


def test_general_define_uses_sentence_and_general_prompt() -> None:
    llm = FakeLLM("A general pace or rate.")
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="general",
        sentence="The orchestra kept a steady tempo.",
        current_paragraph="Optional paragraph.",
    )

    result = asyncio.run(service.define(request))

    assert result.provenance == "general"
    assert "SENTENCE:\nThe orchestra kept a steady tempo." in llm.calls[0]["user_prompt"]
    assert "dictionary-style" in llm.calls[0]["system_prompt"]


def test_define_rejects_empty_model_definition() -> None:
    llm = FakeLLM("   ")
    service = ReaderDefineService(llm_client=llm)  # type: ignore[arg-type]
    request = ReaderDefineRequest(
        term="tempo",
        mode="general",
        sentence="x",
    )

    with pytest.raises(ReaderDefineError, match="no definition"):
        asyncio.run(service.define(request))
