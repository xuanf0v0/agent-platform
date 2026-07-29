"""Best-effort live MCP market research during listing optimize.

Connects to configured remote providers (SellerSprite, Sorftime), lists tools,
and tries 1-2 read-oriented tool calls. Results are UI-safe (redacted, truncated).
MCP failures never block listing optimize success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import anyio
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from amazon_create.mcp.live_research_call import (
    ToolCallSpec,
    call_tool_best_effort,
    input_schema_json,
    output_schema_json,
)
from amazon_create.mcp.live_research_data import build_research_bundle, normalize_tool_payload
from amazon_create.mcp.live_research_models import (
    _MAX_TOOLS_SAMPLE,
    McpCallRecord,
    McpToolSnapshot,
    collect_endpoint_secrets,
    content_to_text,
    derive_research_query,
    known_tool_names,
    pick_research_tools,
    preferred_tool_names,
    sanitize_text,
    truncate_summary,
)
from amazon_create.mcp.live_research_session import snapshot_to_dict, snapshots_from_session
from amazon_create.mcp.live_research_types import (
    ResearchBundle,
    ResearchGap,
    ResearchItem,
    ToolNormalization,
)
from amazon_create.mcp.remote_http import (
    McpEndpointSettings,
    RemoteMcpEndpoint,
    endpoints_from_settings,
)
from amazon_create.mcp.response_limits import McpResponseBudget
from amazon_create.mcp.security import (
    MAX_MCP_PAYLOAD_ITEMS,
    MAX_MCP_RESEARCH_GAPS,
    MAX_MCP_RESEARCH_ITEMS,
)
from mcp import ClientSession

_PROVIDER_TIMEOUT_S: Final[float] = 25.0
# SIF market tools return denser JSON than SellerSprite/Sorftime probes.
_SIF_RESPONSE_LIMIT_BYTES: Final[int] = 256_000
_SIF_OPERATION_LIMIT_BYTES: Final[int] = 512_000

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


async def research_endpoint(
    endpoint: RemoteMcpEndpoint,
    *,
    query: str,
    marketplace: str = "US",
    purpose: str = "market",
    timeout_s: float = _PROVIDER_TIMEOUT_S,
) -> McpToolSnapshot:
    """Initialize, list tools, and call preferred research tools for one endpoint."""
    secrets = collect_endpoint_secrets(endpoint)
    headers = dict(endpoint.headers)
    if endpoint.name == "sif":
        response_budget = McpResponseBudget(
            response_limit_bytes=_SIF_RESPONSE_LIMIT_BYTES,
            operation_limit_bytes=_SIF_OPERATION_LIMIT_BYTES,
        )
        provider_timeout = max(timeout_s, 45.0)
    else:
        response_budget = McpResponseBudget()
        provider_timeout = timeout_s

    async def _run() -> McpToolSnapshot:
        async with (
            httpx.AsyncClient(
                headers=headers,
                follow_redirects=False,
                trust_env=False,
                event_hooks={"response": [response_budget.guard_response]},
            ) as http_client,
            streamable_http_client(
                endpoint.url,
                http_client=http_client,
            ) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            _ = await session.initialize()
            # SIF tools/list exceeds the shared response budget (~400KB). Use the
            # built-in keyword tool allowlist and skip catalog listing.
            skip_list = bool(known_tool_names(endpoint.name))
            tools = []
            names: list[str] = []
            sample: list[str] = []
            tool_count = 0
            if not skip_list:
                tools_result = await session.list_tools()
                tools = tools_result.tools
                tool_count = len(tools)
                names = [tool.name for tool in tools[:MAX_MCP_PAYLOAD_ITEMS]]
                sample = [sanitize_text(name, secrets) for name in names[:_MAX_TOOLS_SAMPLE]]
                if tool_count > MAX_MCP_PAYLOAD_ITEMS:
                    return McpToolSnapshot(
                        provider=endpoint.name,
                        status="skipped",
                        tool_count=tool_count,
                        tools_sample=sample,
                        calls=[],
                        error=None,
                        research_gaps=(
                            ResearchGap(code="payload_too_large", provider=endpoint.name),
                        ),
                    )
            targets = pick_research_tools(endpoint.name, names, purpose)
            if not targets:
                gap_code = (
                    "tool_not_allowlisted"
                    if preferred_tool_names(endpoint.name, purpose)
                    else "provider_not_allowlisted"
                )
                return McpToolSnapshot(
                    provider=endpoint.name,
                    status="skipped",
                    tool_count=tool_count,
                    tools_sample=sample,
                    calls=[],
                    error=None,
                    research_gaps=(ResearchGap(code=gap_code, provider=endpoint.name),),
                )
            calls: list[McpCallRecord] = []
            research_items: list[ResearchItem] = []
            research_gaps: list[ResearchGap] = []
            tool_by_name = {tool.name: tool for tool in tools if tool.name in targets}
            for tool_name in targets:
                tool_obj = tool_by_name.get(tool_name)
                outcome = await call_tool_best_effort(
                    session,
                    ToolCallSpec(
                        provider=endpoint.name,
                        tool_name=tool_name,
                        query=query,
                        marketplace=marketplace,
                        input_schema_json=(
                            input_schema_json(tool_obj) if tool_obj is not None else ""
                        ),
                        output_schema_json=(
                            output_schema_json(tool_obj) if tool_obj is not None else ""
                        ),
                        secrets=tuple(secrets),
                    ),
                )
                calls.append(outcome.call)
                research_items.extend(outcome.normalization.items)
                research_gaps.extend(outcome.normalization.gaps)
                if (
                    len(research_items) > MAX_MCP_RESEARCH_ITEMS
                    or len(research_gaps) > MAX_MCP_RESEARCH_GAPS
                ):
                    return McpToolSnapshot(
                        provider=endpoint.name,
                        status="skipped",
                        tool_count=tool_count or len(targets),
                        tools_sample=sample or list(targets),
                        calls=calls,
                        error=None,
                        research_gaps=(
                            ResearchGap(code="payload_too_large", provider=endpoint.name),
                        ),
                    )
            return McpToolSnapshot(
                provider=endpoint.name,
                status="ok",
                tool_count=tool_count or len(targets),
                tools_sample=sample or [sanitize_text(name, secrets) for name in targets],
                calls=calls,
                error=None,
                research_items=tuple(research_items),
                research_gaps=tuple(research_gaps),
            )

    try:
        with anyio.fail_after(provider_timeout):
            return await _run()
    except TimeoutError:
        return McpToolSnapshot(
            provider=endpoint.name,
            status="error",
            tool_count=0,
            tools_sample=[],
            calls=[],
            error=f"timeout after {provider_timeout:.0f}s",
            research_gaps=(ResearchGap(code="provider_error", provider=endpoint.name),),
        )
    except (
        anyio.BrokenResourceError,
        anyio.ClosedResourceError,
        anyio.EndOfStream,
        ExceptionGroup,
        McpError,
        httpx.HTTPError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        limit_hit = response_budget.limit_hit
        message = None if limit_hit else "provider unavailable"
        return McpToolSnapshot(
            provider=endpoint.name,
            status="skipped" if limit_hit else "error",
            tool_count=0,
            tools_sample=[],
            calls=[],
            error=message,
            research_gaps=(
                ResearchGap(
                    code="payload_too_large" if limit_hit else "provider_error",
                    provider=endpoint.name,
                ),
            ),
        )


async def fetch_live_mcp_research(
    settings: McpEndpointSettings,
    *,
    query: str,
    marketplace: str = "US",
    purpose: str = "market",
    timeout_s: float = _PROVIDER_TIMEOUT_S,
) -> list[McpToolSnapshot]:
    """Fetch live research from every configured remote MCP provider.

    Returns an empty list when no keys are configured. Per-provider errors become
    ``status="error"`` snapshots; never raises for remote failures.
    """
    from amazon_create.mcp.sif_research import research_sif_endpoint

    endpoints = endpoints_from_settings(settings)
    if not endpoints:
        return []
    snapshots: list[McpToolSnapshot] = []
    for endpoint in endpoints:
        if not preferred_tool_names(endpoint.name, purpose):
            continue
        if endpoint.name == "sif":
            # SIF uses plain JSON-RPC (tools/list is too large for streamable HTTP).
            snapshots.append(
                await anyio.to_thread.run_sync(
                    lambda ep=endpoint: research_sif_endpoint(
                        ep,
                        query=query,
                        marketplace=marketplace,
                        purpose=purpose,
                        timeout_s=max(timeout_s, 45.0),
                    )
                )
            )
        else:
            snapshots.append(
                await research_endpoint(
                    endpoint,
                    query=query,
                    marketplace=marketplace,
                    purpose=purpose,
                    timeout_s=timeout_s,
                )
            )
    return snapshots


def fetch_live_mcp_research_sync(
    settings: McpEndpointSettings,
    *,
    query: str,
    marketplace: str = "US",
    purpose: str = "market",
    timeout_s: float = _PROVIDER_TIMEOUT_S,
) -> list[McpToolSnapshot]:
    """Sync wrapper for Streamlit / CLI (runs the async research path)."""

    async def _run() -> list[McpToolSnapshot]:
        return await fetch_live_mcp_research(
            settings,
            query=query,
            marketplace=marketplace,
            purpose=purpose,
            timeout_s=timeout_s,
        )

    return anyio.run(_run)


def research_bundle_from_snapshots(
    snapshots: Sequence[McpToolSnapshot | Mapping[str, str]],
) -> ResearchBundle:
    """Combine successful normalized data and explicit provider gaps."""
    normalizations: list[ToolNormalization] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, McpToolSnapshot):
            normalizations.append(
                ToolNormalization(
                    gaps=(
                        ResearchGap(
                            code="payload_malformed",
                            provider="automatic_research",
                            tool="session_cache",
                        ),
                    )
                )
            )
            continue
        gaps = list(snapshot.research_gaps)
        if snapshot.status == "error" and not gaps:
            gaps.append(ResearchGap(code="provider_error", provider=snapshot.provider))
        normalizations.append(ToolNormalization(items=snapshot.research_items, gaps=tuple(gaps)))
    return build_research_bundle(tuple(normalizations))


__all__ = [
    "McpCallRecord",
    "McpToolSnapshot",
    "ResearchBundle",
    "content_to_text",
    "derive_research_query",
    "fetch_live_mcp_research",
    "fetch_live_mcp_research_sync",
    "normalize_tool_payload",
    "pick_research_tools",
    "research_bundle_from_snapshots",
    "research_endpoint",
    "sanitize_text",
    "snapshot_to_dict",
    "snapshots_from_session",
    "truncate_summary",
]
