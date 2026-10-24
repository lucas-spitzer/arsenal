from app.models.assistant import AssistantChatRequest, CreateDiscussionThreadRequest
from app.services.assistant import SYSTEM_PROMPTS, AssistantService


class _Unused:
    pass


def test_tbs_prompt_teaches_from_the_source() -> None:
    prompt = SYSTEM_PROMPTS["discussion:tbs"]

    assert "second lieutenant at The Basic School" in prompt
    assert "Answer ONLY from the SOURCE MATERIAL" in prompt
    assert "Do not invent facts, examples, or doctrine" in prompt
    assert "Ask one question" in prompt
    assert "Do not withhold the answer" in prompt


def test_discussion_defaults_to_the_tbs_instruction() -> None:
    assert CreateDiscussionThreadRequest(title="Patrol base").submode == "tbs"

    service = AssistantService(retrieval=_Unused(), assessments=_Unused())
    prompt = service._system_prompt(AssistantChatRequest(mode="discussion", messages=[]))

    assert prompt == SYSTEM_PROMPTS["discussion:tbs"]
