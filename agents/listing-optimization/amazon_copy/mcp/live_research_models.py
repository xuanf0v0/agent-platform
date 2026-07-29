"""UI-safe models and pure helpers for live MCP research snapshots."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, cast, runtime_checkable
from urllib.parse import parse_qsl, urlsplit

from typing_extensions import TypedDict, override

from amazon_copy.mcp.live_research_types import ResearchGap, ResearchItem
from amazon_copy.mcp.remote_http import RemoteMcpEndpoint
from amazon_copy.mcp.security import is_secret_key, sanitize_mcp_text, sanitize_mcp_value

SnapshotStatus = Literal["ok", "error", "skipped"]

_MAX_TOOLS_SAMPLE: Final[int] = 12
_MAX_SUMMARY_CHARS: Final[int] = 2000
_MAX_CALLS: Final[int] = 2
_SELLERSPRITE_PREFERRED: Final[tuple[str, ...]] = (
    "keyword_miner",
    "keyword_research",
    "product_research",
    "google_trend",
)
_SORFTIME_PREFERRED: Final[tuple[str, ...]] = (
    "potential_product",
    "keyword_research",
    "keyword_miner",
    "related_keyword",
    "keyword_related",
)
# SIF tools/list payloads exceed the shared response budget; call known tools
# directly after initialize without listing the full catalog.
# Prefer demand + competition only (max 2 calls) for automatic research.
_SIF_PREFERRED: Final[tuple[str, ...]] = (
    "market_get_keyword_demand",
    "market_get_keyword_competition",
)
_SIF_KNOWN_TOOLS: Final[frozenset[str]] = frozenset(
    {
        *_SIF_PREFERRED,
        "market_screen_keyword_opportunities",
        "market_get_keyword_root_trend",
    }
)


class McpCallRecord(TypedDict):
    """One best-effort tool invocation summary for the UI."""

    tool: str
    ok: bool
    summary_text: str


class _BoundaryValue(Protocol):
    @override
    def __str__(self) -> str: ...


@runtime_checkable
class _ContentEnvelope(Protocol):
    @property
    def content(self) -> _BoundaryValue: ...


@runtime_checkable
class _TextBlock(Protocol):
    @property
    def text(self) -> _BoundaryValue: ...


@dataclass(frozen=True, slots=True)
class McpToolSnapshot:
    """UI-safe snapshot of one remote MCP provider after live research."""

    provider: str
    status: SnapshotStatus
    tool_count: int
    tools_sample: list[str] = field(default_factory=list)
    calls: list[McpCallRecord] = field(default_factory=list)
    error: str | None = None
    research_items: tuple[ResearchItem, ...] = ()
    research_gaps: tuple[ResearchGap, ...] = ()


def derive_research_query(title: str, *, max_words: int = 8) -> str:
    """Derive a short marketplace query from a listing title."""
    words = [w for w in title.strip().split() if w]
    if not words:
        return "amazon product"
    return " ".join(words[: max(1, max_words)])


def truncate_summary(text: str, *, limit: int = _MAX_SUMMARY_CHARS) -> str:
    """Truncate long tool payloads for safe UI display."""
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def content_to_text(content: _BoundaryValue) -> str:
    """Best-effort stringify MCP tool content blocks / results."""
    if content is None:
        return ""
    if isinstance(content, str):
        return sanitize_mcp_text(content)
    if isinstance(content, (bytes, bytearray)):
        return sanitize_mcp_text(bytes(content).decode("utf-8", errors="replace"))
    if isinstance(content, _ContentEnvelope) and isinstance(content.content, (list, tuple)):
        parts: list[str] = []
        blocks = cast(
            "list[_BoundaryValue] | tuple[_BoundaryValue, ...]",
            content.content,
        )
        for block in blocks:
            text = block.text if isinstance(block, _TextBlock) else None
            if isinstance(text, str) and text:
                parts.append(sanitize_mcp_text(text))
            else:
                parts.append(sanitize_mcp_text(str(block)))
        if parts:
            return "\n".join(parts)
    try:
        return json.dumps(sanitize_mcp_value(content), ensure_ascii=False)
    except (TypeError, ValueError):
        return sanitize_mcp_text(str(content))


def collect_endpoint_secrets(endpoint: RemoteMcpEndpoint) -> tuple[str, ...]:
    """Collect header/query secrets for redaction (never returned to UI)."""
    secrets = [value for value in endpoint.headers.values() if value]
    secrets.extend(
        value
        for key, value in parse_qsl(urlsplit(endpoint.url).query, keep_blank_values=True)
        if is_secret_key(key) and value
    )
    return tuple(secrets)


def sanitize_text(text: str, secrets: Sequence[str]) -> str:
    """Redact secrets and secret-bearing URLs from display text."""
    return truncate_summary(sanitize_mcp_text(text, tuple(secrets)))


def preferred_tool_names(provider: str) -> tuple[str, ...]:
    """Preferred read-oriented tool names per provider."""
    if provider == "sellersprite":
        return _SELLERSPRITE_PREFERRED
    if provider == "sorftime":
        return _SORFTIME_PREFERRED
    if provider == "sif":
        return _SIF_PREFERRED
    return ()


def known_tool_names(provider: str) -> frozenset[str]:
    """Return built-in tool names that may be called without list_tools."""
    if provider == "sif":
        return _SIF_KNOWN_TOOLS
    return frozenset()


def pick_research_tools(provider: str, tool_names: Sequence[str]) -> list[str]:
    """Pick only exact reviewed read-only tool names for the named provider."""
    advertised = frozenset(tool_names)
    preferred = preferred_tool_names(provider)
    if not preferred:
        return []
    # When the provider catalog was skipped (budget), use the built-in allowlist.
    if not advertised and known_tool_names(provider):
        return list(preferred)[:_MAX_CALLS]
    return [name for name in preferred if name in advertised][:_MAX_CALLS]


__all__ = [
    "_MAX_TOOLS_SAMPLE",
    "McpCallRecord",
    "McpToolSnapshot",
    "SnapshotStatus",
    "collect_endpoint_secrets",
    "content_to_text",
    "derive_research_query",
    "known_tool_names",
    "pick_research_tools",
    "preferred_tool_names",
    "sanitize_text",
    "truncate_summary",
]
