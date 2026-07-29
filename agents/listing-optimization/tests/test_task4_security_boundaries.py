from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast, final
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpx
import pytest
from amazon_copy.config import Settings
from amazon_copy.exporters import export_studio_report
from amazon_copy.mcp.live_research import McpToolSnapshot, research_endpoint
from amazon_copy.mcp.live_research_session import snapshot_to_dict
from amazon_copy.mcp.remote_http import RemoteMcpEndpoint, probe_remote_mcp
from amazon_copy.mcp.security import sanitize_mcp_url
from amazon_copy.schemas import simple_listing
from amazon_copy.schemas.simple_listing import CopyPointsParseError, parse_listing_block
from amazon_copy.schemas.studio_input import StudioInputParseError, parse_studio_request
from amazon_copy.schemas.studio_output import (
    AuditMetadata,
    BulletOption,
    OptimizationReport,
    SuccessOutcome,
    TitleOption,
)
from amazon_copy.specialized_rules.catalog import Marketplace, RuleProfile
from amazon_copy.specialized_rules.client import (
    ReadOnlyRuleResourcesClient,
    RuleReadPolicy,
    SpecializedRuleRequest,
)
from amazon_copy.specialized_rules.routing import RuleRoute
from mcp.types import ListResourcesResult, ReadResourceResult, Resource
from pydantic import AnyUrl, SecretStr
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
    from pathlib import Path
    from types import SimpleNamespace


@final
class _RecordingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks
        self.chunks_yielded = 0
        self.closed = False

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.chunks_yielded += 1
            yield chunk

    @override
    async def aclose(self) -> None:
        self.closed = True


class _FakeToolsResult:
    tools: list[SimpleNamespace]

    def __init__(self) -> None:
        self.tools = []


@pytest.mark.asyncio
async def test_live_mcp_stream_guard_cancels_before_oversized_tail_is_materialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a normal MCP session plus an HTTP stream with a large unconsumed tail.
    original_client = httpx.AsyncClient
    captured_hooks: list[Callable[[httpx.Response], Awaitable[None]]] = []

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        event_hooks = kwargs.get("event_hooks")
        assert isinstance(event_hooks, dict)
        hook_mapping = cast("dict[str, object]", event_hooks)
        hooks = hook_mapping.get("response")
        assert isinstance(hooks, list)
        captured_hooks.extend(cast("list[Callable[[httpx.Response], Awaitable[None]]]", hooks))
        transport = httpx.MockTransport(lambda _request: httpx.Response(204))
        return original_client(transport=transport)

    session = AsyncMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=_FakeToolsResult())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    streams_cm = AsyncMock()
    streams_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), lambda: None))
    streams_cm.__aexit__ = AsyncMock(return_value=None)
    endpoint = RemoteMcpEndpoint(name="fixture", url="https://example.test/mcp")

    # When: research creates its HTTP client and the captured guard reads the fake stream.
    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with (
        patch("amazon_copy.mcp.live_research.streamable_http_client", return_value=streams_cm),
        patch("amazon_copy.mcp.live_research.ClientSession", return_value=session),
    ):
        _ = await research_endpoint(endpoint, query="usb hub")
    assert len(captured_hooks) == 1
    stream = _RecordingStream((b"x" * 16_000,) * 12)
    response = httpx.Response(200, stream=stream)
    await captured_hooks[0](response)

    # Then: the guard closes early and never yields the remaining transport chunks.
    with pytest.raises(httpx.TransportError):
        _ = await response.aread()
    assert stream.closed is True
    assert stream.chunks_yielded < 12


@pytest.mark.asyncio
async def test_remote_probe_whole_operation_timeout_cancels_hung_open() -> None:
    # Given: an MCP connection context that never finishes opening.
    cancelled = anyio.Event()

    async def hang_forever() -> None:
        try:
            await anyio.sleep_forever()
        finally:
            cancelled.set()

    streams_cm = AsyncMock()
    streams_cm.__aenter__ = AsyncMock(side_effect=hang_forever)
    streams_cm.__aexit__ = AsyncMock(return_value=None)
    endpoint = RemoteMcpEndpoint(name="fixture", url="https://example.test/mcp")

    # When: the whole-probe deadline expires.
    with patch(
        "amazon_copy.mcp.remote_http.streamable_http_client",
        return_value=streams_cm,
    ):
        result = await probe_remote_mcp(endpoint, timeout_s=0.01)

    # Then: cancellation is observed and a stable error code is returned.
    assert cancelled.is_set()
    assert result["ok"] is False
    assert result["error_code"] == "operation_timeout"


