"""Deterministic marketplace and product-profile routing."""

import hashlib
from dataclasses import dataclass
from typing import Literal, TypeAlias, assert_never

from amazon_copy.specialized_rules import _exhaustiveness
from amazon_copy.specialized_rules.catalog import RULE_PROFILES, Marketplace, RuleProfile

_MARKETPLACE_CODES = {
    "US": Marketplace.US,
    "UK": Marketplace.UK,
    "GB": Marketplace.UK,
    "DE": Marketplace.DE,
}
_GERMAN_MARKERS = (
    "produktbeschreibung",
    "größe",
    "farbe",
    "lieferung",
    "stifthalter",
    "schreibtisch",
    "büro",
    "fächer",
    "zubehör",
)
_GERMAN_MARKER_THRESHOLD = 2


@dataclass(frozen=True, slots=True)
class ResolvedMarketplace:
    """One explicitly selected or language-resolved marketplace."""

    marketplace: Marketplace
    basis: Literal["explicit", "language"]


@dataclass(frozen=True, slots=True)
class MarketplaceClarificationNeeded:
    """Exact candidates requiring a seller marketplace selection."""

    candidates: tuple[Marketplace, ...]


MarketplaceResolution: TypeAlias = ResolvedMarketplace | MarketplaceClarificationNeeded


@dataclass(frozen=True, slots=True)
class ProductTypeClarificationNeeded:
    """Marketplace-resolved outcome requiring an exact seller Product Type."""

    marketplace: Marketplace


@dataclass(frozen=True, slots=True)
class RuleRoute:
    """Exact profile selection for one marketplace and product type."""

    marketplace: Marketplace
    product_type: str
    profiles: tuple[RuleProfile, ...]
    fingerprint: str


SpecializedRuleRoutingResult: TypeAlias = (
    RuleRoute | MarketplaceClarificationNeeded | ProductTypeClarificationNeeded
)


def resolve_marketplace(
    source_text: str,
    explicit_marketplace: str | None = None,
) -> MarketplaceResolution:
    """Resolve a marketplace or preserve English US/UK ambiguity."""
    explicit = (explicit_marketplace or "").strip().upper()
    selected = _MARKETPLACE_CODES.get(explicit)
    if selected is not None:
        return ResolvedMarketplace(marketplace=selected, basis="explicit")
    if explicit:
        return MarketplaceClarificationNeeded(candidates=tuple(Marketplace))
    folded = source_text.casefold()
    marker_count = sum(marker in folded for marker in _GERMAN_MARKERS)
    if marker_count >= _GERMAN_MARKER_THRESHOLD or any(character in folded for character in "äöüß"):
        return ResolvedMarketplace(marketplace=Marketplace.DE, basis="language")
    return MarketplaceClarificationNeeded(candidates=(Marketplace.US, Marketplace.UK))


def route_rule_profiles(marketplace: Marketplace, product_type: str) -> RuleRoute:
    """Select process gates and exact product profiles without fuzzy fallback."""
    normalized_product_type = product_type.strip().upper()
    profiles = tuple(
        profile
        for profile in RULE_PROFILES
        if marketplace in profile.marketplaces
        and (profile.kind == "process" or normalized_product_type in profile.product_types)
    )
    framed = "\0".join(
        (marketplace.value, normalized_product_type, *(profile.filename for profile in profiles))
    )
    return RuleRoute(
        marketplace=marketplace,
        product_type=normalized_product_type,
        profiles=profiles,
        fingerprint=hashlib.sha256(framed.encode("utf-8")).hexdigest(),
    )


def resolve_rule_route(
    source_text: str,
    explicit_marketplace: str | None,
    product_type: str | None,
) -> SpecializedRuleRoutingResult:
    """Resolve clarification variants before constructing an exact profile route."""
    variant = _exhaustiveness.widen_variant(resolve_marketplace(source_text, explicit_marketplace))
    match variant:
        case MarketplaceClarificationNeeded() as clarification:
            return clarification
        case ResolvedMarketplace() as resolution:
            normalized_product_type = (product_type or "").strip()
            if not normalized_product_type:
                return ProductTypeClarificationNeeded(marketplace=resolution.marketplace)
            return route_rule_profiles(resolution.marketplace, normalized_product_type)
        case _ as unexpected:
            assert_never(_exhaustiveness.reject_variant(unexpected))


__all__ = [
    "MarketplaceClarificationNeeded",
    "MarketplaceResolution",
    "ProductTypeClarificationNeeded",
    "ResolvedMarketplace",
    "RuleRoute",
    "SpecializedRuleRoutingResult",
    "resolve_marketplace",
    "resolve_rule_route",
    "route_rule_profiles",
]
