"""Vendored MCP fixture smoke."""

from __future__ import annotations

import asyncio

from amazon_create.mcp.fixture_server import build_fixture_provider
from amazon_create.mcp.protocol import ResearchQuery


def test_fixture_provider_keyword() -> None:
    provider = build_fixture_provider("fresh")

    async def _run() -> int:
        async with provider.open_session() as session:
            result = await session.call(
                ResearchQuery(role="keyword", query="hardware cloth", marketplace="US")
            )
            return len(result.claims)

    assert asyncio.run(_run()) >= 0
