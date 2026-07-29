"""Optional Writing MCP adapters: writing-tools-mcp + that's boring Writing Editor.

These replace *partial* grammar/readability diagnosis and light English polish.
They never authorize product facts and must not override Amazon length/claim gates.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, TextContent

from amazon_copy.schemas import OptimizedListingCopy


@dataclass(frozen=True, slots=True)
class StdioMcpCommand:
    """One local stdio MCP server launch command."""

    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None


def _text_from_result(result: CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, TextContent) and block.text:
            parts.append(block.text)
    return "\n".join(parts).strip()


def _parse_payload(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def call_stdio_tool_async(
    server: StdioMcpCommand,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float = 20.0,
) -> Any:
    """Call one tool on a stdio MCP server and return parsed JSON or text."""

    params = StdioServerParameters(
        command=server.command,
        args=list(server.args),
        env=server.env,
    )

    async def _run() -> Any:
        async with stdio_client(params) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                _ = await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.isError:
                    message = _text_from_result(result) or f"tool_error:{tool_name}"
                    raise RuntimeError(message)
                return _parse_payload(_text_from_result(result))

    with anyio.fail_after(timeout_seconds):
        return await _run()


def call_stdio_tool(
    server: StdioMcpCommand,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float = 20.0,
) -> Any | None:
    """Synchronous wrapper; returns None on transport or tool failure."""

    async def _run() -> Any:
        return await call_stdio_tool_async(
            server,
            tool_name,
            arguments,
            timeout_seconds=timeout_seconds,
        )

    try:
        return anyio.run(_run)
    except (
        TimeoutError,
        McpError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        ExceptionGroup,
    ):
        return None


if TYPE_CHECKING:
    from amazon_copy.config import Settings
    from amazon_copy.schemas import SourceListingCopy

WritingMcpStatus = Literal["disabled", "ok", "degraded", "error"]

_MAX_ANALYSIS_CHARS: Final = 12_000
_PASSIVE_HINT_RE: Final = re.compile(
    r"\b(?:was|were|is|are|been|be)\s+\w+(?:ed|en)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class WritingAnalysis:
    """Redacted writing signals for diagnosis and rewrite guidance."""

    status: WritingMcpStatus = "disabled"
    provider: str = ""
    character_count: int | None = None
    word_count: int | None = None
    misspellings: tuple[str, ...] = ()
    readability: dict[str, float] = field(default_factory=dict)
    passive_sentences: tuple[str, ...] = ()
    top_keywords: tuple[tuple[str, int], ...] = ()
    clarity_notes: tuple[str, ...] = ()
    editor_preview: str = ""
    gaps: tuple[str, ...] = ()

    def as_prompt_dict(self) -> dict[str, Any]:
        """Compact JSON-safe payload for optimizer / diagnosis prompts."""
        if self.status == "disabled":
            return {"status": "disabled"}
        return {
            "status": self.status,
            "provider": self.provider,
            "character_count": self.character_count,
            "word_count": self.word_count,
            "misspellings": list(self.misspellings[:20]),
            "readability": self.readability,
            "passive_sentence_count": len(self.passive_sentences),
            "passive_samples": list(self.passive_sentences[:5]),
            "top_keywords": [{"term": term, "count": count} for term, count in self.top_keywords[:12]],
            "clarity_notes": list(self.clarity_notes[:8]),
            "editor_preview_available": bool(self.editor_preview),
            "gaps": list(self.gaps),
            "authority": "style_signal_only",
            "can_authorize_facts": False,
        }


def _join_listing_text(
    title: str,
    item_highlights: str,
    bullets: tuple[str, ...] | list[str],
) -> str:
    parts = [title.strip(), item_highlights.strip(), *bullets]
    text = "\n".join(part for part in parts if part)
    return text[:_MAX_ANALYSIS_CHARS]


def _parse_command(raw: str) -> StdioMcpCommand | None:
    pieces = shlex.split(raw.strip())
    if not pieces:
        return None
    return StdioMcpCommand(command=pieces[0], args=tuple(pieces[1:]))


def writing_tools_command(settings: Settings | None) -> StdioMcpCommand | None:
    """Resolve writing-tools-mcp launch command when enabled."""
    if settings is None or not settings.writing_tools_mcp_enabled:
        return None
    return _parse_command(settings.writing_tools_mcp_command)


def writing_editor_command(settings: Settings | None) -> StdioMcpCommand | None:
    """Resolve that's boring Writing Editor launch command when enabled."""
    if settings is None or not settings.writing_editor_mcp_enabled:
        return None
    return _parse_command(settings.writing_editor_mcp_command)


def _as_float_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, (int, float)):
            out[str(key)] = float(raw)
        elif isinstance(raw, dict):
            # nested full-level payload
            for nested_key, nested_val in raw.items():
                if isinstance(nested_val, (int, float)):
                    out[str(nested_key)] = float(nested_val)
    return out


def _as_str_tuple(value: Any, *, limit: int = 20) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
        elif isinstance(item, (list, tuple)) and item:
            # top-keywords may return [term, count]
            term = item[0]
            if isinstance(term, str) and term.strip():
                items.append(term.strip())
    return tuple(dict.fromkeys(items))[:limit]


