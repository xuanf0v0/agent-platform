"""Generic stdio MCP tool caller for optional local writing servers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, TextContent


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


__all__ = [
    "StdioMcpCommand",
    "call_stdio_tool",
    "call_stdio_tool_async",
]
