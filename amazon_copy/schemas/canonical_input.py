"""Canonical provenance-preserving request boundary for Amazon copy workflows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal, TypeAlias, assert_never

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from amazon_copy.schemas.canonical_models import (
    Asin,
    CanonicalListingCopy,
    CanonicalMarketplace,
    ListingConflict,
    NonBlankText,
    RetrievedListingBaseline,
    RetrievedListingProvenance,
    SellerDraft,
    SellerDraftProvenance,
    Sha256Hex,
    parse_seller_draft,
)


class AsinRequest(BaseModel):
    """Minimum viable request that requires PDP retrieval before analysis."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    request_type: Literal["asin"] = "asin"
    marketplace: CanonicalMarketplace
    asin: Asin


class PastedListingRequest(BaseModel):
    """Listing-only request whose marketplace may require clarification."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    request_type: Literal["pasted_listing"] = "pasted_listing"
    marketplace: CanonicalMarketplace | None = None
    seller_draft: SellerDraft


class AsinWithSellerDraft(BaseModel):
    """ASIN request with a separately sourced unpublished seller draft."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    request_type: Literal["asin_with_seller_draft"] = "asin_with_seller_draft"
    marketplace: CanonicalMarketplace
    asin: Asin
    seller_draft: SellerDraft


CanonicalInput: TypeAlias = Annotated[
    AsinRequest | PastedListingRequest | AsinWithSellerDraft,
    Field(discriminator="request_type"),
]


class InputQuestion(BaseModel):
    """Stable machine-readable clarification emitted by canonical intake."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    code: Literal["marketplace_required", "seller_draft_conflict"]
    field: Literal["marketplace", "seller_draft"]
    prompt: NonBlankText
    conflict_ids: tuple[Sha256Hex, ...] = ()


class InputAccepted(BaseModel):
    """Request accepted without merging independently sourced copy."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["accepted"] = "accepted"
    request: CanonicalInput
    baseline: RetrievedListingBaseline | None = None


class InputClarification(BaseModel):
    """Request paused on explicit marketplace or source conflicts."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["awaiting_facts"] = "awaiting_facts"
    request: CanonicalInput
    questions: tuple[InputQuestion, ...] = Field(min_length=1)
    conflicts: tuple[ListingConflict, ...] = ()


CanonicalInputResolution: TypeAlias = Annotated[
    InputAccepted | InputClarification,
    Field(discriminator="status"),
]


@dataclass(frozen=True, slots=True)
class CanonicalInputBoundaryError(ValueError):
    """Typed rejection for a baseline paired with the wrong request."""

    code: Literal["baseline_identity_mismatch", "baseline_not_applicable"]

    @override
    def __str__(self) -> str:
        """Return the stable boundary failure code."""
        return self.code


def _conflict(
    kind: Literal["title", "item_highlights", "point_count", "point_content"],
    field: str,
    values: tuple[str, str],
) -> ListingConflict:
    baseline_value, draft_value = values
    digest_input = f"{kind}\x1f{field}\x1f{baseline_value}\x1f{draft_value}"
    return ListingConflict(
        conflict_id=hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
        kind=kind,
        field=field,
        baseline_value=baseline_value,
        draft_value=draft_value,
    )


def _listing_conflicts(
    baseline: CanonicalListingCopy,
    draft: CanonicalListingCopy,
) -> tuple[ListingConflict, ...]:
    conflicts: list[ListingConflict] = []
    if baseline.title != draft.title:
        conflicts.append(_conflict("title", "title", (baseline.title, draft.title)))
    if baseline.item_highlights != draft.item_highlights:
        conflicts.append(
            _conflict(
                "item_highlights",
                "item_highlights",
                (baseline.item_highlights, draft.item_highlights),
            )
        )
    if len(baseline.bullets) != len(draft.bullets):
        conflicts.append(
            _conflict(
                "point_count",
                "bullets",
                (str(len(baseline.bullets)), str(len(draft.bullets))),
            )
        )
    else:
        conflicts.extend(
            _conflict(
                "point_content",
                f"bullets[{index}]",
                (baseline_point, draft_point),
            )
            for index, (baseline_point, draft_point) in enumerate(
                zip(baseline.bullets, draft.bullets, strict=True)
            )
            if baseline_point != draft_point
        )
    return tuple(conflicts)


def _require_baseline_identity(
    request: AsinRequest | AsinWithSellerDraft,
    baseline: RetrievedListingBaseline,
) -> None:
    if request.marketplace != baseline.marketplace or request.asin != baseline.asin:
        raise CanonicalInputBoundaryError(code="baseline_identity_mismatch")


def resolve_canonical_input(
    request: AsinRequest | PastedListingRequest | AsinWithSellerDraft,
    baseline: RetrievedListingBaseline | None = None,
) -> CanonicalInputResolution:
    """Resolve canonical input without inferring marketplace or merging copy sources."""
    match request:  # noqa: RUF100  # noqa: MATCH_OK - post-match assertion for BasedPyright
        case PastedListingRequest(marketplace=None):
            if baseline is not None:
                raise CanonicalInputBoundaryError(code="baseline_not_applicable")
            return InputClarification(
                request=request,
                questions=(
                    InputQuestion(
                        code="marketplace_required",
                        field="marketplace",
                        prompt="Which marketplace should this listing target: US or UK?",
                    ),
                ),
            )
        case PastedListingRequest():
            if baseline is not None:
                raise CanonicalInputBoundaryError(code="baseline_not_applicable")
            return InputAccepted(request=request)
        case AsinRequest():
            if baseline is not None:
                _require_baseline_identity(request, baseline)
            return InputAccepted(request=request, baseline=baseline)
        case AsinWithSellerDraft(seller_draft=seller_draft):
            if baseline is None:
                return InputAccepted(request=request)
            _require_baseline_identity(request, baseline)
            conflicts = _listing_conflicts(baseline.listing, seller_draft.listing)
            if not conflicts:
                return InputAccepted(request=request, baseline=baseline)
            return InputClarification(
                request=request,
                conflicts=conflicts,
                questions=(
                    InputQuestion(
                        code="seller_draft_conflict",
                        field="seller_draft",
                        prompt=(
                            "Retrieved listing and seller draft differ. Confirm which source "
                            "governs each listed conflict."
                        ),
                        conflict_ids=tuple(item.conflict_id for item in conflicts),
                    ),
                ),
            )
    assert_never(request)


__all__ = [
    "AsinRequest",
    "AsinWithSellerDraft",
    "CanonicalInput",
    "CanonicalInputBoundaryError",
    "CanonicalInputResolution",
    "CanonicalListingCopy",
    "CanonicalMarketplace",
    "InputAccepted",
    "InputClarification",
    "InputQuestion",
    "ListingConflict",
    "PastedListingRequest",
    "RetrievedListingBaseline",
    "RetrievedListingProvenance",
    "SellerDraft",
    "SellerDraftProvenance",
    "parse_seller_draft",
    "resolve_canonical_input",
]