def _as_keyword_pairs(value: Any, *, limit: int = 12) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    pairs: list[tuple[str, int]] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            term, count = item[0], item[1]
            if isinstance(term, str) and isinstance(count, (int, float)):
                pairs.append((term.strip(), int(count)))
        elif isinstance(item, dict):
            term = item.get("term") or item.get("keyword") or item.get("0")
            count = item.get("count") or item.get("1")
            if isinstance(term, str) and isinstance(count, (int, float)):
                pairs.append((term.strip(), int(count)))
    return tuple(pairs)[:limit]


def analyze_listing_writing(
    settings: Settings | None,
    *,
    title: str,
    item_highlights: str,
    bullets: tuple[str, ...] | list[str],
) -> WritingAnalysis:
    """Run optional writing-tools-mcp (+ editor clarity) on listing text."""
    text = _join_listing_text(title, item_highlights, bullets)
    if not text.strip():
        return WritingAnalysis(status="disabled", gaps=("empty_listing",))
    if settings is None:
        return WritingAnalysis(status="disabled")

    tools_cmd = writing_tools_command(settings)
    editor_cmd = writing_editor_command(settings)
    if tools_cmd is None and editor_cmd is None:
        return WritingAnalysis(status="disabled")

    gaps: list[str] = []
    provider_bits: list[str] = []
    misspellings: tuple[str, ...] = ()
    readability: dict[str, float] = {}
    passive: tuple[str, ...] = ()
    top_keywords: tuple[tuple[str, int], ...] = ()
    character_count: int | None = None
    word_count: int | None = None
    clarity_notes: list[str] = []
    editor_preview = ""
    timeout = settings.writing_mcp_timeout_seconds

    if tools_cmd is not None:
        provider_bits.append("writing-tools-mcp")
        char_raw = call_stdio_tool(
            tools_cmd, "character-count", {"text": text}, timeout_seconds=timeout
        )
        word_raw = call_stdio_tool(
            tools_cmd, "word-count", {"text": text}, timeout_seconds=timeout
        )
        spell_raw = call_stdio_tool(
            tools_cmd, "spellcheck", {"text": text}, timeout_seconds=timeout
        )
        read_raw = call_stdio_tool(
            tools_cmd,
            "readability-score",
            {"text": text, "level": "full"},
            timeout_seconds=timeout,
        )
        passive_raw = call_stdio_tool(
            tools_cmd,
            "passive-voice-detection",
            {"text": text},
            timeout_seconds=timeout,
        )
        top_raw = call_stdio_tool(
            tools_cmd,
            "top-keywords",
            {"text": text, "top_n": 10, "remove_stopwords": True},
            timeout_seconds=timeout,
        )
        if isinstance(char_raw, (int, float)):
            character_count = int(char_raw)
        elif char_raw is None:
            gaps.append("writing_tools_character_count_failed")
        if isinstance(word_raw, (int, float)):
            word_count = int(word_raw)
        elif word_raw is None:
            gaps.append("writing_tools_word_count_failed")
        if spell_raw is not None:
            misspellings = _as_str_tuple(spell_raw)
        else:
            gaps.append("writing_tools_spellcheck_failed")
        if read_raw is not None:
            readability = _as_float_map(read_raw)
        else:
            gaps.append("writing_tools_readability_failed")
        if passive_raw is not None:
            passive = _as_str_tuple(passive_raw, limit=12)
        else:
            # local soft fallback signal only
            passive = tuple(
                line.strip()
                for line in text.splitlines()
                if _PASSIVE_HINT_RE.search(line)
            )[:8]
            gaps.append("writing_tools_passive_failed")
        if top_raw is not None:
            top_keywords = _as_keyword_pairs(top_raw)
        else:
            gaps.append("writing_tools_top_keywords_failed")

    if editor_cmd is not None:
        provider_bits.append("writing-editor-mcp")
        clarity_raw = call_stdio_tool(
            editor_cmd,
            "check_clarity_metrics",
            {"text": text},
            timeout_seconds=timeout,
        )
        if clarity_raw is None:
            gaps.append("writing_editor_clarity_failed")
        elif isinstance(clarity_raw, dict):
            for key in ("summary", "notes", "issues", "recommendations"):
                value = clarity_raw.get(key)
                if isinstance(value, str) and value.strip():
                    clarity_notes.append(value.strip()[:300])
                elif isinstance(value, list):
                    clarity_notes.extend(
                        str(item).strip()[:200]
                        for item in value[:5]
                        if str(item).strip()
                    )
            for key, value in clarity_raw.items():
                if isinstance(value, (int, float)) and key not in readability:
                    readability[str(key)] = float(value)
        elif isinstance(clarity_raw, str) and clarity_raw.strip():
            clarity_notes.append(clarity_raw.strip()[:300])

        # Optional style preview only — never auto-applied without fact re-check.
        edit_raw = call_stdio_tool(
            editor_cmd,
            "edit_document",
            {
                "text": text,
                "documentType": "paragraph",
                "outputFormat": "clean",
            },
            timeout_seconds=timeout,
        )
        if isinstance(edit_raw, str) and edit_raw.strip():
            editor_preview = edit_raw.strip()[:_MAX_ANALYSIS_CHARS]
        elif isinstance(edit_raw, dict):
            for key in ("text", "edited", "result", "clean"):
                value = edit_raw.get(key)
                if isinstance(value, str) and value.strip():
                    editor_preview = value.strip()[:_MAX_ANALYSIS_CHARS]
                    break
            if not editor_preview:
                gaps.append("writing_editor_edit_unparsed")
        else:
            gaps.append("writing_editor_edit_failed")

    ok_signal = any(
        (
            character_count is not None,
            word_count is not None,
            bool(misspellings),
            bool(readability),
            bool(passive),
            bool(top_keywords),
            bool(clarity_notes),
            bool(editor_preview),
        )
    )
    if not ok_signal:
        status: WritingMcpStatus = "error"
    elif gaps:
        status = "degraded"
    else:
        status = "ok"

    return WritingAnalysis(
        status=status,
        provider="+".join(provider_bits),
        character_count=character_count,
        word_count=word_count,
        misspellings=misspellings,
        readability=readability,
        passive_sentences=passive,
        top_keywords=top_keywords,
        clarity_notes=tuple(dict.fromkeys(clarity_notes))[:8],
        editor_preview=editor_preview,
        gaps=tuple(gaps),
    )


