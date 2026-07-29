"""Fail-fast shared budget for LLM completions."""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amazon_copy.llm.base import LLMClient


class CallLimitError(Exception):
    """Raised before a completion that would exceed the budget."""


class CallCounter:
    """Count calls across wrapped clients and enforce a hard cap."""

    def __init__(self, max_calls: int) -> None:
        if max_calls < 1:
            message = f"max_calls must be >= 1, got {max_calls}"
            raise ValueError(message)
        self._max_calls = max_calls
        self._count = 0
        self._lock = Lock()

    @property
    def count(self) -> int:
        return self._count

    @property
    def max_calls(self) -> int:
        return self._max_calls

    def increment(self) -> None:
        with self._lock:
            if self._count >= self._max_calls:
                message = f"LLM call limit of {self._max_calls} exceeded"
                raise CallLimitError(message)
            self._count += 1

    def wrap(self, llm: LLMClient) -> LLMClient:
        return _CountedLLM(llm, self)


class _CountedLLM:
    def __init__(self, inner: LLMClient, counter: CallCounter) -> None:
        self._inner = inner
        self._counter = counter

    @property
    def call_count(self) -> int:
        return self._inner.call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        self._counter.increment()
        return self._inner.complete(system, user, **kwargs)