@final
class _ResourceSession:
    def __init__(self, pages: dict[str | None, ListResourcesResult]) -> None:
        self.pages = pages
        self.list_calls: list[str | None] = []
        self.read_calls: list[str] = []

    async def list_resources(self, cursor: str | None = None) -> ListResourcesResult:
        self.list_calls.append(cursor)
        return self.pages[cursor]

    async def read_resource(self, uri: AnyUrl) -> ReadResourceResult:
        self.read_calls.append(str(uri))
        message = "oversized discovery must not read resources"
        raise AssertionError(message)


def _resource(index: int) -> Resource:
    return Resource(
        name=f"unrequested-{index}.md",
        uri=AnyUrl(f"rules://listing-optimize/unrequested-{index}.md"),
        mimeType="text/markdown",
    )


def _rule_request() -> SpecializedRuleRequest:
    filename = "us-adjustable-wedding-sign-stands.md"
    profile = RuleProfile(
        filename=filename,
        marketplaces=(Marketplace.US,),
        product_types=("TEST_PRODUCT",),
        kind="product",
    )
    return SpecializedRuleRequest(
        source_fingerprint="source-a",
        route=RuleRoute(
            marketplace=Marketplace.US,
            product_type="TEST_PRODUCT",
            profiles=(profile,),
            fingerprint="route-a",
        ),
    )


@pytest.mark.asyncio
async def test_resource_discovery_rejects_oversized_page_without_iterating_tail() -> None:
    # Given: one fully materialized page beyond the fixed per-page item budget.
    session = _ResourceSession(
        {None: ListResourcesResult(resources=[_resource(index) for index in range(300)])}
    )
    client = ReadOnlyRuleResourcesClient(
        session=session,
        policy=RuleReadPolicy(bearer_secret=SecretStr("secret")),
    )

    # When: discovery evaluates the page boundary.
    result = await client.load(_rule_request())

    # Then: it degrades before reads or additional pages.
    assert session.list_calls == [None]
    assert session.read_calls == []
    assert {gap.code for gap in result.cache.gaps} == {"resource_too_large"}


@pytest.mark.asyncio
async def test_resource_discovery_rejects_aggregate_item_overflow_across_pages() -> None:
    # Given: individually valid pages whose aggregate crosses the fixed item budget.
    session = _ResourceSession(
        {
            None: ListResourcesResult(
                resources=[_resource(index) for index in range(100)],
                nextCursor="page-2",
            ),
            "page-2": ListResourcesResult(
                resources=[_resource(index) for index in range(100, 200)],
                nextCursor="page-3",
            ),
            "page-3": ListResourcesResult(
                resources=[_resource(index) for index in range(200, 300)]
            ),
        }
    )
    client = ReadOnlyRuleResourcesClient(
        session=session,
        policy=RuleReadPolicy(bearer_secret=SecretStr("secret")),
    )

    # When: the third page would push discovery above its operation ceiling.
    result = await client.load(_rule_request())

    # Then: discovery stops without resource reads and returns one typed gap.
    assert session.list_calls == [None, "page-2", "page-3"]
    assert session.read_calls == []
    assert {gap.code for gap in result.cache.gaps} == {"resource_too_large"}


def test_listing_total_and_field_limits_reject_before_parsing_materialization() -> None:
    # Given: exactly-at-limit, one-over-limit, and one oversized title.
    byte_limit = getattr(simple_listing, "MAX_LISTING_INPUT_BYTES", 64_000)
    exact = "x" * byte_limit
    oversized = f"{exact}x"
    oversized_title = f"{'t' * 5000}\n- safe bullet"

    # When/Then: the exact raw boundary is accepted by the pre-split helper.
    listing, _facts = simple_listing.split_verified_facts_from_listing(exact)
    assert listing == exact
    with pytest.raises(CopyPointsParseError):
        _ = simple_listing.split_verified_facts_from_listing(oversized)
    with pytest.raises(CopyPointsParseError):
        _ = parse_listing_block(oversized_title)


