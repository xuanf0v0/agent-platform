"""Schema-gated third-party keyword and market research data."""

from decimal import Decimal
import unicodedata
from itertools import pairwise
from typing import Annotated, ClassVar, Final, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from amazon_copy.mcp.live_research_types import (
    ResearchBundle,
    ResearchGap,
    ResearchGapCode,
    ResearchItem,
    ToolNormalization,
)
from amazon_copy.mcp.security import sanitize_mcp_json

_MAX_KEYWORD_CHARS: Final = 72
_MAX_KEYWORD_BYTES: Final = 144
_MAX_KEYWORD_TOKENS: Final = 8
_MAX_TOKEN_CHARS: Final = 24
_ALLOWED_PUNCTUATION: Final = frozenset(" &+'-")
_TOKEN_TRANSLATION: Final = str.maketrans("&+'-", "    ")
_URL_MARKERS: Final = ("://", "www.", "mailto:", "data:")
_LEET_TRANSLATION: Final = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}
)
_FORBIDDEN_TOKENS: Final = frozenset(
    {
        "apikey",
        "authorization",
        "bearer",
        "bypass",
        "cookie",
        "credential",
        "credentials",
        "direction",
        "directions",
        "disclose",
        "disregard",
        "execute",
        "exfiltrate",
        "forget",
        "ignore",
        "instruction",
        "instructions",
        "jailbreak",
        "obey",
        "override",
        "passcode",
        "password",
        "passwords",
        "prompt",
        "prompts",
        "reveal",
        "rule",
        "rules",
        "secret",
        "secrets",
        "token",
        "tokens",
    }
)
_FORBIDDEN_TOKEN_PAIRS: Final = frozenset(
    {
        ("api", "key"),
        ("developer", "message"),
        ("internal", "context"),
        ("output", "internal"),
        ("system", "prompt"),
    }
)


def _allowed_character(char: str) -> bool:
    return char in _ALLOWED_PUNCTUATION or unicodedata.category(char)[0] in {"L", "M", "N"}


def parse_marketplace_keyword(raw: str | None) -> str | None:
    """Return one bounded product-search term, rejecting instruction-shaped text."""
    if raw is None:
        return None
    normalized = " ".join(
        unicodedata.normalize("NFKC", raw)
        .replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        .split()
    )
    if (
        not normalized
        or len(normalized) > _MAX_KEYWORD_CHARS
        or len(normalized.encode("utf-8")) > _MAX_KEYWORD_BYTES
        or any(marker in normalized.casefold() for marker in _URL_MARKERS)
        or any(not _allowed_character(char) for char in normalized)
    ):
        return None
    tokens = normalized.casefold().translate(_TOKEN_TRANSLATION).split()
    if (
        not tokens
        or len(tokens) > _MAX_KEYWORD_TOKENS
        or any(len(token) > _MAX_TOKEN_CHARS for token in tokens)
        or any(token.translate(_LEET_TRANSLATION) in _FORBIDDEN_TOKENS for token in tokens)
        or any(pair in _FORBIDDEN_TOKEN_PAIRS for pair in pairwise(tokens))
    ):
        return None
    return normalized


_PROVIDERS: Final = frozenset({"sellersprite", "sorftime", "sif"})
_TOOLS: Final = frozenset(
    {
        "google_trend",
        "keyword_miner",
        "keyword_related",
        "keyword_research",
        "potential_product",
        "product_research",
        "related_keyword",
        # SIF market-domain keyword tools (called without tools/list).
        "market_get_keyword_demand",
        "market_get_keyword_competition",
        "market_screen_keyword_opportunities",
        "market_get_keyword_root_trend",
    }
)
_KEYWORD_FIELDS: Final = frozenset(
    {"keyword", "keywords", "query", "related_keyword", "related_keywords", "term"}
)
_METRIC_FIELDS: Final = frozenset(
    {
        "competition",
        "cpc",
        "demand",
        "monthly_search_volume",
        "popularity",
        "product_count",
        "search_volume",
        "volume",
    }
)
_ALLOWED_SCHEMA_FIELDS: Final = _KEYWORD_FIELDS | _METRIC_FIELDS
_MarketMetric: TypeAlias = Annotated[  # noqa: UP040 -- Python 3.11 compatibility
    Decimal,
    Field(ge=0, le=1_000_000_000_000),
]


class _SchemaNode(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    properties: dict[str, "_SchemaNode"] = Field(default_factory=dict)
    items: "_SchemaNode | None" = None


class _ResearchRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="ignore",
        allow_inf_nan=False,
    )

    keyword: str | None = None
    keywords: tuple[str, ...] = ()
    query: str | None = None
    related_keyword: str | None = None
    related_keywords: tuple[str, ...] = ()
    term: str | None = None
    keyword_root: str | None = None
    competition: _MarketMetric | None = None
    cpc: _MarketMetric | None = None
    demand: _MarketMetric | None = None
    monthly_search_volume: _MarketMetric | None = None
    popularity: _MarketMetric | None = None
    product_count: _MarketMetric | None = None
    search_volume: _MarketMetric | None = None
    volume: _MarketMetric | None = None
    data: tuple["_ResearchRecord", ...] = ()
    items: tuple["_ResearchRecord", ...] = ()
    results: tuple["_ResearchRecord", ...] = ()
    profiles: tuple["_ResearchRecord", ...] = ()
    current: "_ResearchRecord | None" = None


