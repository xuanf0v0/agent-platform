"""Typed evidence provenance and deterministic resolution boundaries."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, ClassVar, Final, Literal, NewType, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic.types import StringConstraints
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from collections.abc import Sequence

ClaimId = NewType("ClaimId", str)
SnapshotId = NewType("SnapshotId", str)
CitationId = NewType("CitationId", str)
ContentHash = NewType("ContentHash", str)

_ID_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_HASH_PATTERN: Final = r"^[0-9a-f]{64}$"
_TIMEZONE_ERROR: Final = ("timezone_aware", "timestamp must include a UTC offset")
_EXPIRY_ERROR: Final = ("invalid_expiry", "expiry must match the authority and lane TTL")
_UNSAFE_TEXT_ERROR: Final = ("unsafe_evidence_text", "evidence text must be non-sensitive")
_HASH_ERROR: Final = ("content_hash_mismatch", "content hash must match canonical claim value")
_DUPLICATE_ERROR: Final = ("duplicate_claim_id", "claim IDs must be unique")
_ONE_DAY: Final = timedelta(hours=24)
_SEVEN_DAYS: Final = timedelta(days=7)
_DIRECTIVE: Final = r"(?:ignore|disregard|override)[\s._:-]+(?:all[\s._:-]+)?"
_TARGET: Final = r"(?:previous|prior|system|developer)[\s._:-]+(?:instructions?|prompts?)"
_ROLE_TAG: Final = r"<\s*/?(?:system|assistant|developer)\b"
_INJECTION_TEXT: Final = re.compile(_DIRECTIVE + _TARGET + "|" + _ROLE_TAG, re.IGNORECASE)
_CREDENTIAL_TEXT: Final = re.compile(
    r"credential|password|bearer|api[\s._:-]*key|(?:sk|ghp|xoxb|akia)[-_][a-z0-9_-]{8,}",
    re.IGNORECASE,
)


def _canonical_content(content: str) -> str:
    return unicodedata.normalize("NFC", content.replace("\r\n", "\n").replace("\r", "\n"))


def _safe_value(value: str) -> str:
    canonical = _canonical_content(value)
    if _INJECTION_TEXT.search(canonical):
        raise PydanticCustomError(*_UNSAFE_TEXT_ERROR)
    return canonical


def _safe_identifier(value: str) -> str:
    canonical = _safe_value(value)
    if _CREDENTIAL_TEXT.search(canonical):
        raise PydanticCustomError(*_UNSAFE_TEXT_ERROR)
    return canonical


def _as_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise PydanticCustomError(*_TIMEZONE_ERROR)
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]
_ID_CONSTRAINTS: Final = StringConstraints(min_length=1, max_length=64, pattern=_ID_PATTERN)
_PROVENANCE: Final = StringConstraints(min_length=1, max_length=128, pattern=_ID_PATTERN)
_KEY: Final = StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$")
_VALUE: Final = StringConstraints(min_length=1, max_length=512)
ClaimIdValue = Annotated[ClaimId, _ID_CONSTRAINTS, AfterValidator(_safe_identifier)]
SnapshotIdValue = Annotated[SnapshotId, _ID_CONSTRAINTS, AfterValidator(_safe_identifier)]
CitationIdValue = Annotated[CitationId, _ID_CONSTRAINTS, AfterValidator(_safe_identifier)]
ContentHashValue = Annotated[ContentHash, StringConstraints(pattern=_HASH_PATTERN)]
Identifier = Annotated[str, _PROVENANCE, AfterValidator(_safe_identifier)]
ClaimKey = Annotated[str, _KEY, AfterValidator(_safe_value)]
ClaimValue = Annotated[str, _VALUE, AfterValidator(_safe_value)]


class _FrozenBoundary(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class ResearchLane(StrEnum):
    """A bounded external-research lane."""

    PRODUCT = "product"
    KEYWORD = "keyword"
    COMPETITOR = "competitor"
    POLICY = "policy"
    SHOPPER = "shopper"


class EvidenceAuthority(StrEnum):
    """Origin authority carried by a normalized claim."""

    USER_ASSERTED = "user_asserted"
    PROVIDER_OBSERVED = "provider_observed"
    OFFICIAL_POLICY = "official_policy"
    INFERENCE = "inference"
    SUGGESTION = "suggestion"


class LaneStatus(StrEnum):
    """Public outcome of one bounded research lane."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"


