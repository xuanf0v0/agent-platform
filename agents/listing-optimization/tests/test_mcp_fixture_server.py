"""Tests for the deterministic fixture MCP server (Task 8).

Coverage:
- Five roles discoverable across all modes
- Fixture flag is ``True`` on every result
- Stale/conflict/malformed modes return typed data with expected transforms
- Hang mode is cancellable via anyio cancellation scopes
- No network (trivially — all data comes from local JSON files)
"""

from __future__ import annotations

import json
import sys
from typing import Any

import anyio
import pytest

from amazon_copy.mcp.fixture_server import FixtureMcpServer, build_fixture_provider, main
from amazon_copy.mcp.protocol import ALL_ROLES, ResearchQuery, ResearchResult

# ── Helpers ─────────────────────────────────────────────────────────────


def _collect_claims(claims: list[Any]) -> dict[str, list[str]]:
    """Group claim values by key for easy assertion."""
    grouped: dict[str, list[str]] = {}
    for c in claims:
        grouped.setdefault(c.key, []).append(c.value)
    return grouped


@pytest.mark.asyncio
async def test_five_roles_discoverable_via_fake_provider() -> None:
    """build_fixture_provider yields a session that advertises 5 roles."""
    provider = build_fixture_provider("fresh")
    async with provider.open_session() as session:
        caps = await session.list_capabilities()
    assert caps == set(ALL_ROLES)
    assert len(caps) == 5


@pytest.mark.asyncio
async def test_five_roles_discoverable_via_fixture_server() -> None:
    """FixtureMcpServer yields a session that advertises 5 roles."""
    server = FixtureMcpServer("fresh")
    async with server.open_session() as session:
        caps = await session.list_capabilities()
    assert caps == set(ALL_ROLES)
    assert len(caps) == 5


# ── fixture flag ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fixture_flag_is_true_for_fresh() -> None:
    result = await _call_one("fresh")
    assert result.fixture is True


@pytest.mark.asyncio
async def test_fixture_flag_is_true_for_stale() -> None:
    result = await _call_one("stale")
    assert result.fixture is True


@pytest.mark.asyncio
async def test_fixture_flag_is_true_for_conflict() -> None:
    result = await _call_one("conflict")
    assert result.fixture is True


@pytest.mark.asyncio
async def test_fixture_flag_is_true_for_malformed() -> None:
    result = await _call_one("malformed")
    assert result.fixture is True


async def _call_one(mode: str = "fresh") -> ResearchResult:
    server = FixtureMcpServer(mode)
    async with server.open_session() as session:
        return await session.call(
            ResearchQuery(role="product", query="USB-C Hub")
        )


# ── Fresh mode ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fresh_mode_returns_json_fixture_data() -> None:
    """Fresh mode should return exactly the data from the JSON fixture file."""
    server = FixtureMcpServer("fresh")
    async with server.open_session() as session:
        result = await session.call(
            ResearchQuery(role="product", query="USB-C Hub")
        )

    assert isinstance(result, ResearchResult)
    assert result.role == "product"
    # The JSON fixture has a claim with key "title" and value starting as expected
    grouped = _collect_claims(result.claims)
    assert "title" in grouped
    assert "Premium USB-C Hub" in grouped["title"][0]
    assert not any("[STALE]" in v for vals in grouped.values() for v in vals)


# ── Stale mode ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_mode_appends_stale_suffix() -> None:
    """Stale mode should append ' [STALE]' to every claim value."""
    server = FixtureMcpServer("stale")
    async with server.open_session() as session:
        result = await session.call(
            ResearchQuery(role="keyword", query="keywords")
        )

    assert isinstance(result, ResearchResult)
    assert len(result.claims) >= 1
    for claim in result.claims:
        assert claim.value.endswith(" [STALE]"), (
            f"Claim '{claim.key}' value '{claim.value}' should end with [STALE]"
        )


@pytest.mark.asyncio
async def test_stale_mode_all_five_roles() -> None:
    """Every role yields stale data in stale mode."""
    server = FixtureMcpServer("stale")
    async with server.open_session() as session:
        for role in ALL_ROLES:
            result = await session.call(ResearchQuery(role=role, query="test"))
            assert isinstance(result, ResearchResult)
            assert result.fixture is True
            if result.claims:
                val = result.claims[0].value
                assert val.endswith(" [STALE]"), f"Role {role} not stale: {val}"


# ── Conflict mode ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conflict_mode_doubles_claims() -> None:
    """Conflict mode duplicates every claim with a conflicting value."""
    server = FixtureMcpServer("conflict")
    async with server.open_session() as session:
        result = await session.call(
            ResearchQuery(role="competitor", query="competitors")
        )

    assert isinstance(result, ResearchResult)
    grouped = _collect_claims(result.claims)
    for key, values in grouped.items():
        assert len(values) == 2, (
            f"Key '{key}' should have 2 conflicting values, got {len(values)}"
        )
        assert any("[CONFLICTING]" in v for v in values)


