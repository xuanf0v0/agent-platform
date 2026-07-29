"""Async studio LLM — routing, mock fixtures, timeout behaviour."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from amazon_copy.config import Settings
from amazon_copy.llm import (
    STUDIO_ROLES,
    AsyncLLMClient,
    ConfigError,
    get_async_llm,
    route_model,
)
from amazon_copy.llm.mock import AsyncMockLLM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    *,
    writer: str = "deepseek-chat",
    review: str = "deepseek-chat",
    vote: str = "deepseek-chat",
) -> Settings:
    return Settings(
        MOCK=True,
        WRITER_MODEL=writer,
        REVIEW_MODEL=review,
        VOTE_MODEL=vote,
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRouteModel:
    """route_model(role, settings) returns the expected model field."""

    def test_writers_use_writer_model(self) -> None:
        s = _settings(writer="gpt-4")
        for role in ("writer_seo", "writer_differentiation", "writer_clarity"):
            assert route_model(role, s) == "gpt-4"

    def test_reviser_uses_writer_model(self) -> None:
        assert route_model("reviser", _settings(writer="claude-3")) == "claude-3"

    def test_integrator_uses_writer_model(self) -> None:
        assert route_model("integrator", _settings(writer="claude-3")) == "claude-3"

    def test_critic_uses_review_model(self) -> None:
        s = _settings(review="gpt-4-turbo")
        assert route_model("critic", s) == "gpt-4-turbo"

    def test_judge_uses_vote_model(self) -> None:
        s = _settings(vote="gpt-4o")
        assert route_model("judge", s) == "gpt-4o"

    def test_unknown_role_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown studio role"):
            route_model("not-a-role", _settings())


class TestGetAsyncLLMRouting:
    """get_async_llm correctly dispatches to mock vs error."""

    @pytest.mark.parametrize("role", STUDIO_ROLES)
    def test_mock_returns_async_mock_llm(self, role: str) -> None:
        client = get_async_llm(role, settings=_settings())
        assert isinstance(client, AsyncMockLLM)

    def test_bad_role_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="Unknown studio role"):
            get_async_llm("not-a-role", settings=_settings())

    def test_non_mock_without_key_raises_config_error(self) -> None:
        s = Settings(
            MOCK=False,
            OPENAI_API_KEY="",
            WRITER_MODEL="x",
            REVIEW_MODEL="x",
            VOTE_MODEL="x",
        )
        with pytest.raises(ConfigError, match="API key is required"):
            get_async_llm("writer_seo", settings=s)

    def test_non_mock_with_key_returns_async_openai(self) -> None:
        from amazon_copy.llm.async_openai_compat import AsyncOpenAILLM

        s = Settings(
            MOCK=False,
            OPENAI_API_KEY="sk-test-not-real",
            OPENAI_API_BASE="https://api.deepseek.com",
            WRITER_MODEL="deepseek-chat",
            REVIEW_MODEL="deepseek-chat",
            VOTE_MODEL="deepseek-chat",
        )
        client = get_async_llm("writer_seo", settings=s)
        assert isinstance(client, AsyncOpenAILLM)


# ---------------------------------------------------------------------------
# AsyncMockLLM — per-role fixture integrity
# ---------------------------------------------------------------------------


class TestAsyncMockLLM:
    """Every studio role returns parseable deterministic JSON."""

    @pytest.mark.parametrize("role", STUDIO_ROLES)
    @pytest.mark.asyncio
    async def test_returns_parseable_json(self, role: str) -> None:
        client = AsyncMockLLM(role)
        payload = json.loads(await client.complete("system", "user"))
        assert isinstance(payload, dict)
        assert len(payload) >= 1

    @pytest.mark.parametrize("role", STUDIO_ROLES)
    @pytest.mark.asyncio
    async def test_deterministic_output(self, role: str) -> None:
        a = json.loads(await AsyncMockLLM(role).complete("s", "u"))
        b = json.loads(await AsyncMockLLM(role).complete("s", "u"))
        assert a == b

    def test_bad_role_rejected(self) -> None:
        with pytest.raises(ConfigError, match="Unknown studio LLM role"):
            AsyncMockLLM("not-a-role")

    @pytest.mark.asyncio
    async def test_call_count_increments(self) -> None:
        client = AsyncMockLLM("critic")
        assert client.call_count == 0
        await client.complete("s", "u")
        assert client.call_count == 1
        await client.complete("s", "u")
        assert client.call_count == 2

    @pytest.mark.asyncio
    async def test_kwargs_are_accepted_and_ignored(self) -> None:
        client = AsyncMockLLM("judge")
        payload = json.loads(
            await client.complete("sys", "usr", temperature=0.9, max_tokens=999)
        )
        assert "winner" in payload


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocol:
    """AsyncMockLLM satisfies the AsyncLLMClient protocol."""

    def test_is_runtime_checkable(self) -> None:
        assert isinstance(AsyncMockLLM("writer_seo"), AsyncLLMClient)

    @pytest.mark.asyncio
    async def test_async_complete_signature(self) -> None:
        client: AsyncLLMClient = AsyncMockLLM("integrator")
        result = await client.complete("system prompt", "user input")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Timeout — no hidden retry
# ---------------------------------------------------------------------------


class _SlowMock:
    """Fake async client that sleeps *delay* seconds before returning."""

    def __init__(self, delay: float) -> None:
        self._delay = delay
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        self._call_count += 1
        await asyncio.sleep(self._delay)
        return '{"slow": true}'


class TestTimeoutNoRetry:
    """Async timeout raises without a second attempt."""

    @pytest.mark.asyncio
    async def test_short_timeout_raises_and_does_not_retry(self) -> None:
        """A fake that sleeps 10 s must time out with a single call recorded."""
        slow = _SlowMock(delay=10.0)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(slow.complete("s", "u"), timeout=0.01)
        # No hidden retry — exactly one call was made.
        assert slow.call_count == 1

    @pytest.mark.asyncio
    async def test_long_enough_timeout_succeeds(self) -> None:
        """A fast fake should complete within the deadline."""
        fast = _SlowMock(delay=0.001)
        result = await asyncio.wait_for(fast.complete("s", "u"), timeout=5.0)
        assert json.loads(result) == {"slow": True}
        assert fast.call_count == 1
