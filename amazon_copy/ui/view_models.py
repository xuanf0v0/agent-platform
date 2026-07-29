"""View-model helpers for rendering StudioState results in the Streamlit UI."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, TypeAlias, cast

from amazon_copy.mcp.live_research_models import McpToolSnapshot
from amazon_copy.mcp.security import sanitize_mcp_value
from amazon_copy.specialized_rules.catalog import ALLOWLISTED_PROFILE_FILENAMES


class _WinnerLike(Protocol):
    titles: Sequence[str]
    bullets: Sequence[str]


if TYPE_CHECKING:
    from collections.abc import Sequence

    from amazon_copy.orchestrator.state import StudioState
    from amazon_copy.specialized_rules.models import SpecializedRuleCache
    from amazon_copy.ui.audit_pipeline import LayerOutput


_McpSnapshotInput: TypeAlias = McpToolSnapshot | Mapping[str, object]
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


def _snapshot_value(snapshot: _McpSnapshotInput, key: str, default: object) -> object:
    if isinstance(snapshot, Mapping):
        return snapshot.get(key, default)
    return getattr(snapshot, key, default)


def _safe_mcp_text(value: object) -> str:
    sanitized = sanitize_mcp_value(value)
    text = (
        sanitized
        if isinstance(sanitized, str)
        else json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    )
    return _URL_RE.sub("[已隐藏链接]", text)


def format_studio_result(state: StudioState) -> str:
    """Extract seller-ready listing text from a StudioState winner.

    Parameters
    ----------
    state:
        Finished studio pipeline state with an elected winner.

    Returns:
    -------
    str
        Winner's first title (if any) followed by its bullet points, one per
        line.  Returns an empty string when ``state.winner`` is ``None``.
    """
    winner = cast("_WinnerLike | None", state.winner)
    if winner is None:
        return ""

    parts: list[str] = []
    if winner.titles:
        parts.append(winner.titles[0])
    parts.extend(winner.bullets)
    return "\n".join(parts)


def stage_summaries(state: StudioState) -> list[str]:
    """Return redacted progress lines summarising a finished studio run.

    Returns:
    -------
    list[str]
        Short captions safe for UI display — outcome, error count, LLM/MCP
        call tallies, and winner dimension if present.
    """
    lines: list[str] = [f"outcome: {state.outcome}"]

    if state.errors:
        lines.append(f"errors ({len(state.errors)}): {state.errors[-1]}")

    lines.append(f"llm_calls: {state.llm_calls}  ·  mcp_calls: {state.mcp_calls}")

    winner = cast("_WinnerLike | None", state.winner)
    if winner is not None:
        t = len(winner.titles)
        b = len(winner.bullets)
        lines.append(f"winner: {t} title(s)  ·  {b} bullet(s)")

    return lines


def format_mcp_research_sections(
    snapshots: Sequence[_McpSnapshotInput],
) -> list[tuple[str, list[str]]]:
    """Format live MCP research snapshots for Streamlit expanders.

    Returns:
    -------
    list[tuple[str, list[str]]]
        Each item is ``(expander_title, body_lines)`` — no secrets.
    """
    sections: list[tuple[str, list[str]]] = []
    for snap in snapshots:
        provider = _safe_mcp_text(_snapshot_value(snap, "provider", "mcp"))
        status = _safe_mcp_text(_snapshot_value(snap, "status", "error"))
        lines: list[str] = [
            f"status: {status}",
            f"tools: {_safe_mcp_text(_snapshot_value(snap, 'tool_count', 0))}",
        ]
        tools_raw = _snapshot_value(snap, "tools_sample", ())
        tools_values: Sequence[object] = (
            cast("Sequence[object]", tools_raw) if isinstance(tools_raw, (list, tuple)) else ()
        )
        tools = [_safe_mcp_text(item) for item in tools_values if isinstance(item, str)]
        if tools:
            sample = ", ".join(tools[:12])
            lines.append(f"sample: {sample}")
        error = _snapshot_value(snap, "error", None)
        if error:
            lines.append(f"error: {_safe_mcp_text(error)}")
        calls_raw = _snapshot_value(snap, "calls", ())
        calls: Sequence[object] = (
            cast("Sequence[object]", calls_raw) if isinstance(calls_raw, (list, tuple)) else ()
        )
        if calls:
            for call_value in calls:
                if not isinstance(call_value, Mapping):
                    continue
                call = cast("Mapping[str, object]", call_value)
                mark = "ok" if call.get("ok") is True else "fail"
                tool = _safe_mcp_text(call.get("tool", "unknown"))
                lines.append(f"call [{mark}] {tool}:")
                summary = call.get("summary_text") or "(empty)"
                # Keep multi-line summaries as separate caption lines.
                lines.extend(
                    f"  {part}" if part else "  "
                    for part in _safe_mcp_text(summary).splitlines() or ["(empty)"]
                )
        elif status == "ok":
            lines.append("calls: (none attempted)")
        sections.append((f"{provider} · {status}", lines))
    return sections


def _safe_rule_filename(value: str) -> str:
    if value in ALLOWLISTED_PROFILE_FILENAMES:
        return value
    return "未指定规则文件"


def format_specialized_rule_sections(
    cache: SpecializedRuleCache,
    *,
    reused: bool = False,
) -> list[tuple[str, list[str]]]:
    """Build safe profile, hash-prefix, and gap rows for the UI."""
    if cache.all_requested_loaded:
        state = "已加载"
    elif cache.snapshots:
        state = "部分加载 · 降级为通用门槛"
    else:
        state = "未加载 · 降级为通用门槛"
    lines = [
        f"加载状态：{state}",
        f"缓存状态：{'已复用源绑定缓存' if reused else '本次读取'}",
        "内部规则仅作写作门槛，不能授权新产品事实。",
    ]
    snapshots = {snapshot.profile_filename: snapshot for snapshot in cache.snapshots}
    profile_names = tuple(
        dict.fromkeys(
            (
                *cache.requested_profiles,
                *(snapshot.profile_filename for snapshot in cache.snapshots),
            )
        )
    )
    for filename in profile_names:
        safe_filename = _safe_rule_filename(filename)
        snapshot = snapshots.get(filename)
        if snapshot is None:
            lines.append(f"未加载规则：{safe_filename}")
            continue
        lines.append(f"已选规则：{safe_filename} · SHA-256 前缀 {snapshot.content_sha256[:12]}")
    for gap in cache.gaps:
        safe_profile = _safe_rule_filename(gap.profile_filename)
        suffix = f" · {safe_profile}" if gap.profile_filename else ""
        lines.append(f"规则缺口：{gap.code}{suffix}")
    return [("专业规则配置", lines)]


def format_layer_sections(
    layers: Sequence[LayerOutput],
) -> list[tuple[str, list[str]]]:
    """Format audit layers as expander titles and caption lines.

    Returns:
    -------
    list[tuple[str, list[str]]]
        Each item is ``(expander_title, body_lines)`` with titles like
        ``L4 合规审核细则 · ok``.
    """
    sections: list[tuple[str, list[str]]] = []
    for layer in layers:
        title = f"{layer.title_zh} · {layer.status}"
        body = list(layer.lines) if layer.lines else [f"status: {layer.status}"]
        sections.append((title, body))
    return sections


__all__ = [
    "format_layer_sections",
    "format_mcp_research_sections",
    "format_specialized_rule_sections",
    "format_studio_result",
    "stage_summaries",
]
