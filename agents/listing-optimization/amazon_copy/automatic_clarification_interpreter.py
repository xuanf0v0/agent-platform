"""Convert one seller chat reply into typed clarification answers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError

from amazon_copy.automatic_models import ClarificationAnswer  # noqa: TC001
from amazon_copy.optimizer_runtime import resolve_client

if TYPE_CHECKING:
    from amazon_copy.automatic_models import (
        AutomaticOptimizationContext,
        AutomaticOptimizationDependencies,
    )
    from amazon_copy.llm import LLMClient
    from amazon_copy.review.models import ClarificationQuestion


class _Interpretation(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    answers: tuple[ClarificationAnswer, ...] = ()


def interpret_clarification_reply(
    llm: LLMClient,
    questions: tuple[ClarificationQuestion, ...],
    reply: str,
) -> tuple[ClarificationAnswer, ...]:
    """Extract only explicit seller decisions for the active questions."""
    payload = {
        "questions": [
            {
                "question_code": question.code,
                "fact_key": question.fact_key,
                "question": question.question_zh,
                "evidence_needed": question.evidence_needed,
                "claim_terms": list(question.claim_terms),
            }
            for question in questions
        ],
        "seller_reply": reply,
    }
    system = (
        "Extract seller decisions for the supplied questions only. Return JSON with an answers "
        "array. Each answer has question_code, action confirm or remove, and value. Confirm only "
        "facts explicitly stated by the seller. Use remove when the seller cannot confirm a claim "
        "or approves conservative deletion. Omit unanswered questions. Never infer product facts."
    )
    raw = llm.complete(
        system=system,
        user=json.dumps(payload, ensure_ascii=False),
        temperature=0,
        max_tokens=1200,
    )
    try:
        interpreted = _Interpretation.model_validate_json(raw)
    except ValidationError:
        return ()
    allowed_codes = {question.code for question in questions}
    seen: set[str] = set()
    accepted: list[ClarificationAnswer] = []
    for answer in interpreted.answers:
        if answer.question_code not in allowed_codes or answer.question_code in seen:
            continue
        seen.add(answer.question_code)
        accepted.append(answer)
    return tuple(accepted)


def interpret_clarification_context(
    context: AutomaticOptimizationContext,
    questions: tuple[ClarificationQuestion, ...],
    dependencies: AutomaticOptimizationDependencies,
) -> AutomaticOptimizationContext | None:
    """Return a structured resume context when the seller reply is understood."""
    if not context.clarification_reply or context.clarification_answers:
        return None
    answers = interpret_clarification_reply(
        resolve_client(dependencies.llm, dependencies.settings),
        questions,
        context.clarification_reply,
    )
    if not answers:
        return None
    return context.model_copy(
        update={"clarification_answers": answers, "clarification_reply": None}
    )


__all__ = ["interpret_clarification_context", "interpret_clarification_reply"]
