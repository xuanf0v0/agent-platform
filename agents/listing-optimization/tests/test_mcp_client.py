"""Tests for the MCP protocol and client layer (Task 7)."""

from __future__ import annotations

import pytest

# Test 1 — import works without any MCP config dependency
from amazon_copy.mcp import (
    ALL_ROLES,
    BudgetedSession,
    CapabilityMissingError,
    CheckedSession,
    FakeProvider,
    FakeSession,
    McpClientConfig,
    ResearchClaim,
    ResearchError,
    ResearchQuery,
    ResearchResult,
    UnmappedToolError,
    build_fake_provider,
)


class TestImportWorks:
    """Verify the module is importable without external MCP SDK."""

    def test_all_public_names_are_accessible(self) -> None:
        assert isinstance(ResearchClaim, type)
        assert isinstance(ResearchError, type)
        assert isinstance(ResearchQuery, type)
        assert isinstance(ResearchResult, type)

    def test_all_roles_frozenset(self) -> None:
        assert ALL_ROLES == {"product", "keyword", "competitor", "policy", "shopper"}
        assert len(ALL_ROLES) == 5

    def test_mcp_client_config_defaults(self) -> None:
        config = McpClientConfig()
        assert config.max_payload_bytes == 100_000
        assert config.role_to_tool["product"] == "product_research"
        assert len(config.role_to_tool) == 5

    def test_build_fake_provider_returns_fake_provider(self) -> None:
        provider = build_fake_provider()
        assert isinstance(provider, FakeProvider)


class TestFakeProvider:
    """Fake provider lists 5 roles and returns a claim."""

    @pytest.mark.asyncio
    async def test_lists_all_five_roles(self) -> None:
        async with build_fake_provider().open_session() as session:
            caps = await session.list_capabilities()

        assert caps == {"product", "keyword", "competitor", "policy", "shopper"}
        assert len(caps) == 5

    @pytest.mark.asyncio
    async def test_call_returns_research_result_with_claim(self) -> None:
        async with build_fake_provider().open_session() as session:
            result = await session.call(
                ResearchQuery(role="product", query="USB-C Hub")
            )

        assert isinstance(result, ResearchResult)
        assert result.role == "product"
        assert len(result.claims) >= 1
        assert result.claims[0].key == "mock_key"
        assert "USB-C Hub" in result.claims[0].value
        assert result.claims[0].confidence == 0.85
        assert result.fixture is True

    @pytest.mark.asyncio
    async def test_fixture_override(self) -> None:
        fixture = ResearchResult(
            role="keyword",
            claims=[
                ResearchClaim(
                    key="top_kw",
                    value="usb c hub",
                    authority="fixture",
                    confidence=0.99,
                )
            ],
        )
        async with build_fake_provider(
            fixtures={"keyword": fixture}
        ).open_session() as session:
            result = await session.call(
                ResearchQuery(role="keyword", query="keywords")
            )

        assert result is fixture
        assert result.claims[0].key == "top_kw"

    @pytest.mark.asyncio
    async def test_call_count_tracks(self) -> None:
        provider = build_fake_provider()
        async with provider.open_session() as session:
            assert session.call_count == 0
            _ = await session.call(ResearchQuery(role="product", query="test"))
            assert session.call_count == 1
            _ = await session.call(ResearchQuery(role="keyword", query="test"))
            assert session.call_count == 2


class TestMissingCapability:
    """Missing capability raises error BEFORE dispatching the inner call."""

    @pytest.mark.asyncio
    async def test_unadvertised_role_raises_and_does_not_call(self) -> None:
        inner = FakeSession()
        inner.restrict_capabilities({"product", "keyword"})
        config = McpClientConfig()
        checked = CheckedSession(inner, config)

        # Prime capabilities
        caps = await checked.list_capabilities()
        assert caps == {"product", "keyword"}

        # Trying "shopper" should fail before inner.call() is invoked
        with pytest.raises(CapabilityMissingError) as exc_info:
            await checked.call(
                ResearchQuery(role="shopper", query="buying intent")
            )

        assert exc_info.value.code == "CAPABILITY_MISSING"
        assert "shopper" in exc_info.value.message
        # Inner call was never reached
        assert inner.call_count == 0

    @pytest.mark.asyncio
    async def test_empty_capabilities_rejects_all_roles(self) -> None:
        inner = FakeSession()
        inner.restrict_capabilities(set())
        checked = CheckedSession(inner, McpClientConfig())

        with pytest.raises(CapabilityMissingError):
            await checked.call(
                ResearchQuery(role="product", query="test")
            )

        assert inner.call_count == 0


