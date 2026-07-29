"""Public listing-optimizer entry points."""

from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticResearchCache,
    AwaitingApproval,
    ClarificationAnswer,
    FunnelHypothesis,
    ProductIdentity,
)
from amazon_copy.automatic_pipeline import issue_approval_token, run_automatic_optimization
from amazon_copy.optimizer_runtime import SimpleOptimizerError, production_settings
from amazon_copy.optimizer_service import optimize_listing
from amazon_copy.review.search_terms import build_backend_search_terms
from amazon_copy.schemas.simple_listing import (
    CopyPointsParseError,
    format_optimized_listing,
    parse_copy_points,
    parse_listing_block,
    split_verified_facts_from_listing,
)

if TYPE_CHECKING:
    from amazon_copy.config import Settings

_production_settings = production_settings


def optimize_listing_text(
    source_text: str,
    settings: Settings | None = None,
    *,
    verified_facts: str | None = None,
) -> str:
    """Return seller-ready listing text using a real model by default."""
    runtime = production_settings(settings)
    listing_text = source_text
    facts = verified_facts
    if facts is None:
        listing_text, _ = split_verified_facts_from_listing(source_text)
    source = parse_listing_block(listing_text)
    result = optimize_listing(source, settings=runtime, verified_facts=facts)
    return format_optimized_listing(result, source.format_template)


__all__ = [
    "AutomaticOptimizationContext",
    "AutomaticOptimizationDependencies",
    "AutomaticResearchCache",
    "AwaitingApproval",
    "ClarificationAnswer",
    "CopyPointsParseError",
    "FunnelHypothesis",
    "ProductIdentity",
    "SimpleOptimizerError",
    "build_backend_search_terms",
    "format_optimized_listing",
    "issue_approval_token",
    "optimize_listing",
    "optimize_listing_text",
    "parse_copy_points",
    "parse_listing_block",
    "run_automatic_optimization",
    "split_verified_facts_from_listing",
]
