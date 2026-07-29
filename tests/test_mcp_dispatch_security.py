from __future__ import annotations

from types import SimpleNamespace
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from amazon_copy.config import Settings
from amazon_copy.mcp.live_research import (
    pick_research_tools,
    research_endpoint,
    snapshots_from_session,
)
from amazon_copy.mcp.remote_http import (
    RemoteMcpEndpoint,
    UnsafeMcpEndpointError,
    build_sellersprite_endpoint,
    build_sif_endpoint,
    build_sorftime_endpoint,
    endpoints_from_settings,
)
from pydantic import SecretStr


class _EndpointBuilder(Protocol):
    def __call__(self, *, key: str, base_url: str) -> RemoteMcpEndpoint: ...


def _streams_context() -> AsyncMock:
    context = AsyncMock()
    context.__aenter__ = AsyncMock(
        return_value=(MagicMock(), MagicMock(), lambda: None)
    )
    context.__aexit__ = AsyncMock(return_value=None)
    return context


def _session_with_tools(tools: list[SimpleNamespace]) -> tuple[AsyncMock, AsyncMock]:
    session = AsyncMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=tools))
    call_tool = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(text="result")],
            structuredContent={"keyword": "usb c hub"},
        )
    )
    session.call_tool = call_tool
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session, call_tool


def _tool(name: str, input_schema: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        inputSchema=input_schema,
        outputSchema={
            "type": "object",
            "properties": {"keyword": {"type": "string"}},
        },
    )


class TestReviewedToolDispatch:
    def test_only_exact_provider_allowlist_names_are_selected(self) -> None:
        # Given: lookalike, mutating, and one exact reviewed SellerSprite tool
        names = [
            "delete_account",
            "keyword_miner_delete",
            "Keyword_Miner",
            "keyword_miner",
        ]

        # When: the research dispatcher selects callable tools
        selected = pick_research_tools("sellersprite", names)

        # Then: only the exact reviewed name is eligible
        assert selected == ["keyword_miner"]

    def test_unknown_provider_has_no_callable_tools(self) -> None:
        # Given: an unreviewed provider advertising a familiar name
        names = ["keyword_miner", "product_research"]

        # When/Then: provider identity prevents dispatch
        assert pick_research_tools("unreviewed-provider", names) == []

    @pytest.mark.asyncio
    async def test_unknown_only_tools_are_skipped_without_dispatch(self) -> None:
        # Given: a known provider advertising only a mutating tool
        endpoint = RemoteMcpEndpoint(
            name="sellersprite",
            url="https://mcp.sellersprite.com/mcp",
            headers={"secret-key": "credential-value"},
        )
        session, call_tool = _session_with_tools(
            [_tool("delete_account", {"type": "object"})]
        )

        # When: the endpoint is researched
        with (
            patch(
                "amazon_copy.mcp.live_research.streamable_http_client",
                return_value=_streams_context(),
            ),
            patch("amazon_copy.mcp.live_research.ClientSession", return_value=session),
        ):
            snapshot = await research_endpoint(endpoint, query="usb c hub")

        # Then: no side effect occurs and the skipped boundary is explicit
        call_tool.assert_not_called()
        assert snapshot.status == "skipped"
        assert {gap.code for gap in snapshot.research_gaps} == {"tool_not_allowlisted"}

    @pytest.mark.asyncio
    async def test_declared_input_schema_drives_one_dispatch(self) -> None:
        # Given: a reviewed tool declaring query and marketplace fields
        endpoint = RemoteMcpEndpoint(
            name="sellersprite",
            url="https://mcp.sellersprite.com/mcp",
        )
        tool = _tool(
            "keyword_miner",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "marketplace": {"type": "string"},
                },
                "required": ["query"],
            },
        )
        session, call_tool = _session_with_tools([tool])

        # When: the reviewed tool is called
        with (
            patch(
                "amazon_copy.mcp.live_research.streamable_http_client",
                return_value=_streams_context(),
            ),
            patch("amazon_copy.mcp.live_research.ClientSession", return_value=session),
        ):
            snapshot = await research_endpoint(endpoint, query="usb c hub")

        # Then: schema-derived arguments are dispatched once, without probing templates
        call_tool.assert_awaited_once_with(
            "keyword_miner",
            arguments={"query": "usb c hub", "marketplace": "US"},
        )
        assert snapshot.calls[0]["ok"] is True

    @pytest.mark.asyncio
    async def test_unsupported_required_input_never_dispatches(self) -> None:
        # Given: a reviewed tool requiring an account mutation identifier
        endpoint = RemoteMcpEndpoint(
            name="sellersprite",
            url="https://mcp.sellersprite.com/mcp",
        )
        session, call_tool = _session_with_tools(
            [
                _tool(
                    "keyword_miner",
                    {
                        "type": "object",
                        "properties": {"account_id": {"type": "string"}},
                        "required": ["account_id"],
                    },
                )
            ]
        )

        # When: research encounters the unsupported schema
        with (
            patch(
                "amazon_copy.mcp.live_research.streamable_http_client",
                return_value=_streams_context(),
            ),
            patch("amazon_copy.mcp.live_research.ClientSession", return_value=session),
        ):
            snapshot = await research_endpoint(endpoint, query="usb c hub")

        # Then: validation stops dispatch and records the boundary gap
        call_tool.assert_not_called()
        assert {gap.code for gap in snapshot.research_gaps} == {
            "input_schema_unsupported"
        }


