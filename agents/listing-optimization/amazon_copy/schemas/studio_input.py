"""Typed boundary for one-box Amazon US studio briefs."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Annotated, ClassVar, Final, Literal, Never, NewType, assert_never

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import override  # noqa: UP035

from amazon_copy.input_security import InputSecurityError, require_studio_input
from amazon_copy.schemas.listing_format import ListingFormatTemplate  # noqa: TC001
from amazon_copy.schemas.simple_listing import CopyPointsParseError, parse_listing_block

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Asin = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{10}$")]
SellerClaimId = NewType("SellerClaimId", str)
EvidenceGapId = NewType("EvidenceGapId", str)
RequestHash = NewType("RequestHash", str)


@unique
class SellerFactField(StrEnum):
    """A factual segment explicitly submitted by the seller."""

    ASIN = "asin"
    BRAND = "brand"
    CATEGORY = "category"
    TITLE = "title"
    BULLET = "bullet"


@unique
class MissingField(StrEnum):
    """An optional product identifier absent from the submitted brief."""

    ASIN = "asin"
    BRAND = "brand"
    CATEGORY = "category"


@unique
class StudioInputField(StrEnum):
    """The one-box field associated with a parser failure."""

    BRIEF = "brief"
    ASIN = "asin"
    BRAND = "brand"
    CATEGORY = "category"
    MARKETPLACE = "marketplace"


@unique
class StudioInputErrorCode(StrEnum):
    """Stable parser failure codes safe to expose at a boundary."""

    DUPLICATE_HEADER = "duplicate_header"
    EMPTY_HEADER = "empty_header"
    INVALID_ASIN = "invalid_asin"
    INVALID_LISTING = "invalid_listing"
    UNSUPPORTED_MARKETPLACE = "unsupported_marketplace"


class SellerAssertion(BaseModel):
    """One seller-supplied fact without external-verification semantics."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    claim_id: SellerClaimId
    field: SellerFactField
    segment_index: int = Field(ge=0)
    value: NonBlankText
    authority: Literal["user_asserted"] = "user_asserted"


class EvidenceGap(BaseModel):
    """One optional fact omitted from the seller's submitted brief."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    gap_id: EvidenceGapId
    field: MissingField
    reason: Literal["not_submitted"] = "not_submitted"


class StudioRequest(BaseModel):
    """Canonical immutable request parsed from the existing one-box surface."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    marketplace: Literal["US"] = "US"
    asin: Asin | None = None
    brand: NonBlankText | None = None
    category: NonBlankText | None = None
    title: NonBlankText
    bullets: tuple[NonBlankText, ...] = Field(min_length=1, max_length=10)
    format_template: ListingFormatTemplate
    seller_assertions: tuple[SellerAssertion, ...]
    evidence_gaps: tuple[EvidenceGap, ...]
    request_hash: RequestHash


@dataclass(frozen=True, slots=True)
class StudioInputParseError(ValueError):
    """Typed safe failure raised while parsing one submitted brief."""

    field: StudioInputField
    code: StudioInputErrorCode

    @override
    def __str__(self) -> str:
        """Return the safe field and stable failure code."""
        return f"{self.field.value}: {self.code.value}"


_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<name>asin|brand|category|marketplace)\s*:\s*(?P<value>.*?)\s*$",
    re.IGNORECASE,
)
_ASIN_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{10}$")
_HEADER_FIELDS: Final[dict[str, StudioInputField]] = {
    "asin": StudioInputField.ASIN,
    "brand": StudioInputField.BRAND,
    "category": StudioInputField.CATEGORY,
    "marketplace": StudioInputField.MARKETPLACE,
}
_MISSING_FIELDS: Final[tuple[MissingField, ...]] = (
    MissingField.ASIN,
    MissingField.BRAND,
    MissingField.CATEGORY,
)


def _stable_digest(namespace: str, parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for part in (namespace, *parts):
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(length=8, byteorder="big"))
        digest.update(encoded)
    return digest.hexdigest()


def _seller_assertion(
    field: SellerFactField,
    segment_index: int,
    value: str,
) -> SellerAssertion:
    claim_id = SellerClaimId(
        f"s:{_stable_digest('seller-claim-v1', (field.value, str(segment_index), value))[:62]}"
    )
    return SellerAssertion(
        claim_id=claim_id,
        field=field,
        segment_index=segment_index,
        value=value,
    )


