"""Compatibility shim — stdio helpers live in ``amazon_copy.mcp.writing_mcp``."""

from __future__ import annotations

from amazon_copy.mcp.writing_mcp import (
    StdioMcpCommand,
    call_stdio_tool,
    call_stdio_tool_async,
)

__all__ = [
    "StdioMcpCommand",
    "call_stdio_tool",
    "call_stdio_tool_async",
]
