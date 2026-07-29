"""Allowlisted listing-optimization rule profile catalog."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Marketplace(StrEnum):
    """Supported Amazon marketplace family for specialized profiles."""

    US = "US"
    UK = "UK"
    DE = "DE"


@dataclass(frozen=True, slots=True)
class RuleProfile:
    """One exact allowlisted resource and its deterministic routing keys."""

    filename: str
    marketplaces: tuple[Marketplace, ...]
    product_types: tuple[str, ...]
    kind: Literal["product", "process"]


_ALL_MARKETPLACES = (Marketplace.US, Marketplace.UK, Marketplace.DE)


def _product(
    filename: str,
    marketplaces: tuple[Marketplace, ...],
    product_type: str,
) -> RuleProfile:
    return RuleProfile(filename, marketplaces, (product_type,), "product")


def _process(
    filename: str,
    marketplaces: tuple[Marketplace, ...] = _ALL_MARKETPLACES,
) -> RuleProfile:
    return RuleProfile(filename, marketplaces, (), "process")


RULE_PROFILES: tuple[RuleProfile, ...] = (
    _product("us-adjustable-wedding-sign-stands.md", (Marketplace.US,), "SIGN_DISPLAY_STAND"),
    _product("us-childrens-swim-aid-listing-audit.md", (Marketplace.US,), "SWIM_VEST"),
    _product(
        "us-decorative-wired-ribbon-short-fields.md",
        (Marketplace.US,),
        "DECORATIVE_WIRED_RIBBON",
    ),
    _product("us-metal-magazine-file-holder-copy.md", (Marketplace.US,), "MAGAZINE_FILE_HOLDER"),
    _product("us-multifunction-desk-organizer-copy.md", (Marketplace.US,), "DESK_ORGANIZER"),
    _product("us-natural-scallop-shell-copy.md", (Marketplace.US,), "NATURAL_SCALLOP_SHELL"),
    _product("us-outdoor-bird-bath-short-fields.md", (Marketplace.US,), "OUTDOOR_BIRD_BATH"),
    _product("us-small-mesh-zipper-pouches.md", (Marketplace.US,), "MESH_ZIPPER_POUCH"),
    _product("us-tiered-letter-tray-organizers.md", (Marketplace.US,), "LETTER_TRAY_ORGANIZER"),
    _product("us-wall-file-organizer-short-fields.md", (Marketplace.US,), "WALL_FILE_ORGANIZER"),
    _product(
        "us-wall-file-organizer-public-diagnostic.md",
        (Marketplace.US,),
        "WALL_FILE_ORGANIZER",
    ),
    _product("wood-wall-panel-keyword-gap-seo.md", (Marketplace.US,), "WOOD_WALL_PANEL"),
    _product(
        "acoustic-wood-slat-wall-panels-diagnostic-pattern.md",
        (Marketplace.US,),
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL",
    ),
    _product(
        "us-wood-slat-wall-panel-traffic-benchmark.md",
        (Marketplace.US,),
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL",
    ),
    _product(
        "us-acoustic-wood-panel-public-comparison.md",
        (Marketplace.US,),
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL",
    ),
    _product(
        "us-large-acoustic-polyester-panel-public-benchmark.md",
        (Marketplace.US,),
        "ACOUSTIC_POLYESTER_PANEL",
    ),
    _product("public-amazon-hardware-cloth-benchmark.md", (Marketplace.US,), "HARDWARE_CLOTH"),
    _product(
        "us-short-field-office-organizer-examples.md",
        (Marketplace.US,),
        "OFFICE_ORGANIZER",
    ),
    _product("uk-bakery-packaging-copy.md", (Marketplace.UK,), "BAKERY_PACKAGING"),
    _product("uk-cellophane-hamper-copy.md", (Marketplace.UK,), "CELLOPHANE_HAMPER"),
    _product(
        "uk-a5-hardback-lined-notebook-cold-start.md",
        (Marketplace.UK,),
        "A5_HARDBACK_LINED_NOTEBOOK",
    ),
    _product(
        "uk-acrylic-rotating-pen-holder-cold-start.md",
        (Marketplace.UK,),
        "ROTATING_PEN_HOLDER",
    ),
    _product(
        "uk-craft-kit-seasonality-and-mobile-amazon-fallback.md",
        (Marketplace.UK,),
        "CRAFT_KIT",
    ),
    _product("uk-dust-mop-refill-pads-cold-start.md", (Marketplace.UK,), "DUST_MOP_REFILL_PAD"),
    _product("uk-plastic-wallets-document-wallets.md", (Marketplace.UK,), "DOCUMENT_WALLET"),
    _product(
        "de-acrylic-rotating-pen-holder-cold-start.md",
        (Marketplace.DE,),
        "ROTATING_PEN_HOLDER",
    ),
    _product("de-writing-pad-title-optimization.md", (Marketplace.DE,), "WRITING_PAD"),
    _product(
        "de-cellophane-gift-packaging-diagnostic-pattern.md",
        (Marketplace.DE,),
        "CELLOPHANE_GIFT_PACKAGING",
    ),
    _product(
        "small-self-adhesive-cellophane-bags-de-uk.md",
        (Marketplace.DE, Marketplace.UK),
        "SELF_ADHESIVE_CELLOPHANE_BAG",
    ),
    _process("parent-child-variation-copy.md"),
    _process("structured-fact-authorization-and-cascade-dedupe.md"),
    _process("us-short-title-highlight-search-terms.md", (Marketplace.US,)),
    _process("short-title-highlight-search-term-allocation.md"),
    _process("us-short-title-item-highlights-backend-terms.md", (Marketplace.US,)),
    _process("cosmo-rufus-copy-rules.md"),
    _process("copy-and-image-sop-scoring-rubric.md"),
    _process("xiyou-multi-asin-keyword-and-review-workflow.md"),
    _process("amazon-rolling-plan-workbook-from-screenshot.md"),
    _process("amazon-public-pdp-and-autocomplete-fallback.md"),
    _process("us-localized-public-amazon-price-and-offer-checks.md", (Marketplace.US,)),
    _process("us-mature-competitor-price-promo-ad-audit.md", (Marketplace.US,)),
)
ALLOWLISTED_PROFILE_FILENAMES: frozenset[str] = frozenset(
    profile.filename for profile in RULE_PROFILES
)

__all__ = [
    "ALLOWLISTED_PROFILE_FILENAMES",
    "RULE_PROFILES",
    "Marketplace",
    "RuleProfile",
]
