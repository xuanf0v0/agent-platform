"""Validated session serialization for redacted live-research snapshots."""

from __future__ import annotations

from typing import Final, cast

from pydantic import ValidationError

from amazon_copy.mcp.live_research_models import (
    McpCallRecord,
    McpToolSnapshot,
    SnapshotStatus,
)
from amazon_copy.mcp.live_research_types import ResearchGap, ResearchItem
from amazon_copy.mcp.security import (
    sanitize_mcp_payload,
    sanitize_mcp_session_text,
    sanitize_mcp_text,
)

_MAX_SESSION_TOOL_COUNT: Final = 1_000_000
_MAX_SESSION_TOOL_COUNT_DIGITS: Final = 7


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def _object_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw = cast("dict[object, object]", value)
    return {str(key): item for key, item in raw.items()}


def _session_value(value: object) -> object:
    if isinstance(value, str):
        return sanitize_mcp_session_text(value)
    if isinstance(value, list):
        values = cast("list[object]", value)
        return [_session_value(item) for item in values]
    if isinstance(value, tuple):
        values = cast("tuple[object, ...]", value)
        return [_session_value(item) for item in values]
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return {str(key): _session_value(item) for key, item in mapping.items()}
    return value


def snapshot_to_dict(snapshot: McpToolSnapshot) -> dict[str, object]:
    """Serialize only UI-safe snapshot fields for session state."""
    raw: dict[str, object] = {
        "provider": snapshot.provider,
        "status": snapshot.status,
        "tool_count": snapshot.tool_count,
        "tools_sample": list(snapshot.tools_sample),
        "calls": [dict(call) for call in snapshot.calls],
        "error": snapshot.error,
        "research_items": [item.model_dump(mode="json") for item in snapshot.research_items],
        "research_gaps": [gap.model_dump(mode="json") for gap in snapshot.research_gaps],
    }
    sanitized = sanitize_mcp_payload(_session_value(raw))
    mapping = _object_dict(sanitized.value)
    if mapping is not None:
        return mapping
    code = sanitized.limit_code or "payload_too_large"
    provider = sanitize_mcp_text(snapshot.provider)
    return {
        "provider": provider,
        "status": "skipped",
        "tool_count": 0,
        "tools_sample": [],
        "calls": [],
        "error": None,
        "research_items": [],
        "research_gaps": [ResearchGap(code=code, provider=provider).model_dump(mode="json")],
    }


def _status(value: object) -> SnapshotStatus:
    if isinstance(value, str) and value in {"ok", "error", "skipped"}:
        return cast("SnapshotStatus", value)
    return "error"


def _string_list(value: object) -> list[str]:
    values = _object_list(value)
    if values is None:
        return []
    return [item for item in values if isinstance(item, str)]


def _calls(value: object) -> list[McpCallRecord]:
    values = _object_list(value)
    if values is None:
        return []
    calls: list[McpCallRecord] = []
    for item in values:
        mapping = _object_dict(item)
        if mapping is None:
            continue
        calls.append(
            McpCallRecord(
                tool=str(mapping.get("tool", "")),
                ok=mapping.get("ok") is True,
                summary_text=str(mapping.get("summary_text", "")),
            )
        )
    return calls


def _malformed_gap(provider: str) -> ResearchGap:
    return ResearchGap(
        code="payload_malformed",
        provider=provider,
        tool="session_cache",
    )


def _research(
    item_values: object,
    gap_values: object,
    provider: str,
) -> tuple[tuple[ResearchItem, ...], tuple[ResearchGap, ...]]:
    items: list[ResearchItem] = []
    gaps: list[ResearchGap] = []
    item_list = _object_list(item_values)
    if item_list is not None:
        for value in item_list:
            try:
                items.append(ResearchItem.model_validate(value))
            except ValidationError:
                gaps.append(_malformed_gap(provider))
    gap_list = _object_list(gap_values)
    if gap_list is not None:
        for value in gap_list:
            try:
                gaps.append(ResearchGap.model_validate(value))
            except ValidationError:
                gaps.append(_malformed_gap(provider))
    return tuple(items), tuple(gaps)


def _snapshot(value: object) -> McpToolSnapshot | None:
    if isinstance(value, McpToolSnapshot):
        value = snapshot_to_dict(value)
    mapping = _object_dict(value)
    if mapping is None:
        return None
    sanitized = sanitize_mcp_payload(_session_value(mapping))
    if sanitized.limit_code is not None:
        return McpToolSnapshot(
            provider="unknown",
            status="skipped",
            tool_count=0,
            research_gaps=(ResearchGap(code=sanitized.limit_code, provider="unknown"),),
        )
    mapping = _object_dict(sanitized.value)
    if mapping is None:
        return None
    provider_value = mapping.get("provider", "unknown")
    provider = provider_value if isinstance(provider_value, str) else "unknown"
    research_items, research_gaps = _research(
        mapping.get("research_items"),
        mapping.get("research_gaps"),
        provider,
    )
    error = mapping.get("error")
    tool_count_value = mapping.get("tool_count")
    tool_count, malformed_count = _tool_count(tool_count_value)
    if malformed_count:
        research_gaps = (*research_gaps, _malformed_gap(provider))
    return McpToolSnapshot(
        provider=provider,
        status=_status(mapping.get("status")),
        tool_count=tool_count,
        tools_sample=_string_list(mapping.get("tools_sample")),
        calls=_calls(mapping.get("calls")),
        error=error if isinstance(error, str) else None,
        research_items=research_items,
        research_gaps=research_gaps,
    )


def _tool_count(value: object) -> tuple[int, bool]:
    if isinstance(value, bool):
        return 0, True
    if isinstance(value, int):
        return (value, False) if 0 <= value <= _MAX_SESSION_TOOL_COUNT else (0, True)
    if (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and len(value) <= _MAX_SESSION_TOOL_COUNT_DIGITS
    ):
        return int(value), False
    return 0, value is not None


def snapshots_from_session(raw: object) -> list[McpToolSnapshot]:
    """Restore valid snapshots while safely discarding unrelated session values."""
    values = _object_list(raw)
    if values is None:
        return []
    return [snapshot for value in values if (snapshot := _snapshot(value)) is not None]


__all__ = ["snapshot_to_dict", "snapshots_from_session"]
