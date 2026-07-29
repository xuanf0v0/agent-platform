"""Research node definitions for multi-agent MCP research lanes.

Provides the typed outcome container and helpers shared between the MCP
research orchestrator and any future graph-based pipeline (no LangGraph
dependency yet — pure anyio).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from amazon_copy.mcp.protocol import ALL_ROLES, ResearchQuery, ResearchResult, ResearchRole

if TYPE_CHECKING:
    from amazon_copy.schemas.studio_input import StudioRequest

# ── Types ────────────────────────────────────────────────────────────────

LaneStatus = Literal["success", "failed", "not_applicable"]


@dataclass(frozen=True, slots=True)
class LaneOutcome:
    """The result of one MCP research lane.

    Attributes:
        role: Which role this lane targeted.
        status: ``"success"``, ``"failed"``, or ``"not_applicable"``.
        result: The :class:`ResearchResult` on success; ``None`` otherwise.
        error: A human-readable error description on failure.
    """

    role: ResearchRole
    status: LaneStatus
    result: ResearchResult | None = None
    error: str | None = None


# ── Query builders ──────────────────────────────────────────────────────


def _build_query_text(role: ResearchRole, request: str | StudioRequest) -> str:  # noqa: C901 — role dispatch is intentionally explicit
    """Build a role-specific query string from *request*."""
    if isinstance(request, str):
        return request

    # StudioRequest — tailor the query per role
    if role == "product":
        parts = [request.title]
        if request.brand:
            parts.append(f"Brand: {request.brand}")
        parts.extend(request.bullets)
        return " | ".join(parts)

    if role == "keyword":
        parts = [request.title]
        if request.category:
            parts.append(f"Category: {request.category}")
        return " | ".join(parts)

    if role == "competitor":
        parts = []
        if request.brand:
            parts.append(f"Brand: {request.brand}")
        if request.asin:
            parts.append(f"ASIN: {request.asin}")
        if request.category:
            parts.append(f"Category: {request.category}")
        return " | ".join(parts) or request.title

    if role == "policy":
        parts = [request.title]
        if request.category:
            parts.append(f"Category: {request.category}")
        parts.append(f"Marketplace: {request.marketplace}")
        return " | ".join(parts)

    # shopper
    parts = [request.title]
    if request.brand:
        parts.append(f"Brand: {request.brand}")
    parts.extend(request.bullets)
    return " | ".join(parts)


def build_queries(request: str | StudioRequest) -> dict[ResearchRole, ResearchQuery]:
    """Build one :class:`ResearchQuery` per research role.

    When *request* is a :class:`StudioRequest`, each role receives a
    role-tailored query string.  When it is a plain ``str``, the same
    text is sent to every role.
    """
    marketplace = request.marketplace if not isinstance(request, str) else "US"
    def _query(role: ResearchRole) -> ResearchQuery:
        return ResearchQuery(
            role=role,
            query=_build_query_text(role, request),
            marketplace=marketplace,
        )

    return {role: _query(role) for role in ALL_ROLES}


# ── Competitor signal detection ─────────────────────────────────────────


def has_competitor_signal(request: str | object) -> bool:
    """Return ``True`` when *request* carries competitor-relevant data.

    A plain string is always assumed to carry a signal.
    A :class:`StudioRequest` needs at least one of ``brand``, ``asin``,
    or ``category`` to be present.
    """
    if isinstance(request, str):
        return True
    return request.brand is not None or request.asin is not None or request.category is not None


# ── Claim normalization ─────────────────────────────────────────────────


def _quick_hash(value: str) -> str:
    """Short content-based hash for claim provenance."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def normalize_result(result: ResearchResult) -> ResearchResult:
    """Normalize claims: ensure ``content_hash`` and non-empty keys.

    - Empty ``key`` values are replaced with ``"unnamed"``.
    - Missing ``content_hash`` values are populated from the claim value.
    - The ``fixture`` flag is preserved as-is.
    """
    normalized = [
        replace(
            c,
            key=c.key or "unnamed",
            content_hash=c.content_hash or _quick_hash(c.value),
        )
        for c in result.claims
    ]
    return replace(result, claims=normalized)
