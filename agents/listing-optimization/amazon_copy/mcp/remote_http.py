"""Streamable-HTTP remote MCP probe (SellerSprite, Sorftime, etc.).

Connects via the official MCP Python SDK ``streamablehttp_client`` +
``ClientSession``. Never logs full secrets; redacts keys from error text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal, Protocol, TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import anyio
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from typing_extensions import TypedDict

from amazon_copy.mcp.response_limits import McpResponseBudget
from amazon_copy.mcp.security import (
    MAX_MCP_PAYLOAD_ITEMS,
    REDACTED,
    is_secret_key,
    sanitize_mcp_session_text,
    sanitize_mcp_text,
    sanitize_mcp_url,
)
from mcp import ClientSession

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import SecretStr

_DEFAULT_TOOL_SAMPLE: Final[int] = 15
_REMOTE_MCP_TIMEOUT_S: Final[float] = 25.0
_BuiltinProvider: TypeAlias = Literal[
    "sellersprite",
    "sorftime",
    "sif",
]
_EXPECTED_HOST: Final[dict[_BuiltinProvider, str]] = {
    "sellersprite": "mcp.sellersprite.com",
    "sorftime": "mcp.sorftime.com",
    "sif": "mcp.sif.com",
}


class McpEndpointSettings(Protocol):
    """Configuration fields required to build trusted provider endpoints."""

    sellersprite_mcp_key: SecretStr
    sorftime_mcp_key: SecretStr
    sif_mcp_key: SecretStr
    sellersprite_mcp_url: str
    sorftime_mcp_url: str
    sif_mcp_url: str
    remote_mcp_timeout_seconds: float


class RemoteProbeSummary(TypedDict):
    """Redacted probe result suitable for logs and evidence JSON."""

    name: str
    ok: bool
    tool_count: int
    tool_names: list[str]
    error_code: str | None
    error_message: str | None
    fixture: bool
    called_tool: str | None


@dataclass(frozen=True, slots=True)
class RemoteMcpEndpoint:
    """Remote MCP streamable-HTTP endpoint configuration."""

    name: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict[str, str])


def mask_secret(value: str) -> str:
    """Fully hide a credential without retaining identifying fragments."""
    _ = value
    return REDACTED


def redact_secrets(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Fully remove known secrets and credential patterns from text."""
    return sanitize_mcp_text(text, secrets)


def redact_url(url: str) -> str:
    """Fully redact credential query params from a URL."""
    return sanitize_mcp_url(url)


class UnsafeMcpEndpointError(ValueError):
    """A configured built-in endpoint did not match its trusted HTTPS host."""

    provider: _BuiltinProvider
    url: str

    def __init__(self, provider: _BuiltinProvider, url: str) -> None:
        """Record the provider and a redacted form of the rejected URL."""
        self.provider = provider
        self.url = redact_url(url)
        super().__init__(f"unsafe configured {provider} MCP endpoint: {self.url}")


def _validated_builtin_url(provider: _BuiltinProvider, url: str) -> str:
    expected_host = _EXPECTED_HOST[provider]
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeMcpEndpointError(provider, url) from exc
    trusted = (
        parts.scheme.casefold() == "https"
        and parts.hostname is not None
        and parts.hostname.casefold().rstrip(".") == expected_host
        and parts.username is None
        and parts.password is None
        and port in {None, 443}
    )
    if not trusted:
        raise UnsafeMcpEndpointError(provider, url)
    return url


def build_sellersprite_endpoint(
    *,
    key: str,
    base_url: str = "https://mcp.sellersprite.com/mcp",
) -> RemoteMcpEndpoint:
    """Build SellerSprite endpoint (``secret-key`` header)."""
    trusted_url = _validated_builtin_url("sellersprite", base_url.rstrip("?&"))
    return RemoteMcpEndpoint(
        name="sellersprite",
        url=trusted_url,
        headers={"secret-key": key},
    )


def build_sorftime_endpoint(
    *,
    key: str,
    base_url: str = "https://mcp.sorftime.com",
) -> RemoteMcpEndpoint:
    """Build Sorftime endpoint (``?key=`` query param, preferred)."""
    trusted_url = _validated_builtin_url("sorftime", base_url)
    parts = urlsplit(trusted_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["key"] = key
    url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "", urlencode(query), parts.fragment)
    )
    return RemoteMcpEndpoint(name="sorftime", url=url, headers={})


def build_sif_endpoint(
    *,
    key: str,
    base_url: str = "https://mcp.sif.com/mcp",
) -> RemoteMcpEndpoint:
    """Build SIF endpoint (``secret-key`` header, same pattern as SellerSprite)."""
    trusted_url = _validated_builtin_url("sif", base_url.rstrip("?&"))
    return RemoteMcpEndpoint(
        name="sif",
        url=trusted_url,
        headers={"secret-key": key},
    )


