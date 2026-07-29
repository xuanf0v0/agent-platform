"""Serializable specialized-rule cache models and exhaustiveness helpers."""

import hashlib
from typing import ClassVar, Literal, Never, TypeAlias, TypeVar, final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from amazon_copy.mcp.security import sanitize_mcp_text
from amazon_copy.specialized_rules.catalog import ALLOWLISTED_PROFILE_FILENAMES

_Variant = TypeVar("_Variant")


@final
class _ExhaustivenessSentinel:
    __slots__ = ()


def widen_variant(
    value: _Variant,
) -> _Variant | _ExhaustivenessSentinel:
    return value


def reject_variant(_value: _ExhaustivenessSentinel) -> Never:
    raise AssertionError

_FROZEN_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    hide_input_in_errors=True,
)
_CACHE_FALSE_SUCCESS = "rule_cache_false_success"
_CACHE_FALSE_SUCCESS_MESSAGE = "loaded state requires every requested rule snapshot"
_CONTENT_HASH_MISMATCH = "rule_content_hash_mismatch"
_CONTENT_HASH_MISMATCH_MESSAGE = "rule content hash does not match Markdown"
_PROFILE_NOT_ALLOWLISTED = "rule_profile_not_allowlisted"
_PROFILE_NOT_ALLOWLISTED_MESSAGE = "rule profile is not allowlisted"


RuleGapCode: TypeAlias = Literal[
    "endpoint_unconfigured",
    "pagination_cycle",
    "pagination_limit",
    "provider_error",
    "provider_timeout",
    "resource_credential_rejected",
    "resource_malformed",
    "resource_missing",
    "resource_not_markdown",
    "resource_too_large",
    "unsafe_endpoint",
]


class SpecializedRuleGap(BaseModel):
    """Safe machine-readable reason that a requested profile was not loaded."""

    model_config: ClassVar[ConfigDict] = _FROZEN_CONFIG

    code: RuleGapCode
    profile_filename: str = ""


class SpecializedRuleSnapshot(BaseModel):
    """Sanitized internal guidance loaded from one allowlisted Markdown profile."""

    model_config: ClassVar[ConfigDict] = _FROZEN_CONFIG

    profile_filename: str
    content_markdown: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority: Literal["internal_guidance"] = "internal_guidance"
    can_authorize_facts: Literal[False] = False

    @field_validator("profile_filename")
    @classmethod
    def require_allowlisted_profile(cls, value: str) -> str:
        """Reject cache snapshots outside the reviewed filename allowlist."""
        if value not in ALLOWLISTED_PROFILE_FILENAMES:
            raise PydanticCustomError(
                _PROFILE_NOT_ALLOWLISTED,
                _PROFILE_NOT_ALLOWLISTED_MESSAGE,
            )
        return value

    @field_validator("content_markdown")
    @classmethod
    def redact_credential_patterns(cls, value: str) -> str:
        """Remove credential-shaped text before cache serialization."""
        return sanitize_mcp_text(value)

    @model_validator(mode="after")
    def require_matching_content_hash(self) -> "SpecializedRuleSnapshot":
        """Bind the content hash to the sanitized Markdown bytes."""
        actual = hashlib.sha256(self.content_markdown.encode("utf-8")).hexdigest()
        if actual != self.content_sha256:
            raise PydanticCustomError(
                _CONTENT_HASH_MISMATCH,
                _CONTENT_HASH_MISMATCH_MESSAGE,
            )
        return self


class SpecializedRuleCache(BaseModel):
    """Source- and route-bound cache identity for specialized rule resources."""

    model_config: ClassVar[ConfigDict] = _FROZEN_CONFIG

    source_fingerprint: str
    route_fingerprint: str
    requested_profiles: tuple[str, ...] = ()
    snapshots: tuple[SpecializedRuleSnapshot, ...] = ()
    gaps: tuple[SpecializedRuleGap, ...] = ()
    all_requested_loaded: bool = False

    @model_validator(mode="after")
    def prevent_false_loaded_state(self) -> "SpecializedRuleCache":
        """Reject success claims that lack every requested snapshot."""
        requested = self.requested_profiles
        loaded = tuple(snapshot.profile_filename for snapshot in self.snapshots)
        consistent_success = (
            bool(requested)
            and not self.gaps
            and len(requested) == len(set(requested))
            and len(loaded) == len(set(loaded))
            and set(requested) == set(loaded)
        )
        if self.all_requested_loaded and not consistent_success:
            raise PydanticCustomError(
                _CACHE_FALSE_SUCCESS,
                _CACHE_FALSE_SUCCESS_MESSAGE,
            )
        return self


class SpecializedRuleLoad(BaseModel):
    """One cache outcome with an explicit resume-reuse signal."""

    model_config: ClassVar[ConfigDict] = _FROZEN_CONFIG

    cache: SpecializedRuleCache
    reused: bool


__all__ = [
    "RuleGapCode",
    "SpecializedRuleCache",
    "SpecializedRuleGap",
    "SpecializedRuleLoad",
    "SpecializedRuleSnapshot",
]