_Payload: TypeAlias = _ResearchRecord | tuple[_ResearchRecord, ...]  # noqa: UP040 -- Python 3.11 compatibility
_PAYLOAD_ADAPTER: Final[TypeAdapter[_Payload]] = TypeAdapter(
    _ResearchRecord | tuple[_ResearchRecord, ...]
)


def _gap(code: ResearchGapCode, provider: str, tool: str) -> ToolNormalization:
    return ToolNormalization(gaps=(ResearchGap(code=code, provider=provider, tool=tool),))


def _schema_field_names(node: _SchemaNode) -> frozenset[str]:
    names = set(node.properties)
    for child in node.properties.values():
        names.update(_schema_field_names(child))
    if node.items is not None:
        names.update(_schema_field_names(node.items))
    return frozenset(names)


def _schema_gap(output_schema_json: str) -> ResearchGapCode | None:
    if not output_schema_json.strip():
        return "schema_missing"
    payload = sanitize_mcp_json(output_schema_json)
    if payload is None or payload.limit_code is not None:
        return "schema_malformed"
    try:
        schema = _SchemaNode.model_validate(payload.value)
    except ValidationError:
        return "schema_malformed"
    if not (_schema_field_names(schema) & _ALLOWED_SCHEMA_FIELDS):
        return "schema_not_allowlisted"
    return None


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _flatten(payload: _Payload) -> tuple[_ResearchRecord, ...]:
    match payload:
        case _ResearchRecord() as record:
            nested = (
                *record.data,
                *record.items,
                *record.results,
                *record.profiles,
                *((record.current,) if record.current is not None else ()),
            )
            return (record, *(child for item in nested for child in _flatten(item)))
        case tuple() as records:
            return tuple(child for item in records for child in _flatten(item))


def _items(payload: _Payload, provider: str, tool: str) -> tuple[ResearchItem, ...]:
    accepted: list[ResearchItem] = []
    for record in _flatten(payload):
        keyword_values = (
            record.keyword,
            *record.keywords,
            record.query,
            record.related_keyword,
            *record.related_keywords,
            record.term,
            record.keyword_root,
        )
        for raw in keyword_values:
            value = parse_marketplace_keyword(raw)
            if value is not None:
                accepted.append(
                    ResearchItem(
                        kind="keyword",
                        key="keyword",
                        value=value,
                        provider=provider,
                        tool=tool,
                    )
                )
        metrics = (
            ("competition", record.competition),
            ("cpc", record.cpc),
            ("demand", record.demand),
            ("monthly_search_volume", record.monthly_search_volume),
            ("popularity", record.popularity),
            ("product_count", record.product_count),
            ("search_volume", record.search_volume),
            ("volume", record.volume),
        )
        for key, value in metrics:
            if value is not None:
                accepted.append(
                    ResearchItem(
                        kind="market_metric",
                        key=key,
                        value=_decimal_text(value),
                        provider=provider,
                        tool=tool,
                    )
                )
    return tuple(
        {
            (item.kind, item.key, item.value.casefold(), item.provider, item.tool): item
            for item in accepted
        }.values()
    )


def normalize_tool_payload(
    *,
    provider: str,
    tool: str,
    output_schema_json: str,
    payload_json: str,
) -> ToolNormalization:
    """Accept only declared keyword/market fields from known MCP tools."""
    provider_name = provider.casefold().strip()
    tool_name = tool.casefold().strip()
    gap_code: ResearchGapCode | None = None
    payload_value: _Payload | None = None
    if provider_name not in _PROVIDERS:
        gap_code = "provider_not_allowlisted"
        provider_name = provider_name or "unknown"
    elif tool_name not in _TOOLS:
        gap_code = "tool_not_allowlisted"
    # Empty output schema is allowed only for SIF direct-call tools (no tools/list).
    elif (
        not output_schema_json.strip()
        and provider_name != "sif"
        and (schema_gap := _schema_gap(output_schema_json))
    ):
        gap_code = schema_gap
    elif output_schema_json.strip() and (schema_gap := _schema_gap(output_schema_json)):
        gap_code = schema_gap
    else:
        payload = sanitize_mcp_json(payload_json)
        if payload is None:
            gap_code = "payload_malformed"
        elif payload.limit_code is not None:
            gap_code = payload.limit_code
        else:
            try:
                payload_value = _PAYLOAD_ADAPTER.validate_python(payload.value)
            except ValidationError:
                gap_code = "payload_malformed"
    if gap_code is not None:
        return _gap(gap_code, provider_name, tool_name)
    if payload_value is None:
        return _gap("payload_malformed", provider_name, tool_name)
    items = _items(payload_value, provider_name, tool_name)
    if not items:
        return _gap("payload_rejected", provider_name, tool_name)
    return ToolNormalization(items=items)


def build_research_bundle(
    normalizations: tuple[ToolNormalization, ...],
) -> ResearchBundle:
    """Combine tool results with stable deduplication and keyword order."""
    items = tuple(item for result in normalizations for item in result.items)
    gaps = tuple(gap for result in normalizations for gap in result.gaps)
    unique_items = tuple(
        {
            (item.kind, item.key, item.value.casefold(), item.provider, item.tool): item
            for item in items
        }.values()
    )
    keywords = tuple(
        {
            item.value.casefold(): item.value for item in unique_items if item.kind == "keyword"
        }.values()
    )
    return ResearchBundle(items=unique_items, gaps=gaps, allowed_keywords=keywords)


__all__ = [
    "ResearchBundle",
    "ResearchGap",
    "ResearchItem",
    "ToolNormalization",
    "build_research_bundle",
    "normalize_tool_payload",
]
