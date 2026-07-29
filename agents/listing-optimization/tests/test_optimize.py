from __future__ import annotations

import json

import pytest
from amazon_copy.llm import MockLLM
from amazon_copy.modes import optimize, seo
from amazon_copy.schemas import BulletPoint, ProductInput
from pydantic import ValidationError


def _product() -> ProductInput:
    return ProductInput(
        product="USB C Hub",
        market="US",
        instruction="Improve query relevance",
        rootwords=["usb"],
        keywords=["usb c hub"],
    )


def _source_bullets() -> list[str]:
    return [f"Verified source benefit {index} " + "x" * 100 for index in range(1, 6)]


class _OptimizeLLM:
    call_count = 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self.call_count += 1
        rows = []
        for index in range(1, 6):
            text = f"Optimized shopper benefit {index} " + "x" * 165
            rows.append(
                {
                    "text": text,
                    "text_zh": f"优化后的卖点 {index}",
                    "change_rationale": "**Added shopper intent while preserving verified facts**",
                }
            )
        return json.dumps({"bullets": rows})


class _RetryOptimizeLLM(_OptimizeLLM):
    def complete(self, system: str, user: str, **kwargs: object) -> str:
        if self.call_count == 0:
            self.call_count += 1
            rows = [
                {
                    "text": f"Too short {index}.",
                    "text_zh": f"过短 {index}",
                    "change_rationale": "**Initial attempt**",
                }
                for index in range(1, 6)
            ]
            return json.dumps({"bullets": rows})
        return super().complete(system, user, **kwargs)


def test_optimize_accepts_151_to_200_and_returns_rationales() -> None:
    result = optimize(_product(), _source_bullets(), llm=_OptimizeLLM())
    assert len(result) == 5
    assert all(151 <= bullet.plain_len <= 200 for bullet in result)
    assert all(bullet.text_zh for bullet in result)
    assert all(bullet.change_rationale.startswith("**") for bullet in result)
    assert all(not bullet.text.endswith(".") for bullet in result)


def test_optimize_retries_one_provider_schema_violation() -> None:
    llm = _RetryOptimizeLLM()

    result = optimize(_product(), _source_bullets(), llm=llm)

    assert len(result) == 5
    assert llm.call_count == 2


def test_optimize_mock_uses_only_optimize_role() -> None:
    llm = MockLLM("optimize_bp")
    result = optimize(_product(), _source_bullets(), llm=llm)
    assert len(result) == 5
    assert llm.call_count == 1


def test_optimize_accepts_existing_bullet_models_as_pipeline_input() -> None:
    source = [BulletPoint(text=text, text_zh="原文") for text in _source_bullets()]
    result = optimize(_product(), source, llm=MockLLM("optimize_bp"))
    assert len(result) == 5


@pytest.mark.parametrize("bullets", [None, [], ["", "b", "c", "d", "e"]])
def test_optimize_rejects_missing_or_empty_bp(bullets: list[str] | None) -> None:
    with pytest.raises(ValidationError, match="bullets"):
        optimize(_product(), bullets, llm=MockLLM("optimize_bp"))


def test_seo_entry_is_pure_and_rejects_missing_bullets() -> None:
    result = seo(
        title="USB C Hub",
        bullets=_source_bullets(),
        intents=["shopper benefit"],
        rootwords=["usb"],
        keywords=["usb c hub"],
    )
    assert result.keyword_count == 1
    with pytest.raises(ValidationError, match="bullets"):
        seo(title="USB C Hub", bullets=[])
