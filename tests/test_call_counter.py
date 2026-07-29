from __future__ import annotations

import pytest
from amazon_copy.llm import MockLLM
from amazon_copy.orchestrator._counter import CallCounter, CallLimitError


def test_max_one_allows_one_then_fails_before_inner_call() -> None:
    inner = MockLLM("research_product")
    wrapped = CallCounter(max_calls=1).wrap(inner)
    wrapped.complete("system", "user")

    with pytest.raises(CallLimitError, match="limit of 1"):
        wrapped.complete("system", "user")

    assert inner.call_count == 1


def test_invalid_limit_rejected() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        CallCounter(max_calls=0)
