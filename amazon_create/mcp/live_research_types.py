"""Typed sanitized outputs from live third-party research."""

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ResearchGapCode = Literal[
    "provider_not_allowlisted",
    "tool_not_allowlisted",
    "schema_missing",
    "schema_malformed",
    "schema_not_allowlisted",
    "input_schema_unsupported",
    "payload_malformed",
    "payload_rejected",
    "payload_too_large",
    "payload_too_deep",
    "provider_error",
    "tool_error",
]


class ResearchItem(BaseModel):
    """One sanitized priority-6 keyword or market metric."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["keyword", "market_metric"]
    key: NonBlank
    value: NonBlank
    provider: NonBlank
    tool: NonBlank
    priority: Literal[6] = 6
    trusted: Literal[False] = False


class ResearchGap(BaseModel):
    """One safe reason an MCP result did not become authority data."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    code: ResearchGapCode
    provider: NonBlank
    tool: str = ""


class ToolNormalization(BaseModel):
    """Accepted items and explicit gaps from one tool result."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    items: tuple[ResearchItem, ...] = ()
    gaps: tuple[ResearchGap, ...] = ()


class ResearchBundle(BaseModel):
    """Sanitized research facts available to automatic optimization."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    items: tuple[ResearchItem, ...] = ()
    gaps: tuple[ResearchGap, ...] = ()
    allowed_keywords: tuple[NonBlank, ...] = ()


__all__ = [
    "ResearchBundle",
    "ResearchGap",
    "ResearchGapCode",
    "ResearchItem",
    "ToolNormalization",
]