def _expires_at(
    lane: ResearchLane,
    authority: EvidenceAuthority,
    retrieved_at: datetime,
) -> datetime | None:
    match authority:  # noqa: MATCH_OK - every enum member is explicit
        case EvidenceAuthority.USER_ASSERTED:
            return None
        case (
            EvidenceAuthority.PROVIDER_OBSERVED
            | EvidenceAuthority.OFFICIAL_POLICY
            | EvidenceAuthority.INFERENCE
            | EvidenceAuthority.SUGGESTION
        ):
            pass
    match lane:  # noqa: MATCH_OK - every enum member is explicit
        case ResearchLane.PRODUCT | ResearchLane.POLICY | ResearchLane.COMPETITOR:
            return retrieved_at + _ONE_DAY
        case ResearchLane.KEYWORD | ResearchLane.SHOPPER:
            return retrieved_at + _SEVEN_DAYS


class EvidenceClaim(_FrozenBoundary):
    """One normalized fact without its raw provider payload."""

    claim_id: ClaimIdValue
    lane: ResearchLane
    claim_key: ClaimKey
    value: ClaimValue
    authority: EvidenceAuthority
    retrieved_at: UtcDateTime
    source_id: Identifier
    server_id: Identifier
    tool_id: Identifier
    confidence: float = Field(ge=0.0, le=1.0)
    marketplace: Literal["US"] = "US"
    content_hash: ContentHashValue
    excerpt: str = Field(default="", max_length=160, exclude=True, repr=False)
    expires_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def _expiry_matches_provenance(self) -> Self:
        if self.content_hash != canonical_content_hash(self.value):
            raise PydanticCustomError(*_HASH_ERROR)
        expected = _expires_at(self.lane, self.authority, self.retrieved_at)
        if self.expires_at is None and expected is not None:
            object.__setattr__(self, "expires_at", expected)
        elif self.expires_at != expected:
            raise PydanticCustomError(*_EXPIRY_ERROR)
        return self


def _require_unique_claim_ids(claims: Sequence[EvidenceClaim]) -> None:
    claim_ids = tuple(claim.claim_id for claim in claims)
    if len(claim_ids) != len(set(claim_ids)):
        raise PydanticCustomError(*_DUPLICATE_ERROR)


class Citation(_FrozenBoundary):
    """A redacted reference to one normalized evidence claim."""

    citation_id: CitationIdValue
    claim_id: ClaimIdValue
    source_id: Identifier
    retrieved_at: UtcDateTime
    content_hash: ContentHashValue
    marketplace: Literal["US"] = "US"
    excerpt: str = Field(default="", max_length=160, exclude=True, repr=False)


class LaneReport(_FrozenBoundary):
    """Redacted status and claim references for one research lane."""

    lane: ResearchLane
    status: LaneStatus
    claim_ids: tuple[ClaimIdValue, ...] = ()
    error_code: Identifier | None = None


class EvidenceSnapshot(_FrozenBoundary):
    """Immutable, payload-free evidence captured for one US run."""

    snapshot_id: SnapshotIdValue
    created_at: UtcDateTime
    marketplace: Literal["US"] = "US"
    claims: tuple[EvidenceClaim, ...] = ()
    citations: tuple[Citation, ...] = ()
    lane_reports: tuple[LaneReport, ...] = ()

    @model_validator(mode="after")
    def _claim_ids_are_unique(self) -> Self:
        _require_unique_claim_ids(self.claims)
        return self


class FreshnessResult(_FrozenBoundary):
    """Fresh claims and stale IDs after deterministic TTL filtering."""

    fresh_claims: tuple[EvidenceClaim, ...] = ()
    stale_claim_ids: tuple[ClaimIdValue, ...] = ()


