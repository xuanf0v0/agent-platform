"""Compatibility shim — listing format lives in ``amazon_copy.schemas.simple_listing``."""

from __future__ import annotations

from amazon_copy.schemas.simple_listing import (
    BulletMarker,
    HighlightsLabelPosition,
    ListingFormatTemplate,
    TitleLabelPosition,
)

__all__ = [
    "BulletMarker",
    "HighlightsLabelPosition",
    "ListingFormatTemplate",
    "TitleLabelPosition",
]
