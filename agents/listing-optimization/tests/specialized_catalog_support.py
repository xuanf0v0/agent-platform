from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, final

from amazon_copy.specialized_rules.catalog import Marketplace
from amazon_copy.specialized_rules.models import (
    SpecializedRuleCache,
    SpecializedRuleLoad,
    SpecializedRuleSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from amazon_copy.config import Settings
    from amazon_copy.specialized_rules.resource_loader import SpecializedRuleRequest


COMBINED_RULE_SOURCE: Final = (
    Path(__file__).with_name("fixtures") / "specialized_catalog_profiles.md"
)


@final
class SpecializedCatalogResourceError(FileNotFoundError):
    resource_path: Path

    def __init__(self, resource_path: Path) -> None:
        self.resource_path = resource_path
        super().__init__(f"required specialized catalog fixture is unavailable: {resource_path}")


@dataclass(frozen=True, slots=True)
class ProductRouteCase:
    filename: str
    marketplace: Marketplace
    product_type: str


@dataclass(frozen=True, slots=True)
class ProcessRouteCase:
    filename: str
    marketplaces: tuple[Marketplace, ...]


PRODUCT_ROUTE_CASES: Final[tuple[ProductRouteCase, ...]] = (
    ProductRouteCase("us-adjustable-wedding-sign-stands.md", Marketplace.US, "SIGN_DISPLAY_STAND"),
    ProductRouteCase("us-childrens-swim-aid-listing-audit.md", Marketplace.US, "SWIM_VEST"),
    ProductRouteCase(
        "us-decorative-wired-ribbon-short-fields.md",
        Marketplace.US,
        "DECORATIVE_WIRED_RIBBON",
    ),
    ProductRouteCase(
        "us-metal-magazine-file-holder-copy.md", Marketplace.US, "MAGAZINE_FILE_HOLDER"
    ),
    ProductRouteCase("us-multifunction-desk-organizer-copy.md", Marketplace.US, "DESK_ORGANIZER"),
    ProductRouteCase("us-natural-scallop-shell-copy.md", Marketplace.US, "NATURAL_SCALLOP_SHELL"),
    ProductRouteCase("us-outdoor-bird-bath-short-fields.md", Marketplace.US, "OUTDOOR_BIRD_BATH"),
    ProductRouteCase("us-small-mesh-zipper-pouches.md", Marketplace.US, "MESH_ZIPPER_POUCH"),
    ProductRouteCase(
        "us-tiered-letter-tray-organizers.md", Marketplace.US, "LETTER_TRAY_ORGANIZER"
    ),
    ProductRouteCase(
        "us-wall-file-organizer-short-fields.md", Marketplace.US, "WALL_FILE_ORGANIZER"
    ),
    ProductRouteCase(
        "us-wall-file-organizer-public-diagnostic.md", Marketplace.US, "WALL_FILE_ORGANIZER"
    ),
    ProductRouteCase("wood-wall-panel-keyword-gap-seo.md", Marketplace.US, "WOOD_WALL_PANEL"),
    ProductRouteCase(
        "acoustic-wood-slat-wall-panels-diagnostic-pattern.md",
        Marketplace.US,
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL",
    ),
    ProductRouteCase(
        "us-wood-slat-wall-panel-traffic-benchmark.md",
        Marketplace.US,
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL",
    ),
    ProductRouteCase(
        "us-acoustic-wood-panel-public-comparison.md",
        Marketplace.US,
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL",
    ),
    ProductRouteCase(
        "us-large-acoustic-polyester-panel-public-benchmark.md",
        Marketplace.US,
        "ACOUSTIC_POLYESTER_PANEL",
    ),
    ProductRouteCase("public-amazon-hardware-cloth-benchmark.md", Marketplace.US, "HARDWARE_CLOTH"),
    ProductRouteCase(
        "us-short-field-office-organizer-examples.md", Marketplace.US, "OFFICE_ORGANIZER"
    ),
    ProductRouteCase("uk-bakery-packaging-copy.md", Marketplace.UK, "BAKERY_PACKAGING"),
    ProductRouteCase("uk-cellophane-hamper-copy.md", Marketplace.UK, "CELLOPHANE_HAMPER"),
    ProductRouteCase(
        "uk-a5-hardback-lined-notebook-cold-start.md",
        Marketplace.UK,
        "A5_HARDBACK_LINED_NOTEBOOK",
    ),
    ProductRouteCase(
        "uk-acrylic-rotating-pen-holder-cold-start.md",
        Marketplace.UK,
        "ROTATING_PEN_HOLDER",
    ),
    ProductRouteCase(
        "uk-craft-kit-seasonality-and-mobile-amazon-fallback.md", Marketplace.UK, "CRAFT_KIT"
    ),
    ProductRouteCase(
        "uk-dust-mop-refill-pads-cold-start.md", Marketplace.UK, "DUST_MOP_REFILL_PAD"
    ),
    ProductRouteCase("uk-plastic-wallets-document-wallets.md", Marketplace.UK, "DOCUMENT_WALLET"),
    ProductRouteCase(
        "de-acrylic-rotating-pen-holder-cold-start.md",
        Marketplace.DE,
        "ROTATING_PEN_HOLDER",
    ),
    ProductRouteCase("de-writing-pad-title-optimization.md", Marketplace.DE, "WRITING_PAD"),
    ProductRouteCase(
        "de-cellophane-gift-packaging-diagnostic-pattern.md",
        Marketplace.DE,
        "CELLOPHANE_GIFT_PACKAGING",
    ),
    ProductRouteCase(
        "small-self-adhesive-cellophane-bags-de-uk.md",
        Marketplace.DE,
        "SELF_ADHESIVE_CELLOPHANE_BAG",
    ),
    ProductRouteCase(
        "small-self-adhesive-cellophane-bags-de-uk.md",
        Marketplace.UK,
        "SELF_ADHESIVE_CELLOPHANE_BAG",
    ),
)

PROCESS_ROUTE_CASES: Final[tuple[ProcessRouteCase, ...]] = (
    ProcessRouteCase("parent-child-variation-copy.md", tuple(Marketplace)),
    ProcessRouteCase(
        "structured-fact-authorization-and-cascade-dedupe.md",
        tuple(Marketplace),
    ),
    ProcessRouteCase("us-short-title-highlight-search-terms.md", (Marketplace.US,)),
    ProcessRouteCase("short-title-highlight-search-term-allocation.md", tuple(Marketplace)),
    ProcessRouteCase("us-short-title-item-highlights-backend-terms.md", (Marketplace.US,)),
    ProcessRouteCase("cosmo-rufus-copy-rules.md", tuple(Marketplace)),
    ProcessRouteCase("copy-and-image-sop-scoring-rubric.md", tuple(Marketplace)),
    ProcessRouteCase("xiyou-multi-asin-keyword-and-review-workflow.md", tuple(Marketplace)),
    ProcessRouteCase("amazon-rolling-plan-workbook-from-screenshot.md", tuple(Marketplace)),
    ProcessRouteCase("amazon-public-pdp-and-autocomplete-fallback.md", tuple(Marketplace)),
    ProcessRouteCase("us-localized-public-amazon-price-and-offer-checks.md", (Marketplace.US,)),
    ProcessRouteCase("us-mature-competitor-price-promo-ad-audit.md", (Marketplace.US,)),
)


@lru_cache(maxsize=1)
def combined_rule_profiles() -> Mapping[str, str]:
    if not COMBINED_RULE_SOURCE.is_file():
        raise SpecializedCatalogResourceError(COMBINED_RULE_SOURCE)
    text = COMBINED_RULE_SOURCE.read_text(encoding="utf-8")
    marker_re = re.compile(r"^\*\*[^`\n]+`(?P<path>[^`]+)`\s*$", re.MULTILINE)
    profiles: dict[str, str] = {}
    markers = tuple(marker_re.finditer(text))
    for marker in markers:
        filename = Path(marker.group("path")).name
        remainder = text[marker.end() :]
        next_section = re.search(r"^## \u4e13\u9879", remainder, re.MULTILINE)
        end = marker.end() + next_section.start() if next_section else len(text)
        profiles[filename] = text[marker.end() : end].strip()
    return MappingProxyType(profiles)


@final
class CombinedCatalogRuleFetcher:
    def __init__(self) -> None:
        self.calls: int = 0
        self.requested_profiles: list[tuple[str, ...]] = []

    def __call__(
        self,
        settings: Settings,
        *,
        request: SpecializedRuleRequest,
        cached: SpecializedRuleCache | None = None,
    ) -> SpecializedRuleLoad:
        del settings
        requested = tuple(profile.filename for profile in request.route.profiles)
        self.requested_profiles.append(requested)
        if (
            cached is not None
            and cached.source_fingerprint == request.source_fingerprint
            and cached.route_fingerprint == request.route.fingerprint
            and cached.requested_profiles == requested
        ):
            return SpecializedRuleLoad(cache=cached, reused=True)
        self.calls += 1
        content = combined_rule_profiles()
        snapshots = tuple(self._snapshot(filename, content[filename]) for filename in requested)
        return SpecializedRuleLoad(
            cache=SpecializedRuleCache(
                source_fingerprint=request.source_fingerprint,
                route_fingerprint=request.route.fingerprint,
                requested_profiles=requested,
                snapshots=snapshots,
                all_requested_loaded=True,
            ),
            reused=False,
        )

    @staticmethod
    def _snapshot(filename: str, markdown: str) -> SpecializedRuleSnapshot:
        return SpecializedRuleSnapshot(
            profile_filename=filename,
            content_markdown=markdown,
            content_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        )


ALL_SOURCE_FILENAMES: Final[frozenset[str]] = frozenset(
    case.filename for case in (*PRODUCT_ROUTE_CASES, *PROCESS_ROUTE_CASES)
)


__all__ = [
    "ALL_SOURCE_FILENAMES",
    "COMBINED_RULE_SOURCE",
    "PROCESS_ROUTE_CASES",
    "PRODUCT_ROUTE_CASES",
    "CombinedCatalogRuleFetcher",
    "ProcessRouteCase",
    "ProductRouteCase",
    "SpecializedCatalogResourceError",
    "combined_rule_profiles",
]
