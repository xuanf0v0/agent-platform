"""Deterministic fixture MCP server for offline testing.

Provides:
- :class:`FixtureMcpServer` — wraps :class:`FakeProvider` with labelled
  ``fixture=True`` results and mode-specific behaviour.
- :func:`build_fixture_provider` — factory that loads JSON fixture files
  and returns a :class:`FakeProvider` pre-populated with deterministic data.

Modes
-----
- ``fresh`` (default): unmodified fixture data with ``fixture=True``.
- ``stale``: all claim values are suffixed with `` [STALE]``.
- ``conflict``: every claim has a second claim with the same key but
  a different value.
- ``malformed``: claims have empty keys or zero confidence.
- ``hang``: :meth:`call` blocks on ``anyio.Event.wait()`` until
  the surrounding cancellation scope is cancelled.

Usage::

    from amazon_copy.mcp.fixture_server import build_fixture_provider

    async with build_fixture_provider("fresh").open_session() as session:
        caps = await session.list_capabilities()          # 5 roles
        result = await session.call(ResearchQuery(...))   # fixture data
        assert result.fixture is True
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio

from amazon_copy.mcp.client import FakeProvider, FakeSession
from amazon_copy.mcp.protocol import (
    ALL_ROLES,
    ResearchClaim,
    ResearchError,
    ResearchQuery,
    ResearchResult,
    ResearchSession,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# ── Internal helpers ────────────────────────────────────────────────────


def _load_fixture_dict(role: str) -> dict[str, Any]:
    """Load a single fixture JSON file and return the raw dict."""
    path = os.path.join(FIXTURES_DIR, f"{role}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "role": role,
            "claims": [],
            "fixture": True,
        }


def _dict_to_result(data: dict[str, Any]) -> ResearchResult:
    """Convert a fixture JSON dict to a typed :class:`ResearchResult`."""
    claims = [ResearchClaim(**c) for c in data.get("claims", [])]
    return ResearchResult(
        role=data["role"],
        claims=claims,
        fixture=data.get("fixture", True),
    )


def _load_all_fixtures() -> dict[str, ResearchResult]:
    """Load **all** five fixture files and return a role→result mapping."""
    return {role: _dict_to_result(_load_fixture_dict(role)) for role in ALL_ROLES}


# ── Mode transforms ─────────────────────────────────────────────────────


def _apply_stale(r: ResearchResult) -> ResearchResult:
    """Append `` [STALE]`` to every claim value."""
    return ResearchResult(
        role=r.role,
        claims=[
            ResearchClaim(
                key=c.key,
                value=f"{c.value} [STALE]",
                authority=c.authority,
                confidence=c.confidence,
                content_hash=c.content_hash or "stale",
            )
            for c in r.claims
        ],
        fixture=True,
    )


def _apply_conflict(r: ResearchResult) -> ResearchResult:
    """Duplicate each claim with a conflicting value."""
    doubled: list[ResearchClaim] = []
    for c in r.claims:
        doubled.append(c)
        doubled.append(
            ResearchClaim(
                key=c.key,
                value=f"{c.value} [CONFLICTING]",
                authority=f"{c.authority}_secondary",
                confidence=round(c.confidence * 0.5, 2),
            )
        )
    return ResearchResult(role=r.role, claims=doubled, fixture=True)


def _apply_malformed(r: ResearchResult) -> ResearchResult:
    """Introduce an empty-key claim and a zero-confidence claim."""
    tainted = list(r.claims)
    tainted.insert(
        0,
        ResearchClaim(key="", value="missing key", authority="malformed", confidence=0.0),
    )
    tainted.append(
        ResearchClaim(key="bad_conf", value="", authority="malformed", confidence=0.0),
    )
    return ResearchResult(role=r.role, claims=tainted, fixture=True)


# ── Hang session ────────────────────────────────────────────────────────


class _HangSession:
    """Session whose :meth:`call` blocks on an :class:`anyio.Event`.

    Cancelling the task running the call will abort the hang.
    """

    def __init__(self, inner: ResearchSession) -> None:
        self._inner = inner
        self._hang_event = anyio.Event()

    async def list_capabilities(self) -> set[str]:
        return await self._inner.list_capabilities()

    async def call(self, query: ResearchQuery) -> ResearchResult:
        await self._hang_event.wait()
        # Should never reach here — caller must cancel before this
        raise ResearchError(code="HANG", message="Unexpectedly unblocked")


# ── Public API ──────────────────────────────────────────────────────────


def build_fixture_provider(mode: str = "fresh") -> FakeProvider:
    """Build a :class:`FakeProvider` pre-populated with mode-specific fixtures.

    Args:
        mode: One of ``"fresh"``, ``"stale"``, ``"conflict"``,
            ``"malformed"``, or ``"hang"``.

    Returns:
        A :class:`FakeProvider` that yields sessions returning mode-shaped data.
    """
    fixtures = _load_all_fixtures()

    if mode == "stale":
        fixtures = {r: _apply_stale(v) for r, v in fixtures.items()}
    elif mode == "conflict":
        fixtures = {r: _apply_conflict(v) for r, v in fixtures.items()}
    elif mode == "malformed":
        fixtures = {r: _apply_malformed(v) for r, v in fixtures.items()}
    elif mode == "fresh":
        pass  # already fixture=True in JSON
    elif mode == "hang":
        pass  # handled by FixtureMcpServer / _HangSession wrapper

    return FakeProvider(fixtures=fixtures)


# ── FixtureMcpServer ────────────────────────────────────────────────────


class FixtureMcpServer:
    """Deterministic fixture MCP server for offline contract testing.

    Wraps :class:`FakeProvider` with explicit mode support and a
    ``fixture=True`` guarantee on all returned :class:`ResearchResult`\\ s.

    Usage::

        server = FixtureMcpServer(mode="fresh")
        async with server.open_session() as session:
            caps = await session.list_capabilities()
            result = await session.call(ResearchQuery(...))
    """

    def __init__(self, mode: str = "fresh") -> None:
        self.mode = mode
        self._provider = build_fixture_provider(mode)

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[ResearchSession]:
        """Yield a :class:`ResearchSession` whose :meth:`call` returns
        deterministic fixture data shaped by *mode*."""
        async with self._provider.open_session() as session:
            if self.mode == "hang":
                yield _HangSession(session)
            else:
                yield session

    def ready_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict describing this server's state."""
        return {
            "server": "amazon_mcp_fixture",
            "mode": self.mode,
            "roles": sorted(ALL_ROLES),
            "fixture": True,
            "status": "ready",
        }


# ── CLI ─────────────────────────────────────────────────────────────────


def main() -> None:
    """Print ready JSON and exit (no real MCP stdio server)."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "fresh"
    server = FixtureMcpServer(mode=mode)
    json.dump(server.ready_json(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
