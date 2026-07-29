"""Tests for multi-agent MCP research lanes (Task 13).

Coverage:
- ``LaneOutcome`` / ``ResearchBundle`` dataclass invariants
- ``build_queries`` from both string and ``StudioRequest``
- ``has_competitor_signal`` detection
- ``normalize_result`` claim normalization
- Integration: five-lane complete quorum
- Integration: missing provider → source_only
- Integration: one failure → degraded without inventing claims
- Integration: concurrent execution (event-based, no sleep flakiness)
- Integration: competitor not_applicable
- Integration: budget charged on each call
- Integration: budget exhaustion propagates gracefully
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from amazon_copy.agents.mcp_research import ResearchBundle, run_research_lanes
from amazon_copy.mcp.client import FakeProvider, FakeSession
from amazon_copy.mcp.fixture_server import build_fixture_provider
from amazon_copy.mcp.protocol import (
    ALL_ROLES,
    ResearchClaim,
    ResearchError,
    ResearchQuery,
    ResearchResult,
    ResearchSession,
)
from amazon_copy.orchestrator.budgets import BudgetLedger, BudgetLimits
from amazon_copy.orchestrator.research_nodes import (
    LaneOutcome,
    build_queries,
    has_competitor_signal,
    normalize_result,
)
from amazon_copy.schemas.listing_format import ListingFormatTemplate
from amazon_copy.schemas.studio_input import StudioRequest

# ── Unit: LaneOutcome ────────────────────────────────────────────────────


class TestLaneOutcome:
    """LaneOutcome construction and field access."""

    def test_success_outcome(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[ResearchClaim(key="title", value="USB Hub", authority="test", confidence=0.9)],
        )
        outcome = LaneOutcome(role="product", status="success", result=result)
        assert outcome.role == "product"
        assert outcome.status == "success"
        assert outcome.result is result
        assert outcome.error is None

    def test_failed_outcome(self) -> None:
        outcome = LaneOutcome(role="keyword", status="failed", error="timeout")
        assert outcome.status == "failed"
        assert outcome.result is None
        assert outcome.error == "timeout"

    def test_not_applicable_outcome(self) -> None:
        outcome = LaneOutcome(role="competitor", status="not_applicable")
        assert outcome.status == "not_applicable"
        assert outcome.result is None
        assert outcome.error is None


# ── Unit: ResearchBundle ────────────────────────────────────────────────


class TestResearchBundle:
    """ResearchBundle dataclass invariants."""

    def test_source_only_bundle(self) -> None:
        bundle = ResearchBundle(lanes={}, mode="source_only", claim_ids=[], gaps=sorted(ALL_ROLES))
        assert bundle.mode == "source_only"
        assert bundle.lanes == {}
        assert bundle.claim_ids == []
        assert bundle.gaps == sorted(ALL_ROLES)

    def test_complete_bundle(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[ResearchClaim(key="title", value="Hub", authority="t", confidence=0.9)],
        )
        outcome = LaneOutcome(role="product", status="success", result=result)
        bundle = ResearchBundle(
            lanes={"product": outcome},
            mode="complete",
            claim_ids=["title"],
            gaps=[],
        )
        assert bundle.mode == "complete"
        assert bundle.claim_ids == ["title"]


# ── Unit: build_queries ─────────────────────────────────────────────────


class TestBuildQueries:
    """Query construction from various inputs."""

    def test_from_plain_string(self) -> None:
        queries = build_queries("USB-C Hub for travel")
        assert set(queries) == ALL_ROLES
        for role in ALL_ROLES:
            q = queries[role]
            assert q.role == role
            assert q.query == "USB-C Hub for travel"
            assert q.marketplace == "US"

    def test_from_studio_request(self) -> None:
        req = StudioRequest(
            title="Premium USB-C Hub",
            bullets=("7-in-1 design", "4K HDMI support"),
            format_template=ListingFormatTemplate(),
            seller_assertions=(),
            evidence_gaps=(),
            request_hash="abc123",
            brand="TechConnect",
            category="Electronics",
        )
        queries = build_queries(req)
        assert set(queries) == ALL_ROLES
        # Product query includes brand
        assert "TechConnect" in queries["product"].query
        # Keyword query includes category
        assert "Electronics" in queries["keyword"].query
        # Policy query includes marketplace
        assert "US" in queries["policy"].query
        # Competitor query includes brand
        assert "TechConnect" in queries["competitor"].query
        # Shopper query includes brand
        assert "TechConnect" in queries["shopper"].query


# ── Unit: has_competitor_signal ──────────────────────────────────────────


class TestHasCompetitorSignal:
    """Competitor signal detection."""

    def test_string_assumes_signal(self) -> None:
        assert has_competitor_signal("some text") is True

    def test_studio_request_with_brand(self) -> None:
        req = StudioRequest(
            title="Hub",
            bullets=("test",),
            format_template=ListingFormatTemplate(),
            seller_assertions=(),
            evidence_gaps=(),
            request_hash="h",
            brand="TechConnect",
        )
        assert has_competitor_signal(req) is True

    def test_studio_request_with_asin(self) -> None:
        req = StudioRequest(
            title="Hub",
            bullets=("test",),
            format_template=ListingFormatTemplate(),
            seller_assertions=(),
            evidence_gaps=(),
            request_hash="h",
            asin="B0ABCDEFGH",
        )
        assert has_competitor_signal(req) is True

    def test_studio_request_without_signal(self) -> None:
        req = StudioRequest(
            title="Hub",
            bullets=("test",),
            format_template=ListingFormatTemplate(),
            seller_assertions=(),
            evidence_gaps=(),
            request_hash="h",
        )
        assert has_competitor_signal(req) is False


# ── Unit: normalize_result ──────────────────────────────────────────────


class TestNormalizeResult:
    """Claim normalization invariants."""

    def test_content_hash_added_when_missing(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[ResearchClaim(key="k", value="hello", authority="a", confidence=0.5)],
            fixture=True,
        )
        n = normalize_result(result)
        assert n.claims[0].content_hash != ""
        assert len(n.claims[0].content_hash) == 16

    def test_content_hash_preserved_when_present(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[
                ResearchClaim(
                    key="k", value="hello", authority="a",
                    confidence=0.5, content_hash="abcdef1234567890",
                )
            ],
            fixture=True,
        )
        n = normalize_result(result)
        assert n.claims[0].content_hash == "abcdef1234567890"

    def test_empty_key_renamed(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[ResearchClaim(key="", value="hello", authority="a", confidence=0.5)],
        )
        n = normalize_result(result)
        assert n.claims[0].key == "unnamed"

    def test_fixture_flag_preserved(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[ResearchClaim(key="k", value="v", authority="a", confidence=0.5)],
            fixture=True,
        )
        n = normalize_result(result)
        assert n.fixture is True

    def test_non_fixture_flag_preserved(self) -> None:
        result = ResearchResult(
            role="product",
            claims=[ResearchClaim(key="k", value="v", authority="a", confidence=0.5)],
            fixture=False,
        )
        n = normalize_result(result)
        assert n.fixture is False


# ── Integration: run_research_lanes ──────────────────────────────────────


class TestRunResearchLanes:
    """Integration tests for the full research lane execution."""

    @pytest.mark.asyncio
    async def test_five_lanes_complete_quorum(self) -> None:
        """Five successful lanes produce a 'complete' bundle."""
        provider = build_fixture_provider("fresh")
        bundle = await run_research_lanes("USB-C Hub", provider)

        assert bundle.mode == "complete", f"Expected complete, got {bundle.mode}"
        assert len(bundle.lanes) == 5
        for role in ALL_ROLES:
            outcome = bundle.lanes[role]
            assert outcome.status == "success", f"{role} should succeed, got {outcome.status}"
            assert outcome.result is not None
        assert bundle.gaps == []

    @pytest.mark.asyncio
    async def test_missing_provider_source_only(self) -> None:
        """No provider returns 'source_only' immediately without running lanes."""
        bundle = await run_research_lanes("USB-C Hub", provider=None)

        assert bundle.mode == "source_only"
        assert bundle.lanes == {}
        assert bundle.gaps == sorted(ALL_ROLES)
        assert bundle.claim_ids == []

    @pytest.mark.asyncio
    async def test_one_failure_returns_degraded(self) -> None:
        """A single lane failure produces 'degraded' without inventing claims.

        Note: the quorum rule is product + policy + (keyword OR shopper).
        Failing only *keyword* still gives ``complete`` because *shopper*
        satisfies the OR.  We fail *product* instead, which breaks quorum.
        """
        call_count = 0

        class _FailingSession(FakeSession):
            async def call(self, query: ResearchQuery) -> ResearchResult:
                nonlocal call_count
                call_count += 1
                if query.role == "product":
                    raise ResearchError(
                        code="PROVIDER_DOWN",
                        message="Product service unavailable",
                    )
                return await super().call(query)

        class _FailingProvider(FakeProvider):
            @asynccontextmanager
            async def open_session(self) -> AsyncIterator[ResearchSession]:
                yield _FailingSession()

        provider = _FailingProvider()
        bundle = await run_research_lanes("USB-C Hub", provider)

        assert bundle.mode == "degraded"
        assert "product" in bundle.gaps
        assert bundle.lanes["product"].status == "failed"
        assert bundle.lanes["product"].error is not None

        # Other lanes still succeeded
        assert bundle.lanes["keyword"].status == "success"
        assert bundle.lanes["policy"].status == "success"
        assert bundle.lanes["shopper"].status == "success"

        # The failing lane consumed one call
        assert call_count == 5, "All 5 lanes should have called session.call()"

    @pytest.mark.asyncio
    async def test_concurrent_execution(self) -> None:
        """Lanes execute concurrently — proven by interleaving two lanes."""
        started_a = False
        started_b = False
        gate_a = anyio.Event()
        gate_b = anyio.Event()

        class _SyncSession(FakeSession):
            async def call(self, query: ResearchQuery) -> ResearchResult:
                nonlocal started_a, started_b
                if query.role == "product":
                    started_a = True
                    gate_a.set()  # tell lane B that A is inside call()
                    await gate_b.wait()  # block until lane B also enters call()
                elif query.role == "keyword":
                    await gate_a.wait()  # wait for lane A to enter call()
                    started_b = True
                    gate_b.set()  # unblock lane A
                return await super().call(query)

        class _SyncProvider(FakeProvider):
            @asynccontextmanager
            async def open_session(self) -> AsyncIterator[ResearchSession]:
                yield _SyncSession()

        provider = _SyncProvider()
        bundle = await run_research_lanes("USB-C Hub", provider)

        assert bundle.mode == "complete"
        assert started_a, "Lane A (product) should have started"
        assert started_b, "Lane B (keyword) should have started while A was blocked"

    @pytest.mark.asyncio
    async def test_competitor_not_applicable(self) -> None:
        """Competitor is 'not_applicable' when request has no signal."""
        req = StudioRequest(
            title="Premium USB-C Hub",
            bullets=("7-in-1 design",),
            format_template=ListingFormatTemplate(),
            seller_assertions=(),
            evidence_gaps=(),
            request_hash="abc",
        )
        provider = build_fixture_provider("fresh")
        bundle = await run_research_lanes(req, provider)

        assert bundle.lanes["competitor"].status == "not_applicable"
        # product + policy + keyword + shopper all succeed → complete
        assert bundle.mode == "complete"

    @pytest.mark.asyncio
    async def test_budget_charged_on_each_call(self) -> None:
        """When budget is provided, each successful lane charges MCP budget."""
        ledger = BudgetLedger()
        provider = build_fixture_provider("fresh")
        bundle = await run_research_lanes("USB-C Hub", provider, budget=ledger)

        assert bundle.mode == "complete"
        # 5 lanes succeed, each reserves 1 MCP call; competitor also runs
        snapshot = await ledger.snapshot()
        assert snapshot.mcp_calls == 5, f"Expected 5 MCP calls, got {snapshot.mcp_calls}"

    @pytest.mark.asyncio
    async def test_budget_exhaustion_graceful(self) -> None:
        """When budget is exhausted, remaining lanes fail gracefully (degraded)."""
        # Only allow 1 MCP call — at most one lane succeeds
        ledger = BudgetLedger(BudgetLimits(max_mcp_calls=1))
        provider = build_fixture_provider("fresh")
        bundle = await run_research_lanes("USB-C Hub", provider, budget=ledger)

        successes = [r for r, o in bundle.lanes.items() if o.status == "success"]
        failures = [r for r, o in bundle.lanes.items() if o.status == "failed"]

        assert len(successes) >= 1, "At least one lane should have succeeded"
        assert len(failures) >= 1, "At least one lane should have failed due to budget"
        assert bundle.mode == "degraded"
        # Check that failures are due to budget
        for role in failures:
            assert "budget" in (bundle.lanes[role].error or ""), (
                f"{role} error should mention budget, got {bundle.lanes[role].error}"
            )

    @pytest.mark.asyncio
    async def test_only_competitor_not_applicable_degraded_still_possible(self) -> None:
        """If product fails but competitor is N/A, mode is degraded."""
        req = StudioRequest(
            title="Premium USB-C Hub",
            bullets=("7-in-1 design",),
            format_template=ListingFormatTemplate(),
            seller_assertions=(),
            evidence_gaps=(),
            request_hash="abc",
        )

        class _FailingProductSession(FakeSession):
            async def call(self, query: ResearchQuery) -> ResearchResult:
                if query.role == "product":
                    raise ResearchError(code="DOWN", message="product unavailable")
                return await super().call(query)

        class _FailingProductProvider(FakeProvider):
            @asynccontextmanager
            async def open_session(self) -> AsyncIterator[ResearchSession]:
                yield _FailingProductSession()

        provider = _FailingProductProvider()
        bundle = await run_research_lanes(req, provider)

        assert bundle.lanes["competitor"].status == "not_applicable"
        assert bundle.lanes["product"].status == "failed"
        assert bundle.mode == "degraded"