@pytest.mark.asyncio
async def test_conflict_mode_returns_typed_data() -> None:
    """Conflict mode returns valid ResearchResult (not a bare dict)."""
    server = FixtureMcpServer("conflict")
    async with server.open_session() as session:
        result = await session.call(
            ResearchQuery(role="product", query="test")
        )

    assert isinstance(result, ResearchResult)
    assert result.fixture is True


# ── Malformed mode ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_mode_has_empty_key_and_zero_confidence() -> None:
    """Malformed mode includes an empty-key claim and a zero-confidence claim."""
    server = FixtureMcpServer("malformed")
    async with server.open_session() as session:
        result = await session.call(
            ResearchQuery(role="policy", query="policies")
        )

    assert isinstance(result, ResearchResult)
    keys = [c.key for c in result.claims]
    assert "" in keys, "Expected at least one claim with an empty key"

    zero_conf = [c for c in result.claims if c.confidence == 0.0]
    assert len(zero_conf) >= 1, "Expected at least one claim with 0.0 confidence"


# ── Hang mode ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hang_mode_cancelled_with_anyio() -> None:
    """Hang mode blocks on anyio.Event and is unblocked by cancellation."""
    server = FixtureMcpServer("hang")
    hang_cancelled = False

    async with anyio.create_task_group() as tg:
        async with server.open_session() as session:

            async def _hang_call() -> None:
                nonlocal hang_cancelled
                try:
                    await session.call(
                        ResearchQuery(role="product", query="USB-C Hub")
                    )
                except BaseException:
                    hang_cancelled = True

            tg.start_soon(_hang_call)
            # Let the task start and hit the hang
            await anyio.sleep(0.05)
            # Cancel the task group — this should abort the hang
            tg.cancel_scope.cancel()

    assert hang_cancelled, "Hang call was not cancelled"


@pytest.mark.asyncio
async def test_hang_mode_list_capabilities_still_works() -> None:
    """list_capabilities() still works in hang mode (only call() hangs)."""
    server = FixtureMcpServer("hang")
    async with server.open_session() as session:
        caps = await session.list_capabilities()
    assert caps == set(ALL_ROLES)
    assert len(caps) == 5


# ── FixtureMcpServer ────────────────────────────────────────────────────


def test_fixture_mcp_server_ready_json() -> None:
    """ready_json returns a well-formed JSON description."""
    server = FixtureMcpServer("fresh")
    info = server.ready_json()
    assert info["server"] == "amazon_mcp_fixture"
    assert info["mode"] == "fresh"
    assert info["fixture"] is True
    assert info["status"] == "ready"
    assert sorted(info["roles"]) == sorted(ALL_ROLES)


def test_fixture_mcp_server_default_mode_is_fresh() -> None:
    server = FixtureMcpServer()
    assert server.mode == "fresh"


def test_build_fixture_provider_no_args_returns_provider() -> None:
    provider = build_fixture_provider()
    from amazon_copy.mcp.client import FakeProvider
    assert isinstance(provider, FakeProvider)


# ── CLI main ────────────────────────────────────────────────────────────


def test_cli_main_prints_json_and_exits_zero() -> None:
    """``python -m amazon_copy.mcp.fixture_server`` prints JSON and exits 0."""
    from io import StringIO

    old_stdout = sys.stdout
    captured = StringIO()
    sys.stdout = captured
    try:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert output.strip(), "Expected non-empty JSON output"
    parsed = json.loads(output)
    assert parsed["server"] == "amazon_mcp_fixture"
    assert parsed["status"] == "ready"


def test_cli_main_accepts_mode_arg() -> None:
    """CLI accepts a mode argument and reflects it in the JSON."""
    from io import StringIO

    old_argv = sys.argv
    old_stdout = sys.stdout
    sys.argv = ["fixture_server", "stale"]
    captured = StringIO()
    sys.stdout = captured
    try:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout

    parsed = json.loads(captured.getvalue())
    assert parsed["mode"] == "stale"


# ── No network ──────────────────────────────────────────────────────────


def test_no_network_all_data_is_local() -> None:
    """Every fixture file exists on disk — no network calls involved."""
    import os
    from amazon_copy.mcp.fixture_server import FIXTURES_DIR

    for role in ALL_ROLES:
        path = os.path.join(FIXTURES_DIR, f"{role}.json")
        assert os.path.isfile(path), f"Missing fixture file: {path}"
