"""Common interface and configuration errors for LLM adapters."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable


class ConfigError(Exception):
    """Raised when an LLM role or provider configuration is invalid."""


@runtime_checkable
class LLMClient(Protocol):
    """Minimal synchronous completion interface used by agents."""

    @property
    def call_count(self) -> int:
        """Return the number of completion calls made by this client."""
        ...

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Return one synchronous model completion."""
        ...

    def stream(self, system: str, user: str, **kwargs: object) -> Iterator[str]:
        """Yield one model completion without persisting partial output."""
        ...

    def select_tool(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        """Let the model choose one optional tool call."""
        ...
