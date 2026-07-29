"""Canonical listing values and source provenance."""

from __future__ import annotations

import hashlib
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from amazon_copy.schemas.simple_listing import parse_listing_block

if TYPE_CHECKING:
    from datetime import datetime

Asin = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{10}$")]
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


@unique
class CanonicalMarketplace(StrEnum):
    """Marketplace supported by the canonical workflow."""

    US = "US"
    UK = "UK"


class CanonicalListingCopy(BaseModel):
    """Immutable title and copy points from exactly one source."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    title: NonBlankText
    item_highlights: str = ""
    bullets: tuple[NonBlankText, ...] = Field(min_length=1, max_length=10)


class SellerDraftProvenance(BaseModel):
    """Identity and digest for copy pasted by a seller."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    authority: Literal["seller_draft"] = "seller_draft"
    source_id: NonBlankText
    received_at: AwareDatetime
    content_sha256: Sha256Hex


class SellerDraft(BaseModel):
    """Seller-authored copy that never replaces retrieved copy implicitly."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    listing: CanonicalListingCopy
    provenance: SellerDraftProvenance


class RetrievedListingProvenance(BaseModel):
    """Source identity for an ASIN listing retrieved from Amazon."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    authority: Literal["retrieved_listing"] = "retrieved_listing"
    source_id: NonBlankText
    retrieved_at: AwareDatetime


class RetrievedListingBaseline(BaseModel):
    """Authoritative current-copy baseline for one marketplace ASIN."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    marketplace: CanonicalMarketplace
    asin: Asin
    listing: CanonicalListingCopy
    provenance: RetrievedListingProvenance


class ListingConflict(BaseModel):
    """One field where retrieved baseline and seller draft disagree."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    conflict_id: Sha256Hex
    kind: Literal["title", "item_highlights", "point_count", "point_content"]
    field: NonBlankText
    baseline_value: str
    draft_value: str


def parse_seller_draft(raw: str, source_id: str, received_at: datetime) -> SellerDraft:
    """Parse pasted listing text while retaining exact seller-source provenance."""
    parsed = parse_listing_block(raw)
    return SellerDraft(
        listing=CanonicalListingCopy(
            title=parsed.title,
            item_highlights=parsed.item_highlights,
            bullets=tuple(parsed.bullets),
        ),
        provenance=SellerDraftProvenance(
            source_id=source_id,
            received_at=received_at,
            content_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        ),
    )


__all__ = [
    "Asin",
    "CanonicalListingCopy",
    "CanonicalMarketplace",
    "ListingConflict",
    "NonBlankText",
    "RetrievedListingBaseline",
    "RetrievedListingProvenance",
    "SellerDraft",
    "SellerDraftProvenance",
    "Sha256Hex",
    "parse_seller_draft",
]
