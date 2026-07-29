from __future__ import annotations

from dataclasses import dataclass, field

from amazon_copy.automatic_clarification_interpreter import interpret_clarification_reply
from amazon_copy.review.models import ClarificationQuestion


@dataclass(slots=True)
class _ReplyLLM:
    response: str
    prompts: list[str] = field(default_factory=list)

    @property
    def call_count(self) -> int:
        return len(self.prompts)

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        self.prompts.append(user)
        return self.response


def _question(code: str, fact_key: str) -> ClarificationQuestion:
    return ClarificationQuestion(
        code=code,
        finding_code="FACT_UNVERIFIED",
        fact_key=fact_key,
        question_zh=f"请确认 {fact_key}",
        evidence_needed="卖家确认",
    )


def test_interpreter_extracts_confirmed_and_removed_facts_from_one_reply() -> None:
    # Given: one seller reply contains an exact fact plus approval to remove another claim.
    llm = _ReplyLLM(
        '{"answers":['
        '{"question_code":"confirm_height","action":"confirm","value":"68 in and 48 in"},'
        '{"question_code":"confirm_rust","action":"remove","value":""}'
        "]}"
    )
    questions = (
        _question("confirm_height", "height"),
        _question("confirm_rust", "rust_resistance"),
    )

    # When: the reply is interpreted against the current clarification turn.
    answers = interpret_clarification_reply(llm, questions, "高度确认，防锈无法确认请删除")

    # Then: the pipeline receives typed answers rather than raw prose.
    assert [(answer.question_code, answer.action, answer.value) for answer in answers] == [
        ("confirm_height", "confirm", "68 in and 48 in"),
        ("confirm_rust", "remove", ""),
    ]


def test_interpreter_discards_answers_for_questions_not_in_current_turn() -> None:
    # Given: model output contains a hallucinated question code.
    llm = _ReplyLLM(
        '{"answers":['
        '{"question_code":"unknown","action":"confirm","value":"waterproof"}'
        "]}"
    )

    # When: the output is constrained to the active question set.
    answers = interpret_clarification_reply(
        llm,
        (_question("confirm_height", "height"),),
        "确认",
    )

    # Then: no unsupported fact reaches the optimization context.
    assert answers == ()
