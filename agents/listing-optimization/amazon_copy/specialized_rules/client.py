"""Read-only MCP Resources client for specialized listing rules."""

from __future__ import annotations

import socket
from typing import Protocol
from urllib.parse import parse_qsl, urlsplit

import anyio
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from mcp.types import ListResourcesResult, PaginatedRequestParams, ReadResourceResult
from pydantic import AnyUrl, SecretStr

from amazon_copy.mcp.response_limits import McpResponseBudget
from amazon_copy.mcp.security import is_secret_key
from amazon_copy.specialized_rules.models import (
    SpecializedRuleCache,
    SpecializedRuleLoad,
)
from amazon_copy.specialized_rules.resource_loader import (
    ReadOnlyRuleResourcesClient,
    RuleReadPolicy,
    SpecializedRuleRequest,
)
from mcp import ClientSession

_LIMITS = httpx.Limits(
    max_connections=200,
    max_keepalive_connections=40,
    keepalive_expiry=30.0,
)
_SOCKET_OPTIONS = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]


class SpecializedRuleSettings(Protocol):
    """Settings fields required by the listing-optimize Resources transport."""

    listing_optimize_mcp_url: str
    listing_optimize_mcp_token: SecretStr
    listing_optimize_mcp_timeout_seconds: float
    listing_optimize_mcp_max_resource_bytes: int
    listing_optimize_mcp_max_pages: int
    listing_optimize_mcp_max_resources_per_page: int
    listing_optimize_mcp_max_total_resources: int


class _McpResourcesSession:
    def __init__(self, session: ClientSession) -> None:
        self._session: ClientSession = session

    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        if cursor is None:
            return await self._session.list_resources()
        return await self._session.list_resources(params=PaginatedRequestParams(cursor=cursor))

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult:
        return await self._session.read_resource(uri)


def _endpoint_is_safe(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    credential_query = any(
        is_secret_key(key) for key, _value in parse_qsl(parts.query, keep_blank_values=True)
    )
    return (
        parts.scheme.casefold() == "https"
        and parts.hostname is not None
        and parts.username is None
        and parts.password is None
        and port in {None, 443}
        and not parts.fragment
        and not credential_query
    )


def _cached_load(
    request: SpecializedRuleRequest,
    cached: SpecializedRuleCache | None,
) -> SpecializedRuleLoad | None:
    requested = tuple(dict.fromkeys(profile.filename for profile in request.route.profiles))
    if (
        cached is not None
        and cached.source_fingerprint == request.source_fingerprint
        and cached.route_fingerprint == request.route.fingerprint
        and cached.requested_profiles == requested
    ):
        return SpecializedRuleLoad(cache=cached, reused=True)
    return None


async def fetch_specialized_rules(
    settings: SpecializedRuleSettings,
    request: SpecializedRuleRequest,
    cached: SpecializedRuleCache | None = None,
) -> SpecializedRuleLoad:
    """Load specialized rules via remote MCP Resources when configured.

    Prefer :func:`fetch_specialized_rules_sync` for the automatic workflow: it
    falls back to the packaged local agent node when the remote endpoint is unset.
    """
    reused = _cached_load(request, cached)
    if reused is not None:
        return reused
    endpoint = settings.listing_optimize_mcp_url.strip()
    secret = settings.listing_optimize_mcp_token.get_secret_value()
    if not endpoint or not secret:
        return ReadOnlyRuleResourcesClient.failure(request, "endpoint_unconfigured")
    if not _endpoint_is_safe(endpoint):
        return ReadOnlyRuleResourcesClient.failure(request, "unsafe_endpoint")
    policy = RuleReadPolicy(
        bearer_secret=SecretStr(secret),
        max_resource_bytes=settings.listing_optimize_mcp_max_resource_bytes,
        max_pages=settings.listing_optimize_mcp_max_pages,
        max_resources_per_page=settings.listing_optimize_mcp_max_resources_per_page,
        max_total_resources=settings.listing_optimize_mcp_max_total_resources,
        timeout_seconds=settings.listing_optimize_mcp_timeout_seconds,
    )
    response_budget = McpResponseBudget()
    transport = httpx.AsyncHTTPTransport(
        retries=3,
        limits=_LIMITS,
        socket_options=_SOCKET_OPTIONS,
    )
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.listing_optimize_mcp_timeout_seconds,
        write=10.0,
        pool=10.0,
    )

    async def _run() -> SpecializedRuleLoad:
        async with (
            httpx.AsyncClient(
                headers={"Authorization": f"Bearer {secret}"},
                transport=transport,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                event_hooks={"response": [response_budget.guard_response]},
            ) as http_client,
            streamable_http_client(endpoint, http_client=http_client) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            _ = await session.initialize()
            client = ReadOnlyRuleResourcesClient(
                session=_McpResourcesSession(session),
                policy=policy,
            )
            return await client.load(request)

    try:
        with anyio.fail_after(settings.listing_optimize_mcp_timeout_seconds):
            return await _run()
    except TimeoutError:
        return ReadOnlyRuleResourcesClient.failure(request, "provider_timeout")
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
        return ReadOnlyRuleResourcesClient.failure(request, "provider_error")


def fetch_specialized_rules_sync(
    settings: SpecializedRuleSettings,
    *,
    request: SpecializedRuleRequest,
    cached: SpecializedRuleCache | None = None,
) -> SpecializedRuleLoad:
    """Load specialized rules for the automatic workflow.

    Default agent node: read allowlisted profiles from installed package data.
    Optional remote override: when both URL and bearer token are configured,
    load through the authenticated Streamable HTTP Resources client instead.
    """
    reused = _cached_load(request, cached)
    if reused is not None:
        return reused
    endpoint = settings.listing_optimize_mcp_url.strip()
    secret = settings.listing_optimize_mcp_token.get_secret_value()
    if not endpoint or not secret:
        from amazon_copy.specialized_rules.local_loader import fetch_specialized_rules_local

        return fetch_specialized_rules_local(settings, request=request, cached=cached)

    async def _run() -> SpecializedRuleLoad:
        return await fetch_specialized_rules(settings, request, cached)

    return anyio.run(_run)


__all__ = [
    "ReadOnlyRuleResourcesClient",
    "RuleReadPolicy",
    "SpecializedRuleRequest",
    "SpecializedRuleSettings",
    "fetch_specialized_rules",
    "fetch_specialized_rules_sync",
]
