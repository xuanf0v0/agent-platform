"""Tests for Task 20 StudioService facade.

Coverage
--------
- StudioService construction and attribute defaults
- Sync and async optimize_listing both return a StudioState
- Calling the same request twice does not crash and produces unique run_ids
- Module import sanity
"""

from __future__ import annotations

import pytest

from amazon_copy.config import Settings
from amazon_copy.orchestrator.state import StudioState
from amazon_copy.studio import StudioService


def _mock_service() -> StudioService:
    return StudioService(settings=Settings(MOCK=True))


# ── StudioService ─────────────────────────────────────────────────────────


class TestStudioService:
    """StudioService construction and pipeline execution."""

    def test_construct_with_defaults(self) -> None:
        """Can construct with no arguments."""
        service = StudioService()
        assert service is not None

    def test_construct_explicit_none(self) -> None:
        """Passing None explicitly for all params works."""
        service = StudioService(settings=None, provider=None, budget=None)
        assert service is not None

    def test_optimize_listing_returns_studio_state(self) -> None:
        """Sync optimize_listing returns a StudioState with valid outcome."""
        service = _mock_service()
        state = service.optimize_listing("USB-C Hub 7-in-1")
        assert isinstance(state, StudioState)
        assert state.outcome in ("success", "no_winner", "failure")

    def test_same_request_does_not_crash_twice(self) -> None:
        """Repeat calls with the same text produce independent results."""
        service = _mock_service()
        state1 = service.optimize_listing("test")
        state2 = service.optimize_listing("test")
        assert isinstance(state1, StudioState)
        assert isinstance(state2, StudioState)
        assert state1.run_id != state2.run_id

    @pytest.mark.asyncio
    async def test_optimize_listing_async_returns_studio_state(self) -> None:
        """Async optimize_listing_async returns a StudioState."""
        service = _mock_service()
        state = await service.optimize_listing_async("USB-C Hub 7-in-1")
        assert isinstance(state, StudioState)
        assert state.outcome in ("success", "no_winner", "failure")

    def test_optimize_listing_returns_string_outcome(self) -> None:
        """State.outcome is a nonempty string."""
        service = _mock_service()
        state = service.optimize_listing("test")
        assert isinstance(state.outcome, str)
        assert len(state.outcome) > 0


# ── Module import sanity ──────────────────────────────────────────────────


class TestModuleImport:
    """Top-level imports resolve without error."""

    def test_studio_service_importable(self) -> None:
        """StudioService is importable from amazon_copy.studio."""
        from amazon_copy.studio import StudioService as S

        assert S is StudioService

    def test_studio_state_importable(self) -> None:
        """StudioState remains importable from orchestrator.state."""
        from amazon_copy.orchestrator.state import StudioState as S

        assert S is StudioState