def test_studio_request_rejects_oversized_header_block() -> None:
    # Given: a valid ASIN plus a one-megabyte seller field before a valid listing.
    raw = f"ASIN: B0ABCDEFGH\nBrand: {'x' * 1_000_000}\nSafe title\n- Safe bullet"

    # When/Then: the one-box boundary rejects before hashing or downstream calls.
    with pytest.raises(StudioInputParseError):
        _ = parse_studio_request(raw)


def test_url_userinfo_query_and_malformed_netloc_credentials_are_redacted() -> None:
    # Given: credentials in URL userinfo/query and a malformed authority.
    normal = "https://alice:USERINFO_SECRET@example.test/mcp?token=QUERY_SECRET&q=usb"
    malformed = "https://bob:MALFORMED_SECRET@[::1/mcp?password=QUERY_SECRET"

    # When: the central URL boundary serializes them.
    rendered = f"{sanitize_mcp_url(normal)}\n{sanitize_mcp_url(malformed)}"

    # Then: no credential value survives either shape.
    assert "USERINFO_SECRET" not in rendered
    assert "MALFORMED_SECRET" not in rendered
    assert "QUERY_SECRET" not in rendered
    assert "q=usb" in rendered


def test_session_snapshot_drops_private_provider_urls() -> None:
    # Given: a provider error containing a non-credential internal URL.
    snapshot = McpToolSnapshot(
        provider="fixture",
        status="error",
        tool_count=0,
        error="connect failed at https://private-rule.internal.example/mcp",
    )

    # When: it crosses session serialization.
    serialized = json.dumps(snapshot_to_dict(snapshot), ensure_ascii=False)

    # Then: internal host and path information are absent.
    assert "private-rule.internal.example" not in serialized


def _credential_report(secret_text: str) -> SuccessOutcome:
    report = OptimizationReport.model_construct(
        title_options=tuple(TitleOption(text=f"Title {index}") for index in range(3)),
        bullets=tuple(BulletOption(text=f"Benefit {index}") for index in range(5)),
        description="Clean description",
        search_terms="clean terms",
        analysis=secret_text,
        evidence_gaps=(),
        keyword_allocation=(),
        compliance_notes=(),
        return_risk_notes=(),
        citations=(),
        audit=AuditMetadata(run_id="run-1", request_hash="a" * 64),
    )
    return SuccessOutcome(report=report)


def test_exports_remove_all_supported_credential_classes(tmp_path: Path) -> None:
    # Given: every supported credential form embedded in seller-visible prose.
    secrets = (
        "USERINFO_EXPORT_SECRET",
        "QUERY_EXPORT_SECRET",
        "DIGEST_EXPORT_SECRET",
        "COOKIE_EXPORT_SECRET",
        "API_EXPORT_SECRET",
        "TOKEN_EXPORT_SECRET",
        "PEM_EXPORT_SECRET",
    )
    export_fixture = (
        "https://alice:USERINFO_EXPORT_SECRET@example.test/mcp?token=QUERY_EXPORT_SECRET\n"
        'Authorization: Digest username="seller", response="DIGEST_EXPORT_SECRET"\n'
        "Cookie: sid=COOKIE_EXPORT_SECRET\n"
        "X-API-Key: API_EXPORT_SECRET\n"
        "access_token=TOKEN_EXPORT_SECRET\n"
        "-----BEGIN PRIVATE KEY-----\nPEM_EXPORT_SECRET\n-----END PRIVATE KEY-----"
    )

    # When: the real export surface writes all four artifacts.
    paths = export_studio_report(_credential_report(export_fixture), tmp_path)
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in paths.values())

    # Then: no credential-bearing URL/header/assignment/PEM value survives.
    assert all(secret not in rendered for secret in secrets)


def test_security_limits_are_present_and_upper_bounded_in_settings() -> None:
    # Given/When: default server settings are parsed.
    settings = Settings(MOCK=True)

    # Then: transport/resource limits are explicit and finite.
    assert 1 <= settings.remote_mcp_timeout_seconds <= 30
    assert 1 <= settings.listing_optimize_mcp_max_resources_per_page <= 256
    assert (
        settings.listing_optimize_mcp_max_resources_per_page
        <= settings.listing_optimize_mcp_max_total_resources
        <= 512
    )
