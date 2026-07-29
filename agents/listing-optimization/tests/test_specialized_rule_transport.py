from __future__ import annotations

from typing import TYPE_CHECKING

import amazon_copy.specialized_rules.client as client_module
import anyio
import httpx
import pytest
from amazon_copy.config import Settings
from amazon_copy.specialized_rules.catalog import Marketplace, RuleProfile
from amazon_copy.specialized_rules.client import (
    SpecializedRuleRequest,
    fetch_specialized_rules,
)
from amazon_copy.specialized_rules.routing import RuleRoute
from mcp.types import ListResourcesResult, ReadResourceResult, Resource, TextResourceContents
from pydantic import AnyUrl
from typing_extensions import override

if TYPE_CHECKING:
    from types import TracebackType
    from typing import ClassVar, Self

    from mcp.types import BlobResourceContents


class TransportState:
    def __init__(self, filename: str, *, secret: str) -> None:
        self.filename: str = filename
        self.secret: str = secret
        self.http_headers: dict[str, str] = {}
        self.endpoint_url: str = ""
        self.http_closed: bool = False
        self.streams_closed: bool = False
        self.session_closed: bool = False
        self.initialized: bool = False
        self.list_calls: int = 0
        self.read_calls: int = 0


class FakeHttpClient:
    state: ClassVar[TransportState]

    def __init__(
        self,
        *,
        headers: dict[str, str],
        transport: httpx.AsyncHTTPTransport,
        timeout: httpx.Timeout,
        follow_redirects: bool,
        trust_env: bool,
        **_kwargs: object,
    ) -> None:
        del transport, timeout, follow_redirects, trust_env
        self.state.http_headers = headers

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.state.http_closed = True


class FakeStreamsContext:
    state: ClassVar[TransportState]

    async def __aenter__(self) -> tuple[str, str, None]:
        return ("reader", "writer", None)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.state.streams_closed = True


class FakeClientSession:
    state: ClassVar[TransportState]

    def __init__(self, reader: str, writer: str) -> None:
        del reader, writer

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.state.session_closed = True

    async def initialize(self) -> None:
        self.state.initialized = True

    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        del cursor
        self.state.list_calls += 1
        uri = AnyUrl(f"rules://listing-optimize/{self.state.filename}")
        return ListResourcesResult(
            resources=[
                Resource(
                    name=self.state.filename,
                    uri=uri,
                    mimeType="text/markdown",
                )
            ]
        )

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult:
        self.state.read_calls += 1
        contents: list[TextResourceContents | BlobResourceContents] = [
            TextResourceContents(
                uri=uri,
                mimeType="text/markdown",
                text=f"# Rule\nAuthorization: Bearer {self.state.secret}",
            )
        ]
        return ReadResourceResult(contents=contents)


class HangingClientSession(FakeClientSession):
    @override
    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        del cursor
        self.state.list_calls += 1
        await anyio.sleep_forever()
        raise AssertionError


def _request(filename: str) -> SpecializedRuleRequest:
    profile = RuleProfile(
        filename=filename,
        marketplaces=(Marketplace.US,),
        product_types=("SIGN_DISPLAY_STAND",),
        kind="product",
    )
    return SpecializedRuleRequest(
        source_fingerprint="source-fingerprint",
        route=RuleRoute(
            marketplace=Marketplace.US,
            product_type="SIGN_DISPLAY_STAND",
            profiles=(profile,),
            fingerprint="route-fingerprint",
        ),
    )


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    state: TransportState,
    session_type: type[FakeClientSession] = FakeClientSession,
) -> None:
    FakeHttpClient.state = state
    FakeStreamsContext.state = state
    session_type.state = state

    def open_streams(url: str, *, http_client: FakeHttpClient) -> FakeStreamsContext:
        del http_client
        state.endpoint_url = url
        return FakeStreamsContext()

    monkeypatch.setattr(client_module, "httpx", httpx, raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(client_module, "streamable_http_client", open_streams, raising=False)
    monkeypatch.setattr(client_module, "ClientSession", session_type, raising=False)


@pytest.mark.asyncio
async def test_streamable_http_transport_uses_https_bearer_and_closes_every_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one configured HTTPS endpoint and an in-process MCP Resources session.
    filename = "us-adjustable-wedding-sign-stands.md"
    bearer_sentinel = "transport-secret-sentinel"
    state = TransportState(filename, secret=bearer_sentinel)
    _install_transport(monkeypatch, state)
    settings = Settings.model_validate(
        {
            "LISTING_OPTIMIZE_MCP_URL": "https://rules.example.test/mcp",
            "LISTING_OPTIMIZE_MCP_TOKEN": bearer_sentinel,
        }
    )

    # When: the standard Streamable HTTP session discovers and reads the profile.
    outcome = await fetch_specialized_rules(settings, _request(filename))

    # Then: Bearer auth stays transport-only and all context layers close.
    assert state.endpoint_url == "https://rules.example.test/mcp"
    assert state.http_headers == {"Authorization": f"Bearer {bearer_sentinel}"}
    assert state.initialized is True
    assert (state.list_calls, state.read_calls) == (1, 1)
    assert (state.session_closed, state.streams_closed, state.http_closed) == (
        True,
        True,
        True,
    )
    assert outcome.cache.all_requested_loaded is True
    assert bearer_sentinel not in outcome.model_dump_json()


@pytest.mark.asyncio
async def test_hung_streamable_http_session_times_out_and_still_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an authenticated MCP session that hangs during resource discovery.
    filename = "us-adjustable-wedding-sign-stands.md"
    bearer_sentinel = "hung-secret-sentinel"
    state = TransportState(filename, secret=bearer_sentinel)
    _install_transport(monkeypatch, state, HangingClientSession)
    settings = Settings.model_validate(
        {
            "LISTING_OPTIMIZE_MCP_URL": "https://rules.example.test/mcp",
            "LISTING_OPTIMIZE_MCP_TOKEN": bearer_sentinel,
            "LISTING_OPTIMIZE_MCP_TIMEOUT_SECONDS": 0.01,
        }
    )

    # When: the provider exceeds the hard timeout.
    outcome = await fetch_specialized_rules(settings, _request(filename))

    # Then: cleanup completes and only a redacted timeout gap survives.
    assert [gap.code for gap in outcome.cache.gaps] == ["provider_timeout"]
    assert (state.session_closed, state.streams_closed, state.http_closed) == (
        True,
        True,
        True,
    )
    assert bearer_sentinel not in outcome.model_dump_json()


@pytest.mark.asyncio
async def test_unconfigured_transport_returns_gap_without_opening_a_session() -> None:
    # Given: no listing-optimize endpoint or Bearer token.
    settings = Settings.model_validate({})
    request = _request("us-adjustable-wedding-sign-stands.md")

    # When: the Resources transport is requested.
    outcome = await fetch_specialized_rules(settings, request)

    # Then: configuration absence is visible and never claimed as a loaded profile.
    assert [gap.code for gap in outcome.cache.gaps] == ["endpoint_unconfigured"]
    assert outcome.cache.snapshots == ()
    assert outcome.cache.all_requested_loaded is False
