"""Research access over vendored MCP (fixture mock or live)."""

from __future__ import annotations

from typing import Any

from amazon_create.config import Settings
from amazon_create.mcp.live_research_models import derive_research_query
from amazon_create.mcp.live_research_types import ResearchBundle
from amazon_create.mcp.research_context import build_research_context


def build_query(*, product_name: str, marketplace: str, specs: str = "") -> str:
    """Build a marketplace research query string."""
    parts = [product_name.strip(), marketplace.strip()]
    if specs.strip():
        parts.append(specs.strip()[:200])
    return derive_research_query(" ".join(p for p in parts if p))


def load_research_context(
    settings: Settings,
    *,
    product_name: str,
    marketplace: str,
    specs: str = "",
) -> dict[str, Any]:
    """Return a JSON-safe research brief; never raises on provider failure."""
    query = build_query(product_name=product_name, marketplace=marketplace, specs=specs)
    if settings.mock or not _has_remote_keys(settings):
        return _fixture_context(query)
    try:
        from amazon_create.mcp.live_research import (  # noqa: PLC0415
            fetch_live_mcp_research_sync,
            research_bundle_from_snapshots,
        )

        snapshots = fetch_live_mcp_research_sync(settings, query=query)
        bundle = research_bundle_from_snapshots(snapshots)
        return build_research_context(bundle, snapshots=snapshots)
    except Exception as exc:  # noqa: BLE001 — research is best-effort
        return {
            "mode": "degraded",
            "query": query,
            "allowed_keywords": [],
            "gaps": [f"live_research_failed:{type(exc).__name__}"],
            "items": [],
            "guidance": "MCP live research failed; continue with brief-only evidence.",
        }


def _has_remote_keys(settings: Settings) -> bool:
    return bool(
        settings.sellersprite_mcp_key.get_secret_value()
        or settings.sorftime_mcp_key.get_secret_value()
        or settings.sif_mcp_key.get_secret_value()
    )


def _fixture_context(query: str) -> dict[str, Any]:
    """Deterministic offline keyword context from fixture files when useful."""
    try:
        import asyncio

        from amazon_create.mcp.fixture_server import build_fixture_provider  # noqa: PLC0415
        from amazon_create.mcp.protocol import ResearchQuery  # noqa: PLC0415

        provider = build_fixture_provider("fresh")
        roles = ("keyword", "shopper", "competitor")

        async def _pull() -> list[str]:
            keywords: list[str] = []
            async with provider.open_session() as session:
                for role in roles:
                    try:
                        result = await session.call(
                            ResearchQuery(role=role, query=query, marketplace="US")
                        )
                    except Exception:  # noqa: BLE001
                        continue
                    for claim in result.claims:
                        if claim.key in {"keyword", "phrase", "term"} or "keyword" in claim.key:
                            keywords.append(str(claim.value))
                        elif claim.value and len(keywords) < 24:
                            keywords.append(str(claim.value)[:80])
            return keywords[:24]

        keywords = asyncio.run(_pull())
    except Exception:  # noqa: BLE001
        keywords = []

    empty = ResearchBundle()
    ctx = build_research_context(empty)
    ctx["mode"] = "fixture"
    ctx["query"] = query
    ctx["allowed_keywords"] = keywords
    ctx["guidance"] = (
        "Fixture/mock research only. Keywords are market context, not product facts."
    )
    return ctx
