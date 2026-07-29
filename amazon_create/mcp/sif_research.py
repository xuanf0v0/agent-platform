"""Direct JSON-RPC research client for SIF MCP.

SIF's tools/list catalog exceeds the shared Streamable-HTTP response budget, and
the streamable transport is less reliable than plain JSON POST for this host.
This module initializes once and calls a small allowlisted set of market tools
with secret-key auth, then normalizes results through the shared research gate.
"""

from __future__ import annotations

import json
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit

import httpx

from amazon_create.mcp.live_research_call import builtin_tool_arguments
from amazon_create.mcp.live_research_data import normalize_tool_payload
from amazon_create.mcp.live_research_models import (
    McpCallRecord,
    McpToolSnapshot,
    preferred_tool_names,
    sanitize_text,
)
from amazon_create.mcp.live_research_types import ResearchGap, ResearchItem
from amazon_create.mcp.remote_http import RemoteMcpEndpoint
from amazon_create.mcp.security import is_secret_key, sanitize_mcp_payload

_SIF_TIMEOUT_S: Final[float] = 45.0
_SIF_MAX_RESPONSE_BYTES: Final[int] = 256_000
_PROTOCOL_VERSION: Final[str] = "2024-11-05"


def _collect_secrets(endpoint: RemoteMcpEndpoint) -> tuple[str, ...]:
    secrets = [value for value in endpoint.headers.values() if value]
    secrets.extend(
        value
        for key, value in parse_qsl(urlsplit(endpoint.url).query, keep_blank_values=True)
        if is_secret_key(key) and value
    )
    return tuple(secrets)


