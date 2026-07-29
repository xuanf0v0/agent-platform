"""MCP client implementations for Amazon research agents.

Provides:
- :class:`FakeSession` / :class:`FakeProvider` — in-memory test doubles.
- :class:`BudgetedSession` — wraps any session with MCP budget pre-checks.
- :class:`CheckedSession` — wraps any session with capability + tool-map
  validation *before* dispatching the inner call.
- :func:`build_fake_provider` — convenience factory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from amazon_create.mcp.protocol import (
    ALL_ROLES,
    ResearchClaim,
    ResearchError,
    ResearchQuery,
    ResearchResult,
    ResearchSession,
)

if TYPE_CHECKING:
    from amazon_create.mcp.protocol import ResearchProvider  # noqa: F401
    from amazon_create.mcp.protocol import ResearchRole  # noqa: F401

# ── Error subclasses ─────────────────────────────────────────────────────


class CapabilityMissingError(ResearchError):
    """Raised when a session does not advertise the requested role."""

    def __init__(self, role: str, capabilities: set[str]) -> None:
        super().__init__(
            code="CAPABILITY_MISSING",
            message=(
                f"Role {role!r} is not in session capabilities: "
                f"{sorted(capabilities)}"
            ),
        )


class UnmappedToolError(ResearchError):
    """Raised when no MCP tool is configured for the requested role."""

    def __init__(self, role: str) -> None:
        super().__init__(
            code="UNMAPPED_TOOL",
            message=f"No MCP tool mapped for role {role!r} in McpClientConfig",
        )


# ── Config ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class McpClientConfig:
    """Client configuration mapping roles to MCP tool names."""

    role_to_tool: dict[str, str] = field(default_factory=lambda: {
        "product": "product_research",
        "keyword": "keyword_research",
        "competitor": "competitor_research",
        "policy": "policy_research",
        "shopper": "shopper_intent",
    })
    max_payload_bytes: int = 100_000


# ── Fake test doubles ────────────────────────────────────────────────────


class FakeSession:
    """In-memory research session backed by optional fixtures.

    Attributes:
        call_count: Tracks how many times :meth:`call` has been invoked.
    """

    def __init__(self, fixtures: dict[str, ResearchResult] | None = None) -> None:
        self._fixtures = fixtures or {}
        self._capabilities = set(ALL_ROLES)
        self.call_count = 0

    async def list_capabilities(self) -> set[str]:
        """Return all five research roles."""
        return set(self._capabilities)

    async def call(self, query: ResearchQuery) -> ResearchResult:
        """Return a fixture result or a stock mock result."""
        self.call_count += 1
        fixture = self._fixtures.get(query.role)
        if fixture is not None:
            return fixture
        return ResearchResult(
            role=query.role,
            claims=[
                ResearchClaim(
                    key="mock_key",
                    value=f"Mock result for {query.query}",
                    authority="fake_session",
                    confidence=0.85,
                )
            ],
        )

    def restrict_capabilities(self, roles: set[str]) -> None:
        """Narrow the advertised capabilities (for testing)."""
        self._capabilities = roles


class FakeProvider:
    """In-memory research provider for testing."""

    def __init__(self, fixtures: dict[str, ResearchResult] | None = None) -> None:
        self._fixtures = fixtures or {}

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[FakeSession]:
        """Yield a :class:`FakeSession`."""
        session = FakeSession(self._fixtures)
        try:
            yield session
        finally:
            pass


# ── Budgeted wrapper ─────────────────────────────────────────────────────


class BudgetedSession:
    """Wraps a :class:`ResearchSession` with MCP budget pre-checks.

    On every :meth:`list_capabilities` and :meth:`call`, if a
    ``BudgetLedger`` is provided, one ``MCP`` resource is reserved
    before the operation proceeds.  If the reservation is denied,
    a :class:`ResearchError` is raised immediately.
    """

    def __init__(
        self,
        inner: ResearchSession,
        budget: Any | None = None,  # BudgetLedger from orchestrator.budgets
    ) -> None:
        self._inner = inner
        self._budget = budget

    async def list_capabilities(self) -> set[str]:
        await self._reserve_or_raise()
        return await self._inner.list_capabilities()

    async def call(self, query: ResearchQuery) -> ResearchResult:
        await self._reserve_or_raise()
        return await self._inner.call(query)

    # ── helpers ───────────────────────────────────────────────────────

    async def _reserve_or_raise(self) -> None:
        if self._budget is None:
            return
        from amazon_create.orchestrator.budgets import BudgetResource  # noqa: PLC0415

        outcome = await self._budget.reserve(BudgetResource.MCP)
        if hasattr(outcome, "status") and outcome.status != "reserved":
            raise ResearchError(
                code="BUDGET_EXHAUSTED",
                message=f"MCP budget exhausted: {outcome.status}",
            )


# ── Checked wrapper ──────────────────────────────────────────────────────


class CheckedSession:
    """Wraps a :class:`ResearchSession` with capability and tool-map checks.

    Validates *before* dispatching to the inner session:
    1. The requested role is in the session's advertised capabilities.
    2. The requested role has a tool mapping in ``McpClientConfig``.

    If either check fails the corresponding :class:`ResearchError` subclass
    is raised and the inner session is never called (``call_count`` stays 0).
    """

    def __init__(self, inner: ResearchSession, config: McpClientConfig) -> None:
        self._inner = inner
        self._config = config
        self._capabilities: set[str] | None = None

    async def list_capabilities(self) -> set[str]:
        caps = await self._inner.list_capabilities()
        self._capabilities = caps
        return caps

    async def call(self, query: ResearchQuery) -> ResearchResult:
        caps = self._capabilities
        if caps is None:
            caps = await self._inner.list_capabilities()
            self._capabilities = caps

        if query.role not in caps:
            raise CapabilityMissingError(query.role, caps)

        if query.role not in self._config.role_to_tool:
            raise UnmappedToolError(query.role)

        return await self._inner.call(query)


# ── Factory ──────────────────────────────────────────────────────────────


def build_fake_provider(
    fixtures: dict[str, ResearchResult] | None = None,
) -> FakeProvider:
    """Build a :class:`FakeProvider` (test double).

    Args:
        fixtures: Optional mapping of role name to :class:`ResearchResult`
            that the provider should return for that role.

    Returns:
        A :class:`FakeProvider` instance.
    """
    return FakeProvider(fixtures=fixtures or {})
