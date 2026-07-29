"""One schema-gated best-effort MCP tool call."""

import json
from dataclasses import dataclass
from typing import ClassVar, Final

from mcp.shared.exceptions import McpError
from mcp.types import Tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amazon_copy.mcp.live_research_data import normalize_tool_payload
from amazon_copy.mcp.live_research_models import McpCallRecord, content_to_text, sanitize_text
from amazon_copy.mcp.live_research_types import ResearchGap, ToolNormalization
from amazon_copy.mcp.security import sanitize_mcp_payload
from mcp import ClientSession

_DEFAULT_MARKETPLACE: Final = "US"
_QUERY_FIELDS: Final = (
    "keyword",
    "query",
    "keywords",
    "keyword_root",
    "q",
    "search",
    "asin",
)
_MARKET_FIELDS: Final = ("marketplace", "market", "country")
_SIF_TOOL_ARGUMENTS: Final[dict[str, tuple[str, ...]]] = {
    "market_get_keyword_demand": ("keywords", "country"),
    "market_get_keyword_competition": ("keyword", "country"),
    "market_screen_keyword_opportunities": ("keyword_root", "country"),
    "market_get_keyword_root_trend": ("keyword", "country"),
}


class _SchemaProperty(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    value_type: str | tuple[str, ...] | None = Field(default=None, alias="type")
    enum: tuple[str, ...] = ()


class _InputSchema(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    value_type: str | None = Field(default=None, alias="type")
    properties: dict[str, _SchemaProperty] = Field(default_factory=dict)
    required: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolCallSpec:
    """Provider, schema, query, and redaction inputs for one tool."""

    provider: str
    tool_name: str
    query: str
    input_schema_json: str
    output_schema_json: str
    secrets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolCallOutcome:
    """Legacy display call plus normalized authority data."""

    call: McpCallRecord
    normalization: ToolNormalization


def _accepts_string(prop: _SchemaProperty) -> bool:
    match prop.value_type:
        case None | "string":
            return True
        case tuple() as value_types:
            return "string" in value_types
        case _:
            return False


def _accepts_string_or_array(prop: _SchemaProperty) -> bool:
    match prop.value_type:
        case None | "string" | "array":
            return True
        case tuple() as value_types:
            return bool({"string", "array"} & set(value_types))
        case _:
            return False


def _first_supported_field(
    candidates: tuple[str, ...],
    schema: _InputSchema,
    *,
    allow_array: bool = False,
) -> str | None:
    accepts = _accepts_string_or_array if allow_array else _accepts_string
    required = frozenset(schema.required)
    return next(
        (
            name
            for name in candidates
            if name in required
            and name in schema.properties
            and accepts(schema.properties[name])
        ),
        next(
            (
                name
                for name in candidates
                if name in schema.properties and accepts(schema.properties[name])
            ),
            None,
        ),
    )


def builtin_tool_arguments(
    provider: str,
    tool_name: str,
    query: str,
) -> dict[str, object] | None:
    """Arguments for known providers when tools/list schemas are unavailable."""
    if provider != "sif" or tool_name not in _SIF_TOOL_ARGUMENTS:
        return None
    fields = _SIF_TOOL_ARGUMENTS[tool_name]
    arguments: dict[str, object] = {}
    for field in fields:
        if field == "keywords":
            arguments[field] = [query]
        elif field == "keyword":
            arguments[field] = query
        elif field == "keyword_root":
            # Prefer a short root (first 2-3 words) for opportunity screening.
            words = [part for part in query.split() if part]
            arguments[field] = " ".join(words[:3]) if words else query
        elif field == "country":
            arguments[field] = _DEFAULT_MARKETPLACE
    return arguments


def _tool_arguments(
    input_schema_json: str,
    query: str,
    *,
    provider: str = "",
    tool_name: str = "",
) -> dict[str, object] | None:
    if not input_schema_json.strip():
        # SIF skips tools/list and needs built-in args; other providers keep {}.
        builtin = builtin_tool_arguments(provider, tool_name, query)
        return builtin if builtin is not None else {}
    try:
        schema = _InputSchema.model_validate_json(input_schema_json)
    except ValidationError:
        builtin = builtin_tool_arguments(provider, tool_name, query)
        return builtin if builtin is not None else None
    if schema.value_type not in {None, "object"}:
        return None
    query_field = _first_supported_field(_QUERY_FIELDS, schema, allow_array=True)
    market_field = _first_supported_field(_MARKET_FIELDS, schema)
    supported = {field for field in (query_field, market_field) if field is not None}
    if any(required not in supported for required in schema.required):
        builtin = builtin_tool_arguments(provider, tool_name, query)
        return builtin if builtin is not None else None
    arguments: dict[str, object] = {}
    if query_field is not None:
        prop = schema.properties[query_field]
        if prop.value_type == "array" or (
            isinstance(prop.value_type, tuple) and "array" in prop.value_type
        ):
            arguments[query_field] = [query]
        else:
            arguments[query_field] = query
    if market_field is not None:
        market_property = schema.properties[market_field]
        if market_property.enum and _DEFAULT_MARKETPLACE not in market_property.enum:
            return None
        arguments[market_field] = _DEFAULT_MARKETPLACE
    return arguments


async def call_tool_best_effort(
    session: ClientSession,
    spec: ToolCallSpec,
) -> ToolCallOutcome:
    """Dispatch once with schema-derived arguments and normalize the result."""
    arguments = _tool_arguments(
        spec.input_schema_json,
        spec.query,
        provider=spec.provider,
        tool_name=spec.tool_name,
    )
    if arguments is None:
        return ToolCallOutcome(
            call=McpCallRecord(
                tool=spec.tool_name,
                ok=False,
                summary_text="unsupported input schema",
            ),
            normalization=ToolNormalization(
                gaps=(
                    ResearchGap(
                        code="input_schema_unsupported",
                        provider=spec.provider,
                        tool=spec.tool_name,
                    ),
                )
            ),
        )
    try:
        result = await session.call_tool(spec.tool_name, arguments=arguments)
        result_text = content_to_text(result)
        summary = sanitize_text(result_text, spec.secrets) or "(empty result)"
        payload = sanitize_mcp_payload(
            result.structuredContent if result.structuredContent is not None else result_text,
            spec.secrets,
        )
        if payload.limit_code is not None:
            normalization = ToolNormalization(
                gaps=(
                    ResearchGap(
                        code=payload.limit_code,
                        provider=spec.provider,
                        tool=spec.tool_name,
                    ),
                )
            )
        else:
            payload_json = (
                payload.value
                if isinstance(payload.value, str)
                else json.dumps(
                    payload.value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            # SIF text content is often a JSON string envelope.
            if isinstance(payload.value, str):
                try:
                    nested = json.loads(payload.value)
                except json.JSONDecodeError:
                    nested = None
                if isinstance(nested, (dict, list)):
                    payload_json = json.dumps(nested, ensure_ascii=False, separators=(",", ":"))
            normalization = normalize_tool_payload(
                provider=spec.provider,
                tool=spec.tool_name,
                output_schema_json=spec.output_schema_json,
                payload_json=payload_json,
            )
        return ToolCallOutcome(
            call=McpCallRecord(tool=spec.tool_name, ok=True, summary_text=summary),
            normalization=normalization,
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        error = sanitize_text(str(exc) or type(exc).__name__, spec.secrets)
    except (ExceptionGroup, McpError) as exc:
        error = sanitize_text(str(exc) or type(exc).__name__, spec.secrets)
    return ToolCallOutcome(
        call=McpCallRecord(tool=spec.tool_name, ok=False, summary_text=error),
        normalization=ToolNormalization(
            gaps=(ResearchGap(code="tool_error", provider=spec.provider, tool=spec.tool_name),)
        ),
    )


def input_schema_json(tool: Tool) -> str:
    """Serialize a declared input schema within MCP payload limits."""
    return _schema_json(getattr(tool, "inputSchema", None))


def output_schema_json(tool: Tool) -> str:
    """Serialize a declared output schema without provider metadata."""
    return _schema_json(tool.outputSchema)


def _schema_json(schema: object) -> str:
    if schema is None:
        return ""
    payload = sanitize_mcp_payload(schema)
    if payload.value is None:
        return ""
    return json.dumps(payload.value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "ToolCallOutcome",
    "ToolCallSpec",
    "builtin_tool_arguments",
    "call_tool_best_effort",
    "input_schema_json",
    "output_schema_json",
]
