"""Facade over the full studio pipeline — synchronous and async entrypoints.

Usage
-----
Single-request::

    from amazon_copy.studio import StudioService

    service = StudioService()
    state = service.optimize_listing("USB-C Hub 7-in-1")
    print(state.outcome, state.winner)

Async::

    state = await service.optimize_listing_async("USB-C Hub 7-in-1")
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from amazon_copy.orchestrator.studio_graph import run_studio_pipeline

if TYPE_CHECKING:
    from amazon_copy.config import Settings
    from amazon_copy.mcp.protocol import ResearchProvider
    from amazon_copy.orchestrator.budgets import BudgetLedger
    from amazon_copy.orchestrator.state import StudioState


class StudioService:
    """Convenience facade that wraps the full six-stage studio pipeline.

    When constructed without arguments the pipeline loads ``Settings()`` from
    the process environment / ``.env``.  Fixture MCP research is used only when
    ``settings.mock`` is ``True``; otherwise research runs in ``source_only``
    mode until live MCP wiring is available.

    Parameters
    ----------
    settings:
        Application settings.  Pass ``None`` (default) to load from env.
    provider:
        MCP research provider.  ``None`` means the pipeline auto-creates
        a fixture provider in mock mode, or uses ``source_only`` research
        when not mocked.
    budget:
        Optional :class:`~amazon_copy.orchestrator.budgets.BudgetLedger`
        to cap MCP calls.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        provider: ResearchProvider | None = None,
        budget: BudgetLedger | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._budget = budget

    async def optimize_listing_async(self, source_text: str) -> StudioState:
        """Run the full studio pipeline asynchronously.

        Parameters
        ----------
        source_text:
            Raw product text to optimise (title, description, bullet points,
            etc.)

        Returns
        -------
        StudioState
            Frozen snapshot of the pipeline run.  Check ``.outcome`` for
            the overall result (``"success"``, ``"degraded"``,
            ``"no_winner"``, or ``"failure"``).
        """
        return await run_studio_pipeline(
            source_text,
            settings=self._settings,
            provider=self._provider,
            budget=self._budget,
        )

    def optimize_listing(self, source_text: str) -> StudioState:
        """Run the full studio pipeline synchronously.

        This is a blocking convenience wrapper around
        :meth:`optimize_listing_async`.
        """
        return asyncio.run(self.optimize_listing_async(source_text))


__all__ = ["StudioService"]
