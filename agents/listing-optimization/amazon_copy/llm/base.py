"""Common interfaces and configuration errors for LLM adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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


@runtime_checkable
class AsyncLLMClient(Protocol):
    """Minimal async completion interface used by studio agents."""

    @property
    def call_count(self) -> int:
        """Return the number of completion calls made by this client."""
        ...

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        """Return one async model completion."""
        ...
