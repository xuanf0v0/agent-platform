"""Source-bound automatic research cache loading."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from amazon_copy.automatic_context import source_fingerprint
from amazon_copy.automatic_models import (
    AutomaticOptimizationContext,
    AutomaticOptimizationDependencies,
    AutomaticResearchCache,
)
from amazon_copy.config import Settings
from amazon_copy.mcp.live_research import (
    derive_research_query,
    fetch_live_mcp_research_sync,
    research_bundle_from_snapshots,
)
from amazon_copy.mcp.live_research_models import McpToolSnapshot
from amazon_copy.mcp.live_research_session import snapshot_to_dict, snapshots_from_session
from amazon_copy.mcp.live_research_types import ResearchBundle, ResearchGap, ResearchItem
from amazon_copy.mcp.security import (
    MAX_MCP_CACHE_BYTES,
    MAX_MCP_CACHE_CALLS,
    MAX_MCP_CACHE_SNAPSHOTS,
    MAX_MCP_RESEARCH_GAPS,
    MAX_MCP_RESEARCH_ITEMS,
    sanitize_mcp_session_text,
)
from amazon_copy.schemas import SourceListingCopy


@dataclass(frozen=True, slots=True)
class AutomaticResearchRequest:
    """Inputs needed to reuse or fetch one source-bound research bundle."""

    source_text: str
    source: SourceListingCopy
    context: AutomaticOptimizationContext
    dependencies: AutomaticOptimizationDependencies


_RawResearchSnapshot = McpToolSnapshot | Mapping[str, str]


def _malformed_research_snapshot() -> McpToolSnapshot:
    return McpToolSnapshot(
        provider="automatic_research",
        status="error",
        tool_count=0,
        error="provider returned malformed snapshot",
        research_gaps=(
            ResearchGap(
                code="payload_malformed",
                provider="automatic_research",
                tool="session_cache",
            ),
        ),
    )


def _safe_research_snapshots(
    raw: Sequence[_RawResearchSnapshot],
) -> list[McpToolSnapshot]:
    snapshots = [snapshot for snapshot in raw if isinstance(snapshot, McpToolSnapshot)]
    if len(snapshots) != len(raw):
        snapshots.append(_malformed_research_snapshot())
    return snapshots


def _cache_exceeds_limits(cache: AutomaticResearchCache) -> bool:
    snapshots = cache.snapshots
    if len(snapshots) > MAX_MCP_CACHE_SNAPSHOTS:
        return True
    if sum(len(snapshot.calls) for snapshot in snapshots) > MAX_MCP_CACHE_CALLS:
        return True
    if (
        max(
            sum(len(snapshot.research_items) for snapshot in snapshots),
            len(cache.bundle.items),
        )
        > MAX_MCP_RESEARCH_ITEMS
    ):
        return True
    if (
        max(
            sum(len(snapshot.research_gaps) for snapshot in snapshots),
            len(cache.bundle.gaps),
        )
        > MAX_MCP_RESEARCH_GAPS
    ):
        return True
    return len(cache.model_dump_json().encode("utf-8")) > MAX_MCP_CACHE_BYTES


def _degraded_research_cache(cache: AutomaticResearchCache) -> AutomaticResearchCache:
    provider = "automatic_research"
    gap = ResearchGap(code="payload_too_large", provider=provider, tool="session_cache")
    snapshot = McpToolSnapshot(
        provider=provider,
        status="skipped",
        tool_count=0,
        research_gaps=(gap,),
    )
    return AutomaticResearchCache(
        source_fingerprint=sanitize_mcp_session_text(cache.source_fingerprint)[:128],
        query=sanitize_mcp_session_text(cache.query)[:512],
        snapshots=(snapshot,),
        bundle=ResearchBundle(gaps=(gap,)),
    )


def _safe_research_item(item: ResearchItem) -> ResearchItem:
    return item.model_copy(
        update={
            "key": sanitize_mcp_session_text(item.key),
            "value": sanitize_mcp_session_text(item.value),
            "provider": sanitize_mcp_session_text(item.provider),
            "tool": sanitize_mcp_session_text(item.tool),
        }
    )


def _safe_research_gap(gap: ResearchGap) -> ResearchGap:
    return gap.model_copy(
        update={
            "provider": sanitize_mcp_session_text(gap.provider),
            "tool": sanitize_mcp_session_text(gap.tool),
        }
    )


def secure_research_cache(cache: AutomaticResearchCache) -> AutomaticResearchCache:
    """Return a bounded redacted cache or one typed payload-limit gap."""
    if _cache_exceeds_limits(cache):
        return _degraded_research_cache(cache)
    safe_snapshots = tuple(
        snapshots_from_session([snapshot_to_dict(snapshot) for snapshot in cache.snapshots])
    )
    safe_bundle = ResearchBundle(
        items=tuple(_safe_research_item(item) for item in cache.bundle.items),
        gaps=tuple(_safe_research_gap(gap) for gap in cache.bundle.gaps),
        allowed_keywords=tuple(
            sanitize_mcp_session_text(keyword) for keyword in cache.bundle.allowed_keywords
        ),
    )
    secured = AutomaticResearchCache(
        source_fingerprint=cache.source_fingerprint,
        query=sanitize_mcp_session_text(cache.query),
        snapshots=safe_snapshots,
        bundle=safe_bundle,
    )
    return _degraded_research_cache(cache) if _cache_exceeds_limits(secured) else secured


def load_research_cache(
    request: AutomaticResearchRequest,
) -> tuple[AutomaticResearchCache, bool]:
    """Reuse an exact source cache or fetch one safe normalized bundle."""
    fingerprint = source_fingerprint(request.source_text)
    query = derive_research_query(request.source.title)
    cached = request.context.cached_research
    if cached is not None and cached.source_fingerprint == fingerprint:
        return secure_research_cache(cached), True
    settings = request.dependencies.settings or Settings()
    fetcher = request.dependencies.research_fetcher or fetch_live_mcp_research_sync
    try:
        snapshots = _safe_research_snapshots(fetcher(settings, query=query))
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError, ExceptionGroup):
        snapshots = [_malformed_research_snapshot()]
    bundle = research_bundle_from_snapshots(snapshots)
    return (
        secure_research_cache(
            AutomaticResearchCache(
                source_fingerprint=fingerprint,
                query=query,
                snapshots=tuple(snapshots),
                bundle=bundle,
            )
        ),
        False,
    )


__all__ = ["AutomaticResearchRequest", "load_research_cache", "secure_research_cache"]