class TestUnmappedTool:
    """Unmapped tool raises error BEFORE dispatching the inner call."""

    @pytest.mark.asyncio
    async def test_no_tool_mapped_raises_unmapped_tool_error(self) -> None:
        inner = FakeSession()
        # Empty mapping — no role has a tool
        config = McpClientConfig(role_to_tool={})
        checked = CheckedSession(inner, config)

        with pytest.raises(UnmappedToolError) as exc_info:
            await checked.call(
                ResearchQuery(role="product", query="test")
            )

        assert exc_info.value.code == "UNMAPPED_TOOL"
        assert "product" in exc_info.value.message
        assert inner.call_count == 0

    @pytest.mark.asyncio
    async def test_partial_tool_mapping(self) -> None:
        inner = FakeSession()
        # Only "product" is mapped, not "keyword"
        config = McpClientConfig(role_to_tool={"product": "product_research"})
        checked = CheckedSession(inner, config)

        # Product call should succeed (passes capability + tool check)
        result = await checked.call(
            ResearchQuery(role="product", query="USB Hub")
        )
        assert isinstance(result, ResearchResult)
        assert inner.call_count == 1

        # Keyword call should fail — capability exists, but no tool mapping
        with pytest.raises(UnmappedToolError):
            await checked.call(
                ResearchQuery(role="keyword", query="keywords")
            )
        # call_count unchanged (inner.call was NOT invoked)
        assert inner.call_count == 1


class TestBudgetedSession:
    """BudgetedSession wraps MCP budget checks around a session."""

    @pytest.mark.asyncio
    async def test_without_budget_passthrough(self) -> None:
        inner = FakeSession()
        session = BudgetedSession(inner, budget=None)

        caps = await session.list_capabilities()
        assert len(caps) == 5

        result = await session.call(ResearchQuery(role="product", query="test"))
        assert isinstance(result, ResearchResult)
        assert inner.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausts_after_twenty_mcp_reserves(self) -> None:
        """BudgetLedger default max_mcp_calls=20; the 21st reserve fails."""
        from amazon_copy.orchestrator.budgets import BudgetLedger  # noqa: PLC0415

        # Relax deadline so it doesn't interfere
        ledger = BudgetLedger()
        inner = FakeSession()
        session = BudgetedSession(inner, budget=ledger)

        # 20 successful calls
        for i in range(20):
            result = await session.call(
                ResearchQuery(
                    role="product",
                    query=f"call-{i}",
                )
            )
            assert isinstance(result, ResearchResult)

        # The 21st operation fails
        with pytest.raises(ResearchError) as exc_info:
            await session.call(
                ResearchQuery(role="product", query="call-21")
            )

        assert exc_info.value.code == "BUDGET_EXHAUSTED"
        # Inner call count shows 20 actual dispatches
        assert inner.call_count == 20

    @pytest.mark.asyncio
    async def test_list_capabilities_also_reserves_budget(self) -> None:
        """list_capabilities() also consumes budget."""
        from amazon_copy.orchestrator.budgets import BudgetLedger  # noqa: PLC0415

        ledger = BudgetLedger()
        inner = FakeSession()
        session = BudgetedSession(inner, budget=ledger)

        # list_capabilities reserves one MCP slot
        _ = await session.list_capabilities()
        assert inner.call_count == 0  # session.call never invoked

        # 19 more call invocations = 20 total reserves
        for i in range(19):
            _ = await session.call(ResearchQuery(role="product", query=f"c-{i}"))

        # 21st should fail
        with pytest.raises(ResearchError, match="BUDGET_EXHAUSTED"):
            await session.call(ResearchQuery(role="product", query="fail"))


class TestResearchError:
    """ResearchError hierarchy and construction."""

    def test_capability_missing_is_research_error(self) -> None:
        err = CapabilityMissingError("shopper", {"product", "keyword"})
        assert isinstance(err, ResearchError)
        assert err.code == "CAPABILITY_MISSING"

    def test_unmapped_tool_is_research_error(self) -> None:
        err = UnmappedToolError("shopper")
        assert isinstance(err, ResearchError)
        assert err.code == "UNMAPPED_TOOL"

    def test_research_error_string_representation(self) -> None:
        err = ResearchError(code="TEST", message="something went wrong")
        assert str(err) == "[TEST] something went wrong"