def _jsonrpc_request(
    client: httpx.Client,
    *,
    url: str,
    headers: dict[str, str],
    request_id: int,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        body["params"] = params
    response = client.post(url, headers=headers, json=body)
    response.raise_for_status()
    if len(response.content) > _SIF_MAX_RESPONSE_BYTES:
        message = "sif response exceeded byte budget"
        raise ValueError(message)
    payload = response.json()
    if not isinstance(payload, dict):
        message = "sif response is not a JSON object"
        raise TypeError(message)
    return payload


def _result_text(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        if parts:
            return "\n".join(parts)
    structured = result.get("structuredContent")
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _compact_sif_payload(value: object) -> object:
    """Keep only keyword/metric fields SIF returns in large market payloads."""
    if not isinstance(value, dict):
        return value
    data = value
    compact: dict[str, object] = {}
    query_context = data.get("query_context")
    if isinstance(query_context, dict):
        keyword = query_context.get("keyword")
        if isinstance(keyword, str) and keyword.strip():
            compact["keyword"] = keyword.strip()
    profiles = data.get("profiles")
    if isinstance(profiles, list):
        compact_profiles: list[dict[str, object]] = []
        for row in profiles[:20]:
            if not isinstance(row, dict):
                continue
            profile: dict[str, object] = {}
            keyword = row.get("keyword")
            if isinstance(keyword, str) and keyword.strip():
                profile["keyword"] = keyword.strip()
            current = row.get("current")
            if isinstance(current, dict):
                volume = current.get("search_volume")
                if isinstance(volume, (int, float, str)):
                    profile["current"] = {"search_volume": volume}
            if profile:
                compact_profiles.append(profile)
        if compact_profiles:
            compact["profiles"] = compact_profiles
    demand = data.get("demand_snapshot")
    if isinstance(demand, dict):
        for key in ("search_volume", "volume", "monthly_search_volume", "demand"):
            if key in demand and isinstance(demand[key], (int, float, str)):
                compact[key] = demand[key]
    top = data.get("top_competitors")
    if isinstance(top, list):
        # Competitors are not product facts; only keep keyword-like titles if short.
        related: list[str] = []
        for row in top[:10]:
            if not isinstance(row, dict):
                continue
            for key in ("keyword", "title", "search_term"):
                text = row.get(key)
                if isinstance(text, str) and 2 <= len(text.strip()) <= 80:
                    related.append(text.strip())
                    break
        if related:
            compact["related_keywords"] = related
    return compact or data


def research_sif_endpoint(
    endpoint: RemoteMcpEndpoint,
    *,
    query: str,
    timeout_s: float = _SIF_TIMEOUT_S,
) -> McpToolSnapshot:
    """Call allowlisted SIF market tools over plain JSON-RPC HTTP."""
    secrets = _collect_secrets(endpoint)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **dict(endpoint.headers),
    }
    targets = list(preferred_tool_names("sif"))[:2]
    calls: list[McpCallRecord] = []
    research_items: list[ResearchItem] = []
    research_gaps: list[ResearchGap] = []
    try:
        with httpx.Client(
            timeout=timeout_s,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            init = _jsonrpc_request(
                client,
                url=endpoint.url,
                headers=headers,
                request_id=1,
                method="initialize",
                params={
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "amazon-copy-sif", "version": "0.1.0"},
                },
            )
            if "error" in init:
                error = sanitize_text(str(init.get("error")), secrets)
                return McpToolSnapshot(
                    provider="sif",
                    status="error",
                    tool_count=0,
                    tools_sample=[],
                    calls=[],
                    error=error or "initialize failed",
                    research_gaps=(ResearchGap(code="provider_error", provider="sif"),),
                )
            for index, tool_name in enumerate(targets, start=2):
                arguments = builtin_tool_arguments("sif", tool_name, query)
                if arguments is None:
                    calls.append(
                        McpCallRecord(
                            tool=tool_name,
                            ok=False,
                            summary_text="unsupported input schema",
                        )
                    )
                    research_gaps.append(
                        ResearchGap(
                            code="input_schema_unsupported",
                            provider="sif",
                            tool=tool_name,
                        )
                    )
                    continue
                try:
                    payload = _jsonrpc_request(
                        client,
                        url=endpoint.url,
                        headers=headers,
                        request_id=index,
                        method="tools/call",
                        params={"name": tool_name, "arguments": arguments},
                    )
                except (httpx.HTTPError, OSError, TimeoutError, TypeError, ValueError) as exc:
                    error = sanitize_text(str(exc) or type(exc).__name__, secrets)
                    calls.append(McpCallRecord(tool=tool_name, ok=False, summary_text=error))
                    research_gaps.append(
                        ResearchGap(code="tool_error", provider="sif", tool=tool_name)
                    )
                    continue
                if "error" in payload:
                    error = sanitize_text(str(payload.get("error")), secrets)
                    calls.append(McpCallRecord(tool=tool_name, ok=False, summary_text=error))
                    research_gaps.append(
                        ResearchGap(code="tool_error", provider="sif", tool=tool_name)
                    )
                    continue
                result = payload.get("result")
                if not isinstance(result, dict):
                    calls.append(
                        McpCallRecord(
                            tool=tool_name,
                            ok=False,
                            summary_text="malformed tool result",
                        )
                    )
                    research_gaps.append(
                        ResearchGap(
                            code="payload_malformed",
                            provider="sif",
                            tool=tool_name,
                        )
                    )
                    continue
                result_text = _result_text(result)
                summary = sanitize_text(result_text, secrets) or "(empty result)"
                structured = result.get("structuredContent")
                source: object = structured if structured is not None else result_text
                if isinstance(source, str):
                    try:
                        nested = json.loads(source)
                    except json.JSONDecodeError:
                        nested = source
                    else:
                        source = nested
                if isinstance(source, dict):
                    source = _compact_sif_payload(source)
                sanitized = sanitize_mcp_payload(source, secrets)
                if sanitized.limit_code is not None:
                    calls.append(
                        McpCallRecord(tool=tool_name, ok=False, summary_text=summary)
                    )
                    research_gaps.append(
                        ResearchGap(
                            code=sanitized.limit_code,
                            provider="sif",
                            tool=tool_name,
                        )
                    )
                    continue
                payload_json = (
                    sanitized.value
                    if isinstance(sanitized.value, str)
                    else json.dumps(
                        sanitized.value,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                normalization = normalize_tool_payload(
                    provider="sif",
                    tool=tool_name,
                    output_schema_json="",
                    payload_json=payload_json,
                )
                calls.append(McpCallRecord(tool=tool_name, ok=True, summary_text=summary))
                research_items.extend(normalization.items)
                research_gaps.extend(normalization.gaps)
    except (httpx.HTTPError, OSError, TimeoutError, TypeError, ValueError) as exc:
        error = sanitize_text(str(exc) or type(exc).__name__, secrets)
        return McpToolSnapshot(
            provider="sif",
            status="error",
            tool_count=0,
            tools_sample=[],
            calls=calls,
            error=error or "provider unavailable",
            research_gaps=(ResearchGap(code="provider_error", provider="sif"),),
        )
    return McpToolSnapshot(
        provider="sif",
        status="ok",
        tool_count=len(targets),
        tools_sample=list(targets),
        calls=calls,
        error=None,
        research_items=tuple(research_items),
        research_gaps=tuple(research_gaps),
    )


__all__ = ["research_sif_endpoint"]