class ResolutionResult(_FrozenBoundary):
    """Stable claim partitions emitted by resolution."""

    eligible_claims: tuple[EvidenceClaim, ...] = ()
    stale_claim_ids: tuple[ClaimIdValue, ...] = ()
    conflict_claim_ids: tuple[ClaimIdValue, ...] = ()
    superseded_claim_ids: tuple[ClaimIdValue, ...] = ()
    ineligible_claim_ids: tuple[ClaimIdValue, ...] = ()
    resolved_at: UtcDateTime


def canonical_content_hash(content: str) -> ContentHash:
    """Hash canonical NFC text encoded as UTF-8 without retaining the input."""
    return ContentHash(hashlib.sha256(_canonical_content(content).encode("utf-8")).hexdigest())


def filter_fresh_claims(
    claims: Sequence[EvidenceClaim],
    *,
    now: datetime,
) -> FreshnessResult:
    """Exclude claims at or beyond expiry using an injected UTC clock."""
    _require_unique_claim_ids(claims)
    now_utc = _as_utc(now)
    fresh: list[EvidenceClaim] = []
    stale: list[ClaimId] = []
    for claim in sorted(claims, key=lambda item: item.claim_id):
        expires_at = claim.expires_at
        if expires_at is not None and now_utc >= expires_at:
            stale.append(claim.claim_id)
        else:
            fresh.append(claim)
    return FreshnessResult(fresh_claims=tuple(fresh), stale_claim_ids=tuple(stale))


def _authority_rank(claim: EvidenceClaim) -> int | None:
    match claim.lane, claim.authority:  # noqa: MATCH_OK - final case covers valid pairs
        case ResearchLane.PRODUCT, EvidenceAuthority.USER_ASSERTED:
            return 2
        case ResearchLane.PRODUCT, EvidenceAuthority.PROVIDER_OBSERVED:
            return 1
        case ResearchLane.POLICY, EvidenceAuthority.OFFICIAL_POLICY:
            return 2
        case ResearchLane.POLICY, EvidenceAuthority.PROVIDER_OBSERVED:
            return 1
        case (
            ResearchLane.COMPETITOR | ResearchLane.KEYWORD | ResearchLane.SHOPPER,
            EvidenceAuthority.PROVIDER_OBSERVED,
        ):
            return 1
        case ResearchLane(), EvidenceAuthority():
            return None


def _normalized_value(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def resolve_claims(
    claims: Sequence[EvidenceClaim],
    *,
    now: datetime,
) -> ResolutionResult:
    """Resolve claims into deterministic eligibility partitions."""
    now_utc = _as_utc(now)
    freshness = filter_fresh_claims(claims, now=now_utc)
    groups: dict[tuple[ResearchLane, str], list[tuple[int, EvidenceClaim]]] = {}
    eligible: list[EvidenceClaim] = []
    conflicts: list[ClaimId] = []
    superseded: list[ClaimId] = []
    ineligible: list[ClaimId] = []
    for claim in freshness.fresh_claims:
        rank = _authority_rank(claim)
        if rank is None:
            ineligible.append(claim.claim_id)
        else:
            groups.setdefault((claim.lane, claim.claim_key), []).append((rank, claim))
    for group_key in sorted(groups, key=lambda item: (item[0].value, item[1])):
        ranked_claims = groups[group_key]
        highest_rank = max(rank for rank, _claim in ranked_claims)
        highest = [claim for rank, claim in ranked_claims if rank == highest_rank]
        lower = [claim for rank, claim in ranked_claims if rank < highest_rank]
        superseded.extend(claim.claim_id for claim in lower)
        if len({_normalized_value(claim.value) for claim in highest}) > 1:
            conflicts.extend(claim.claim_id for claim in highest)
        else:
            eligible.extend(highest)
    return ResolutionResult(
        eligible_claims=tuple(sorted(eligible, key=lambda claim: claim.claim_id)),
        stale_claim_ids=tuple(sorted(freshness.stale_claim_ids)),
        conflict_claim_ids=tuple(sorted(conflicts)),
        superseded_claim_ids=tuple(sorted(superseded)),
        ineligible_claim_ids=tuple(sorted(ineligible)),
        resolved_at=now_utc,
    )