def _evidence_gap(field: MissingField) -> EvidenceGap:
    gap_id = EvidenceGapId(f"g:{_stable_digest('evidence-gap-v1', (field.value,))[:62]}")
    return EvidenceGap(gap_id=gap_id, field=field)


def _reject_brief_header(field: Literal[StudioInputField.BRIEF]) -> Never:
    raise StudioInputParseError(
        field=field,
        code=StudioInputErrorCode.INVALID_LISTING,
    )


def parse_studio_request(raw: str) -> StudioRequest:  # noqa: C901, PLR0912, PLR0915
    """Parse a one-box title and one-to-ten-point brief without inference."""
    try:
        require_studio_input(raw)
    except InputSecurityError as error:
        raise StudioInputParseError(
            field=StudioInputField.BRIEF,
            code=StudioInputErrorCode.INVALID_LISTING,
        ) from error
    normalized = unicodedata.normalize(
        "NFC",
        raw.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n"),
    )
    lines = normalized.split("\n")
    index = next((position for position, line in enumerate(lines) if line.strip()), len(lines))
    seen: set[StudioInputField] = set()
    asin: str | None = None
    brand: str | None = None
    category: str | None = None

    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        header_match = _HEADER_PATTERN.fullmatch(lines[index])
        if header_match is None:
            break
        field = _HEADER_FIELDS[header_match.group("name").casefold()]
        if field in seen:
            raise StudioInputParseError(
                field=field,
                code=StudioInputErrorCode.DUPLICATE_HEADER,
            )
        seen.add(field)
        value = header_match.group("value")
        if not value:
            raise StudioInputParseError(field=field, code=StudioInputErrorCode.EMPTY_HEADER)
        match field:
            case StudioInputField.ASIN:
                if _ASIN_PATTERN.fullmatch(value) is None:
                    raise StudioInputParseError(
                        field=field,
                        code=StudioInputErrorCode.INVALID_ASIN,
                    )
                asin = value
            case StudioInputField.BRAND:
                brand = value
            case StudioInputField.CATEGORY:
                category = value
            case StudioInputField.MARKETPLACE:
                if value.casefold() != "us":
                    raise StudioInputParseError(
                        field=field,
                        code=StudioInputErrorCode.UNSUPPORTED_MARKETPLACE,
                    )
            case invalid_header:
                assert_never(_reject_brief_header(invalid_header))
        index += 1

    try:
        source = parse_listing_block("\n".join(lines[index:]).strip())
    except CopyPointsParseError as error:
        raise StudioInputParseError(
            field=StudioInputField.BRIEF,
            code=StudioInputErrorCode.INVALID_LISTING,
        ) from error

    assertions: list[SellerAssertion] = []
    if asin is not None:
        assertions.append(_seller_assertion(SellerFactField.ASIN, 0, asin))
    if brand is not None:
        assertions.append(_seller_assertion(SellerFactField.BRAND, 0, brand))
    if category is not None:
        assertions.append(_seller_assertion(SellerFactField.CATEGORY, 0, category))
    assertions.append(_seller_assertion(SellerFactField.TITLE, 0, source.title))
    assertions.extend(
        _seller_assertion(SellerFactField.BULLET, segment_index, bullet)
        for segment_index, bullet in enumerate(source.bullets, start=1)
    )

    missing = {
        MissingField.ASIN: asin is None,
        MissingField.BRAND: brand is None,
        MissingField.CATEGORY: category is None,
    }
    gaps = tuple(_evidence_gap(field) for field in _MISSING_FIELDS if missing[field])
    template = source.format_template
    request_parts = (
        "US",
        asin or "",
        brand or "",
        category or "",
        source.title,
        *(f"bullet:{position}:{bullet}" for position, bullet in enumerate(source.bullets, 1)),
        template.title_label or "",
        template.title_label_position,
        template.item_highlights_label or "",
        template.item_highlights_position,
        template.section_label or "",
        template.bullet_marker,
        str(template.blank_line_after_title),
        str(template.blank_line_after_highlights),
        str(template.blank_line_after_section),
        str(template.blank_line_between_points),
        template.terminal_punctuation or "",
    )
    request_hash = RequestHash(_stable_digest("studio-request-v1", request_parts))
    return StudioRequest(
        asin=asin,
        brand=brand,
        category=category,
        title=source.title,
        bullets=tuple(source.bullets),
        format_template=template,
        seller_assertions=tuple(assertions),
        evidence_gaps=gaps,
        request_hash=request_hash,
    )