def endpoints_from_settings(settings: McpEndpointSettings) -> list[RemoteMcpEndpoint]:
    """Build remote endpoints for any non-empty MCP keys on *settings*.

    Expected attributes (pydantic Settings fields)::

        sellersprite_mcp_key: SecretStr
        sorftime_mcp_key: SecretStr
        sif_mcp_key: SecretStr
        sellersprite_mcp_url: str
        sorftime_mcp_url: str
        sif_mcp_url: str
    """
    endpoints: list[RemoteMcpEndpoint] = []

    ss_key = settings.sellersprite_mcp_key.get_secret_value()
    if ss_key:
        ss_url = settings.sellersprite_mcp_url
        try:
            endpoint = build_sellersprite_endpoint(
                key=ss_key,
                base_url=ss_url or "https://mcp.sellersprite.com/mcp",
            )
        except UnsafeMcpEndpointError:
            endpoint = None
        if endpoint is not None:
            endpoints.append(endpoint)

    sf_key = settings.sorftime_mcp_key.get_secret_value()
    if sf_key:
        sf_url = settings.sorftime_mcp_url
        try:
            endpoint = build_sorftime_endpoint(
                key=sf_key,
                base_url=sf_url or "https://mcp.sorftime.com",
            )
        except UnsafeMcpEndpointError:
            endpoint = None
        if endpoint is not None:
            endpoints.append(endpoint)

    sif_key = settings.sif_mcp_key.get_secret_value()
    if sif_key:
        sif_url = settings.sif_mcp_url
        try:
            endpoint = build_sif_endpoint(
                key=sif_key,
                base_url=sif_url or "https://mcp.sif.com/mcp",
            )
        except UnsafeMcpEndpointError:
            endpoint = None
        if endpoint is not None:
            endpoints.append(endpoint)

    return endpoints


def _collect_secrets(endpoint: RemoteMcpEndpoint) -> tuple[str, ...]:
    secrets = [value for value in endpoint.headers.values() if value]
    secrets.extend(
        value
        for key, value in parse_qsl(urlsplit(endpoint.url).query, keep_blank_values=True)
        if is_secret_key(key) and value
    )
    return tuple(secrets)


def _pick_safe_tool(tool_names: list[str]) -> str | None:
    """Select only an exact reviewed read-only smoke tool name."""
    preferred = (
        "ping",
        "health",
        "health_check",
        "list",
        "tools",
        "help",
        "status",
    )
    for candidate in preferred:
        if candidate in tool_names:
            return candidate
    return None


async def probe_remote_mcp(
    endpoint: RemoteMcpEndpoint,
    *,
    call_safe_tool: bool = True,
    tool_sample: int = _DEFAULT_TOOL_SAMPLE,
    timeout_s: float = _REMOTE_MCP_TIMEOUT_S,
) -> RemoteProbeSummary:
    """Initialize a remote MCP session, list tools, optionally call one safe tool.

    Returns a redacted summary with ``fixture=False``. Secrets never appear in
    ``error_message`` or tool metadata.
    """
    secrets = _collect_secrets(endpoint)
    headers = dict(endpoint.headers)
    response_budget = McpResponseBudget()

    async def _run() -> RemoteProbeSummary:
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
            tools_result = await session.list_tools()
            names = [tool.name for tool in tools_result.tools]
            sample = [
                sanitize_mcp_text(name, secrets)
                for name in names[: min(max(0, tool_sample), MAX_MCP_PAYLOAD_ITEMS)]
            ]
            if len(names) > MAX_MCP_PAYLOAD_ITEMS:
                return RemoteProbeSummary(
                    name=endpoint.name,
                    ok=False,
                    tool_count=len(names),
                    tool_names=sample,
                    error_code="payload_too_large",
                    error_message="remote MCP payload exceeded limit",
                    fixture=False,
                    called_tool=None,
                )
            called: str | None = None
            if call_safe_tool:
                safe = _pick_safe_tool(names)
                if safe is not None:
                    try:
                        _ = await session.call_tool(safe, arguments={})
                        called = safe
                    except (
                        OSError,
                        RuntimeError,
                        TimeoutError,
                        ValueError,
                        TypeError,
                    ):
                        called = None
            return RemoteProbeSummary(
                name=endpoint.name,
                ok=True,
                tool_count=len(names),
                tool_names=sample,
                error_code=None,
                error_message=None,
                fixture=False,
                called_tool=called,
            )

    try:
        with anyio.fail_after(timeout_s):
            return await _run()
    except TimeoutError:
        return RemoteProbeSummary(
            name=endpoint.name,
            ok=False,
            tool_count=0,
            tool_names=[],
            error_code="operation_timeout",
            error_message="remote MCP operation timed out",
            fixture=False,
            called_tool=None,
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
    ) as exc:
        limit_hit = response_budget.limit_hit
        code = "payload_too_large" if limit_hit else type(exc).__name__
        message = (
            "remote MCP payload exceeded limit"
            if limit_hit
            else sanitize_mcp_session_text(str(exc), secrets)
        )
        return RemoteProbeSummary(
            name=endpoint.name,
            ok=False,
            tool_count=0,
            tool_names=[],
            error_code=code,
            error_message=message or code,
            fixture=False,
            called_tool=None,
        )
