"""Compatibility shim — keyword parser lives in ``amazon_copy.mcp.live_research_data``."""

from __future__ import annotations

from amazon_copy.mcp.live_research_data import parse_marketplace_keyword

__all__ = ["parse_marketplace_keyword"]