def analyze_source_writing(
    settings: Settings | None, source: SourceListingCopy
) -> WritingAnalysis:
    """Analyze a structured source listing."""
    return analyze_listing_writing(
        settings,
        title=source.title,
        item_highlights=source.item_highlights,
        bullets=source.bullets,
    )


def polish_listing_with_editor(
    settings: Settings | None,
    listing: OptimizedListingCopy,
) -> OptimizedListingCopy | None:
    """Optionally polish optimized fields via Writing Editor.

    Returns None when disabled, failed, or when the editor returns text that
    cannot be safely mapped field-by-field. Callers must re-run postflight.
    """
    if settings is None:
        return None
    cmd = writing_editor_command(settings)
    if cmd is None or not settings.writing_editor_mcp_polish:
        return None

    def _polish_field(text: str) -> str | None:
        if not text.strip():
            return text
        raw = call_stdio_tool(
            cmd,
            "edit_document",
            {
                "text": text,
                "documentType": "paragraph",
                "outputFormat": "clean",
            },
            timeout_seconds=settings.writing_mcp_timeout_seconds,
        )
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, dict):
            for key in ("text", "edited", "result", "clean"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    title = _polish_field(listing.title)
    highlights = _polish_field(listing.item_highlights)
    if title is None or highlights is None:
        return None
    polished_bullets: list[str] = []
    for bullet in listing.bullets:
        polished = _polish_field(bullet)
        if polished is None:
            return None
        polished_bullets.append(polished)
    # Backend terms are keyword roots — never run academic editor on them.
    try:
        return OptimizedListingCopy(
            title=title,
            item_highlights=highlights,
            bullets=tuple(polished_bullets),
            backend_search_terms=listing.backend_search_terms,
        )
    except (TypeError, ValueError):
        return None


def merge_writing_into_diagnosis_issues(
    analysis: WritingAnalysis,
) -> tuple[dict[str, str], ...]:
    """Turn writing MCP signals into diagnosis-style issue dicts."""
    if analysis.status in {"disabled", "error"} and not analysis.misspellings:
        return ()
    issues: list[dict[str, str]] = []
    if analysis.misspellings:
        sample = "、".join(analysis.misspellings[:8])
        issues.append(
            {
                "level": "P1",
                "title": "拼写 · writing-tools-mcp",
                "detail_zh": f"疑似拼写问题：{sample}（风格信号，需人工确认专有名词/品牌）。",
            }
        )
    if analysis.passive_sentences:
        issues.append(
            {
                "level": "P1",
                "title": "被动语态 · writing-tools-mcp",
                "detail_zh": (
                    f"检测到 {len(analysis.passive_sentences)} 处疑似被动句；"
                    "Amazon 文案可保留必要被动，优先改写冗长或含糊句。"
                ),
            }
        )
    flesch = analysis.readability.get("flesch")
    if flesch is not None and flesch < 50:
        issues.append(
            {
                "level": "P1",
                "title": "可读性 · writing-tools-mcp",
                "detail_zh": f"Flesch≈{flesch:.1f}，偏难读；缩短句子、减少堆词（不改变已验证事实）。",
            }
        )
    for note in analysis.clarity_notes[:3]:
        issues.append(
            {
                "level": "P1",
                "title": "清晰度 · writing-editor-mcp",
                "detail_zh": note[:240],
            }
        )
    return tuple(issues)


__all__ = [
    "WritingAnalysis",
    "analyze_listing_writing",
    "analyze_source_writing",
    "merge_writing_into_diagnosis_issues",
    "polish_listing_with_editor",
    "writing_editor_command",
    "writing_tools_command",
]
