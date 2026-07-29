"""Pre-materialization byte budgets for Streamable HTTP MCP responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, final

import httpx
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

MAX_MCP_RESPONSE_BYTES: Final[int] = 64_000
MAX_MCP_OPERATION_BYTES: Final[int] = 256_000
_MAX_CONTENT_LENGTH_DIGITS: Final[int] = 20


@final
class McpResponseLimitError(httpx.TransportError):
    """The remote response crossed its per-response or whole-operation budget."""

    def __init__(self, *, limit_bytes: int, observed_bytes: int) -> None:
        """Record only byte counts and a stable non-sensitive error message."""
        self.limit_bytes = limit_bytes
        self.observed_bytes = observed_bytes
        super().__init__("remote MCP response exceeded byte budget")


@final
class _BoundedAsyncByteStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, budget: McpResponseBudget) -> None:
        self._stream = stream
        self._budget = budget
        self._response_bytes = 0

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            try:
                self._response_bytes = self._budget.consume(
                    len(chunk),
                    response_bytes=self._response_bytes,
                )
            except McpResponseLimitError:
                await self._stream.aclose()
                raise
            yield chunk

    @override
    async def aclose(self) -> None:
        await self._stream.aclose()


@final
class McpResponseBudget:
    """Mutable counter shared by every HTTP response in one MCP operation."""

    __slots__ = (
        "_consumed_bytes",
        "_limit_hit",
        "operation_limit_bytes",
        "response_limit_bytes",
    )

    def __init__(
        self,
        *,
        response_limit_bytes: int = MAX_MCP_RESPONSE_BYTES,
        operation_limit_bytes: int = MAX_MCP_OPERATION_BYTES,
    ) -> None:
        """Create fixed per-response and aggregate operation ceilings."""
        self.response_limit_bytes = response_limit_bytes
        self.operation_limit_bytes = operation_limit_bytes
        self._consumed_bytes = 0
        self._limit_hit = False

    @property
    def consumed_bytes(self) -> int:
        """Return bytes observed across responses, including the rejected chunk."""
        return self._consumed_bytes

    @property
    def limit_hit(self) -> bool:
        """Return whether any response crossed either byte ceiling."""
        return self._limit_hit

    def consume(self, size: int, *, response_bytes: int) -> int:
        """Account for one network chunk before yielding it to the MCP SDK."""
        next_response = response_bytes + size
        self._consumed_bytes += size
        if next_response > self.response_limit_bytes:
            self._limit_hit = True
            raise McpResponseLimitError(
                limit_bytes=self.response_limit_bytes,
                observed_bytes=next_response,
            )
        if self._consumed_bytes > self.operation_limit_bytes:
            self._limit_hit = True
            raise McpResponseLimitError(
                limit_bytes=self.operation_limit_bytes,
                observed_bytes=self._consumed_bytes,
            )
        return next_response

    async def guard_response(self, response: httpx.Response) -> None:
        """Reject declared oversize bodies or wrap streaming bodies before reads."""
        declared = _content_length(response)
        if declared is not None and (
            declared > self.response_limit_bytes
            or self._consumed_bytes + declared > self.operation_limit_bytes
        ):
            self._limit_hit = True
            await response.aclose()
            limit = (
                self.response_limit_bytes
                if declared > self.response_limit_bytes
                else self.operation_limit_bytes
            )
            raise McpResponseLimitError(limit_bytes=limit, observed_bytes=declared)
        stream = response.stream
        if not isinstance(stream, httpx.AsyncByteStream):
            self._limit_hit = True
            await response.aclose()
            raise McpResponseLimitError(limit_bytes=self.response_limit_bytes, observed_bytes=0)
        response.stream = _BoundedAsyncByteStream(stream, self)


def _content_length(response: httpx.Response) -> int | None:
    if "content-length" not in response.headers:
        return None
    raw = response.headers["content-length"]
    if not raw.isascii() or not raw.isdecimal() or len(raw) > _MAX_CONTENT_LENGTH_DIGITS:
        return None
    return int(raw)


__all__ = [
    "MAX_MCP_OPERATION_BYTES",
    "MAX_MCP_RESPONSE_BYTES",
    "McpResponseBudget",
    "McpResponseLimitError",
]
