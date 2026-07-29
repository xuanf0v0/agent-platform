"""Load allowlisted specialized rule profiles from packaged resources."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import TYPE_CHECKING

from amazon_copy.mcp.security import sanitize_mcp_text
from amazon_copy.resources.amazon_copy_optimization.errors import (
    ContractResourceError,
    ContractResourceErrorCode,
)
from amazon_copy.resources.amazon_copy_optimization.loader import ContractResourceLoader
from amazon_copy.resources.amazon_copy_optimization.manifest import PROFILE_RESOURCES
from amazon_copy.specialized_rules.catalog import ALLOWLISTED_PROFILE_FILENAMES
from amazon_copy.specialized_rules.models import (
    RuleGapCode,
    SpecializedRuleCache,
    SpecializedRuleGap,
    SpecializedRuleLoad,
    SpecializedRuleSnapshot,
)
from amazon_copy.specialized_rules.resource_loader import SpecializedRuleRequest

if TYPE_CHECKING:
    from amazon_copy.config import Settings

_ERROR_TO_GAP: dict[ContractResourceErrorCode, RuleGapCode] = {
    ContractResourceErrorCode.HASH_MISMATCH: "resource_malformed",
    ContractResourceErrorCode.INVALID_UTF8: "resource_malformed",
    ContractResourceErrorCode.MISSING_RESOURCE: "resource_missing",
    ContractResourceErrorCode.NON_MARKDOWN: "resource_not_markdown",
    ContractResourceErrorCode.NOT_ALLOWLISTED: "resource_missing",
    ContractResourceErrorCode.RESOURCE_TOO_LARGE: "resource_too_large",
    ContractResourceErrorCode.DUPLICATE_RESOURCE: "resource_malformed",
    ContractResourceErrorCode.INVALID_POLICY: "resource_malformed",
}


@lru_cache(maxsize=1)
def _packaged_profile_filenames() -> frozenset[str]:
    """Filenames present in the offline contract package (subset of catalog)."""
    return frozenset(resource.filename for resource in PROFILE_RESOURCES)


def _gap(code: RuleGapCode, profile_filename: str = "") -> SpecializedRuleGap:
    return SpecializedRuleGap(code=code, profile_filename=profile_filename)


def _requested_profiles(request: SpecializedRuleRequest) -> tuple[str, ...]:
    """Route profiles that are both allowlisted and packaged for local load."""
    packaged = _packaged_profile_filenames()
    return tuple(
        dict.fromkeys(
            profile.filename
            for profile in request.route.profiles
            if profile.filename in ALLOWLISTED_PROFILE_FILENAMES
            and profile.filename in packaged
        )
    )


def _cached_load(
    request: SpecializedRuleRequest,
    cached: SpecializedRuleCache | None,
) -> SpecializedRuleLoad | None:
    requested = _requested_profiles(request)
    if (
        cached is not None
        and cached.source_fingerprint == request.source_fingerprint
        and cached.route_fingerprint == request.route.fingerprint
        and cached.requested_profiles == requested
    ):
        return SpecializedRuleLoad(cache=cached, reused=True)
    return None


def _read_snapshot(
    loader: ContractResourceLoader,
    filename: str,
) -> SpecializedRuleSnapshot | SpecializedRuleGap:
    try:
        loaded = loader.load_profile(filename)
    except ContractResourceError as error:
        return _gap(_ERROR_TO_GAP.get(error.code, "resource_missing"), filename)
    sanitized = sanitize_mcp_text(loaded.markdown)
    return SpecializedRuleSnapshot(
        profile_filename=filename,
        content_markdown=sanitized,
        content_sha256=hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
    )


def fetch_specialized_rules_local(
    settings: Settings | object,
    *,
    request: SpecializedRuleRequest,
    cached: SpecializedRuleCache | None = None,
) -> SpecializedRuleLoad:
    """Load route profiles from installed package data (no remote MCP)."""
    del settings
    reused = _cached_load(request, cached)
    if reused is not None:
        return reused
    requested = _requested_profiles(request)
    if not requested:
        return SpecializedRuleLoad(
            cache=SpecializedRuleCache(
                source_fingerprint=request.source_fingerprint,
                route_fingerprint=request.route.fingerprint,
                requested_profiles=(),
                gaps=(_gap("resource_missing"),),
            ),
            reused=False,
        )
    try:
        loader = ContractResourceLoader.from_package()
    except ContractResourceError:
        return SpecializedRuleLoad(
            cache=SpecializedRuleCache(
                source_fingerprint=request.source_fingerprint,
                route_fingerprint=request.route.fingerprint,
                requested_profiles=requested,
                gaps=(_gap("provider_error"),),
            ),
            reused=False,
        )
    snapshots: list[SpecializedRuleSnapshot] = []
    gaps: list[SpecializedRuleGap] = []
    for filename in requested:
        outcome = _read_snapshot(loader, filename)
        if isinstance(outcome, SpecializedRuleSnapshot):
            snapshots.append(outcome)
        else:
            gaps.append(outcome)
    loaded = bool(requested) and not gaps and len(snapshots) == len(requested)
    return SpecializedRuleLoad(
        cache=SpecializedRuleCache(
            source_fingerprint=request.source_fingerprint,
            route_fingerprint=request.route.fingerprint,
            requested_profiles=requested,
            snapshots=tuple(snapshots),
            gaps=tuple(gaps),
            all_requested_loaded=loaded,
        ),
        reused=False,
    )


__all__ = ["fetch_specialized_rules_local"]
