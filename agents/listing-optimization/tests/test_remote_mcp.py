"""Unit tests for remote MCP probe helpers (mocked transport, no network)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from amazon_copy.config import Settings
from amazon_copy.mcp import ResearchQuery, ResearchResult, build_fake_provider
from amazon_copy.mcp.remote_http import (
    RemoteMcpEndpoint,
    build_sellersprite_endpoint,
    build_sif_endpoint,
    build_sorftime_endpoint,
    endpoints_from_settings,
    mask_secret,
    probe_remote_mcp,
    redact_secrets,
    redact_url,
)
from pydantic import SecretStr


class TestMaskAndRedact:
    def test_mask_secret_fully_redacted(self) -> None:
        # Given: a 32-char style key
        key = "64283124d5ca414ba43940dc0239c9b7"
        # When/Then
        assert mask_secret(key) == "[REDACTED]"
        assert key not in mask_secret(key)

    def test_mask_secret_short(self) -> None:
        assert mask_secret("abc") == "[REDACTED]"

    def test_redact_secrets_replaces_known_values(self) -> None:
        sample_credential = "t0tybkheowxtzvi2suv2ulbnl3hndz09"
        text = f"auth failed for {sample_credential} in request"
        out = redact_secrets(text, (sample_credential,))
        assert sample_credential not in out
        assert "[REDACTED]" in out

    def test_redact_url_masks_key_query(self) -> None:
        sample_credential = "t0tybkheowxtzvi2suv2ulbnl3hndz09"
        url = f"https://mcp.sorftime.com?key={sample_credential}&region=us"
        out = redact_url(url)
        assert sample_credential not in out
        assert "key=[REDACTED]" in out
        assert "region=us" in out

    def test_redact_url_masks_secret_key_query(self) -> None:
        sample_credential = "64283124d5ca414ba43940dc0239c9b7"
        url = f"https://mcp.sellersprite.com/mcp?secret-key={sample_credential}"
        out = redact_url(url)
        assert sample_credential not in out
        assert "secret-key=[REDACTED]" in out


class TestEndpointBuilders:
    def test_sellersprite_uses_secret_key_header(self) -> None:
        # Given
        key = "64283124d5ca414ba43940dc0239c9b7"
        # When
        endpoint = build_sellersprite_endpoint(key=key)
        # Then
        assert endpoint.name == "sellersprite"
        assert endpoint.url == "https://mcp.sellersprite.com/mcp"
        assert endpoint.headers["secret-key"] == key
        assert key not in endpoint.url

    def test_sorftime_puts_key_in_query(self) -> None:
        key = "t0tybkheowxtzvi2suv2ulbnl3hndz09"
        endpoint = build_sorftime_endpoint(key=key)
        assert endpoint.name == "sorftime"
        assert f"key={key}" in endpoint.url
        assert endpoint.headers == {}

    def test_endpoints_from_settings_empty_keys(self) -> None:
        settings = Settings(
            SELLERSPRITE_MCP_KEY=SecretStr(""),
            SORFTIME_MCP_KEY=SecretStr(""),
            SIF_MCP_KEY=SecretStr(""),
        )
        assert endpoints_from_settings(settings) == []

    def test_endpoints_from_settings_both_keys(self) -> None:
        settings = Settings(
            SELLERSPRITE_MCP_KEY=SecretStr("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            SORFTIME_MCP_KEY=SecretStr("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
            SIF_MCP_KEY=SecretStr("cccccccccccccccccccccccccccccccc"),
            SELLERSPRITE_MCP_URL="https://mcp.sellersprite.com/mcp",
            SORFTIME_MCP_URL="https://mcp.sorftime.com",
            SIF_MCP_URL="https://mcp.sif.com/mcp",
        )
        endpoints = endpoints_from_settings(settings)
        assert len(endpoints) == 3
        assert endpoints[0].name == "sellersprite"
        assert endpoints[1].name == "sorftime"
        assert endpoints[2].name == "sif"

    def test_sif_uses_secret_key_header(self) -> None:
        key = "sifmcp260528fp77b4awf9e4qfpb"
        endpoint = build_sif_endpoint(key=key)
        assert endpoint.name == "sif"
        assert endpoint.url == "https://mcp.sif.com/mcp"
        assert endpoint.headers["secret-key"] == key
        assert key not in endpoint.url

    def test_settings_secrets_never_repr(self) -> None:
        sample_credential = "64283124d5ca414ba43940dc0239c9b7"
        settings = Settings(SELLERSPRITE_MCP_KEY=SecretStr(sample_credential))
        assert sample_credential not in repr(settings)
        assert settings.sellersprite_mcp_url == "https://mcp.sellersprite.com/mcp"
        assert settings.sorftime_mcp_url == "https://mcp.sorftime.com"


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeToolsResult:
    def __init__(self, names: list[str]) -> None:
        self.tools = [_FakeTool(n) for n in names]


class TestProbeRemoteMcpMocked:
    @pytest.mark.asyncio
    async def test_probe_success_lists_tools_fixture_false(self) -> None:
        # Given: mocked streamable HTTP + ClientSession
        sample_credential = "64283124d5ca414ba43940dc0239c9b7"
        endpoint = RemoteMcpEndpoint(
            name="sellersprite",
            url="https://mcp.sellersprite.com/mcp",
            headers={"secret-key": sample_credential},
        )
        tool_names = [f"tool_{i}" for i in range(20)] + ["ping"]

        session = AsyncMock()
        session.initialize = AsyncMock()
        session.list_tools = AsyncMock(return_value=_FakeToolsResult(tool_names))
        session.call_tool = AsyncMock(return_value=SimpleNamespace(content=[]))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        streams_cm = AsyncMock()
        streams_cm.__aenter__ = AsyncMock(
            return_value=(MagicMock(), MagicMock(), lambda: None)
        )
        streams_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "amazon_copy.mcp.remote_http.streamable_http_client",
                return_value=streams_cm,
            ) as client_factory,
            patch(
                "amazon_copy.mcp.remote_http.ClientSession",
                return_value=session,
            ),
        ):
            # When
            result = await probe_remote_mcp(endpoint)

        # Then
        assert result["ok"] is True
        assert result["fixture"] is False
        assert result["name"] == "sellersprite"
        assert result["tool_count"] == 21
        assert len(result["tool_names"]) == 15
        assert result["error_code"] is None
        assert sample_credential not in str(result)
        client_factory.assert_called_once()
        call_kwargs = client_factory.call_args
        assert call_kwargs[0][0] == endpoint.url
        assert (
            call_kwargs[1]["http_client"].headers["secret-key"]
            == sample_credential
        )

    @pytest.mark.asyncio
    async def test_probe_failure_redacts_secret_in_error(self) -> None:
        sample_credential = "t0tybkheowxtzvi2suv2ulbnl3hndz09"
        endpoint = build_sorftime_endpoint(key=sample_credential)

        streams_cm = AsyncMock()
        streams_cm.__aenter__ = AsyncMock(
            side_effect=ConnectionError(f"connect failed key={sample_credential}")
        )
        streams_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "amazon_copy.mcp.remote_http.streamable_http_client",
            return_value=streams_cm,
        ):
            result = await probe_remote_mcp(endpoint)

        assert result["ok"] is False
        assert result["fixture"] is False
        assert result["error_code"] == "ConnectionError"
        assert sample_credential not in (result["error_message"] or "")
        assert sample_credential not in str(result)

    @pytest.mark.asyncio
    async def test_probe_tool_sample_cap(self) -> None:
        endpoint = RemoteMcpEndpoint(name="x", url="https://example.test/mcp")
        names = [f"t{i}" for i in range(3)]
        session = AsyncMock()
        session.initialize = AsyncMock()
        session.list_tools = AsyncMock(return_value=_FakeToolsResult(names))
        session.call_tool = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        streams_cm = AsyncMock()
        streams_cm.__aenter__ = AsyncMock(
            return_value=(MagicMock(), MagicMock(), lambda: None)
        )
        streams_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "amazon_copy.mcp.remote_http.streamable_http_client",
                return_value=streams_cm,
            ),
            patch(
                "amazon_copy.mcp.remote_http.ClientSession",
                return_value=session,
            ),
        ):
            result = await probe_remote_mcp(
                endpoint, call_safe_tool=False, tool_sample=2
            )

        assert result["tool_count"] == 3
        assert result["tool_names"] == ["t0", "t1"]
        session.call_tool.assert_not_called()


class TestOfflineFixturePathIntact:
    """Empty remote keys must not force live MCP for normal research path."""

    def test_empty_keys_yield_no_endpoints(self) -> None:
        settings = Settings(
            MOCK=True,
            OPENAI_API_KEY=SecretStr(""),
            SELLERSPRITE_MCP_KEY=SecretStr(""),
            SORFTIME_MCP_KEY=SecretStr(""),
            SIF_MCP_KEY=SecretStr(""),
        )
        assert endpoints_from_settings(settings) == []

    def test_fake_provider_still_fixture_true(self) -> None:
        async def _run() -> ResearchResult:
            async with build_fake_provider().open_session() as session:
                return await session.call(
                    ResearchQuery(role="product", query="x")
                )

        result = anyio.run(_run)
        assert result.fixture is True
