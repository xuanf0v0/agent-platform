"""SDK-free MCP protocol definitions for Amazon research agents.

Defines the core data types and structural protocols (interfaces)
that research sessions and providers must satisfy. No third-party
SDK dependency — pure Python with stdlib + typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ── Types ────────────────────────────────────────────────────────────────

ResearchRole = Literal["product", "keyword", "competitor", "policy", "shopper"]

ALL_ROLES: frozenset[str] = frozenset({
    "product",
    "keyword",
    "competitor",
    "policy",
    "shopper",
})

# ── Data containers ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResearchQuery:
    """A query to a research tool role."""

    role: ResearchRole
    query: str
    marketplace: str = "US"


@dataclass(frozen=True, slots=True)
class ResearchClaim:
    """A single research claim with provenance metadata."""

    key: str
    value: str
    authority: str
    confidence: float
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """The aggregated result of one research query."""

    role: ResearchRole
    claims: list[ResearchClaim]
    fixture: bool = True


# ── Errors ───────────────────────────────────────────────────────────────


class ResearchError(Exception):
    """Base error for MCP research failures."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# ── Protocols (structural interfaces) ────────────────────────────────────


@runtime_checkable
class ResearchSession(Protocol):
    """Protocol for an active research session.

    Implementations must provide the two async methods below.
    """

    async def list_capabilities(self) -> set[str]:
        """Return the set of roles this session supports."""

    async def call(self, query: ResearchQuery) -> ResearchResult:
        """Execute one research query and return the result."""


@runtime_checkable
class ResearchProvider(Protocol):
    """Protocol for a research provider that can open sessions.

    Usage::

        async with provider.open_session() as session:
            caps = await session.list_capabilities()
            result = await session.call(query)

    Implementations decorate ``open_session`` with
    ``@contextlib.asynccontextmanager``.
    """

    async def open_session(self) -> AsyncIterator[ResearchSession]:
        """Open a research session (async context manager).

        Yields a :class:`ResearchSession` that is valid until the
        ``async with`` block exits.
        """
        ...  # pragma: no cover