class TestConfiguredEndpointTrust:
    @pytest.mark.parametrize(
        ("seller_url", "sorftime_url"),
        [
            ("http://mcp.sellersprite.com/mcp", "http://mcp.sorftime.com"),
            (
                "https://mcp.sellersprite.com.evil.test/mcp",
                "https://mcp.sorftime.com.evil.test",
            ),
        ],
    )
    def test_untrusted_configured_hosts_receive_no_credentials(
        self,
        seller_url: str,
        sorftime_url: str,
    ) -> None:
        # Given: keys paired with non-HTTPS or lookalike configured endpoints
        settings = Settings(
            SELLERSPRITE_MCP_KEY=SecretStr("seller-credential"),
            SORFTIME_MCP_KEY=SecretStr("sorftime-credential"),
            SIF_MCP_KEY=SecretStr(""),
            SELLERSPRITE_MCP_URL=seller_url,
            SORFTIME_MCP_URL=sorftime_url,
        )

        # When/Then: no credential-bearing endpoint can be constructed
        assert endpoints_from_settings(settings) == []

    @pytest.mark.parametrize(
        ("builder", "url"),
        [
            (build_sellersprite_endpoint, "https://attacker.test/mcp"),
            (build_sorftime_endpoint, "https://attacker.test/mcp"),
            (build_sif_endpoint, "https://attacker.test/mcp"),
        ],
    )
    def test_builtin_builder_rejects_arbitrary_host(
        self,
        builder: _EndpointBuilder,
        url: str,
    ) -> None:
        # Given/When/Then: built-in helpers cannot attach keys to arbitrary hosts
        with pytest.raises(UnsafeMcpEndpointError):
            _ = builder(key="credential", base_url=url)

    def test_explicit_endpoint_still_allows_local_transport_injection(self) -> None:
        # Given/When: tests explicitly construct their own local endpoint
        endpoint = RemoteMcpEndpoint(name="fixture", url="http://127.0.0.1:8765/mcp")

        # Then: configuration validation does not affect explicit injection
        assert endpoint.url == "http://127.0.0.1:8765/mcp"


class TestMalformedSessionSnapshot:
    def test_non_numeric_tool_count_defaults_without_raising(self) -> None:
        # Given: tampered session data with a malformed integer
        raw = [{"provider": "sellersprite", "status": "ok", "tool_count": "not-an-int"}]

        # When: the session boundary restores snapshots
        snapshots = snapshots_from_session(raw)

        # Then: the value is discarded and a gap records malformed input
        assert snapshots[0].tool_count == 0
        assert {gap.code for gap in snapshots[0].research_gaps} == {
            "payload_malformed"
        }
