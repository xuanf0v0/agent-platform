"""Allowlisted normalization for third-party Amazon research data."""

import json
import re
from decimal import Decimal
from typing import Annotated, ClassVar, Final, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from amazon_create.mcp.live_research_types import (
    ResearchBundle,
    ResearchGap,
    ResearchGapCode,
    ResearchItem,
    ToolNormalization,
)
from amazon_create.mcp.marketplace_keyword import parse_marketplace_keyword
from amazon_create.mcp.security import sanitize_mcp_json

_PROVIDERS: Final = frozenset({"sellersprite", "sorftime", "sif"})
_TOOLS: Final = frozenset(
    {
        "google_trend",
        "keyword_miner",
        "keyword_related",
        "keyword_research",
        "potential_product",
        "product_research",
        "asin_detail",
        "product_node",
        "related_keyword",
        # SIF market-domain keyword tools (called without tools/list).
        "market_get_keyword_demand",
        "market_get_keyword_competition",
        "market_screen_keyword_opportunities",
        "market_get_keyword_root_trend",
    }
)
_SCHEMALESS_TOOLS: Final = frozenset(
    {
        ("sellersprite", "asin_detail"),
        ("sellersprite", "product_node"),
        ("sellersprite", "keyword_miner"),
        ("sellersprite", "keyword_research"),
        ("sellersprite", "product_research"),
        ("sellersprite", "google_trend"),
        ("sif", "market_get_keyword_demand"),
        ("sif", "market_get_keyword_competition"),
        ("sif", "market_screen_keyword_opportunities"),
        ("sif", "market_get_keyword_root_trend"),
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
_SELLER_METRIC_FIELDS: Final[dict[str, str]] = {
    "searches": "search_volume",
    "search_volume": "search_volume",
    "monthly_search_volume": "monthly_search_volume",
    "purchases": "purchases",
    "purchase_rate": "purchase_rate",
    "purchaserate": "purchase_rate",
    "monopoly_click_rate": "top_click_concentration",
    "monopolyclickrate": "top_click_concentration",
    "products": "product_count",
    "product_count": "product_count",
    "supply_demand_ratio": "supply_demand_ratio",
    "supplydemandratio": "supply_demand_ratio",
    "avg_price": "average_price",
    "avgprice": "average_price",
    "bid": "bid",
    "cpc": "cpc",
    "competition": "competition",
    "demand": "demand",
    "volume": "volume",
}
_ASIN_FIELDS: Final[tuple[str, ...]] = (
    "asin",
    "title",
    "brand",
    "marketplace",
    "parent",
    "price",
    "rating",
    "ratings",
    "dimensions",
    "weight",
    "nodeId",
    "nodeIdPath",
    "nodeLabelPath",
    "variations",
    "features",
    "overviews",
    "subcategories",
    "variationList",
)
_KEYWORD_RESPONSE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "keyword",
        "keywords",
        "term",
        "query",
        "keyword_root",
        "month",
        "searches",
        "search_volume",
        "monthly_search_volume",
        "purchases",
        "purchaseRate",
        "purchase_rate",
        "monopolyClickRate",
        "monopoly_click_rate",
        "products",
        "product_count",
        "supplyDemandRatio",
        "supply_demand_ratio",
        "avgPrice",
        "avg_price",
        "bid",
        "cpc",
        "competition",
        "demand",
        "volume",
        "relevancy",
        "searchRank",
    }
)
_MarketMetric: TypeAlias = Annotated[
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


_Payload: TypeAlias = _ResearchRecord | tuple[_ResearchRecord, ...]
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


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).casefold()


def _item_value(value: object, *, limit: int = 4000) -> str:
    if isinstance(value, str):
        rendered = value.strip()
    elif isinstance(value, bool) or value is None:
        return ""
    elif isinstance(value, (int, float, Decimal)):
        rendered = str(value)
    elif isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        return ""
    return rendered[:limit]


def _walk_dicts(value: object, *, limit: int = 256) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    stack = [value]
    while stack and len(rows) < limit:
        current = stack.pop()
        if isinstance(current, dict):
            rows.append(current)
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))
    return tuple(rows)


def compact_tool_payload(provider: str, tool: str, value: object) -> object:
    """Trim reviewed provider payloads before enforcing the shared byte boundary."""
    if provider != "sellersprite" or not isinstance(value, dict):
        return value
    data = value.get("data")
    envelope = {key: value[key] for key in ("code", "message") if key in value}
    if tool == "asin_detail" and isinstance(data, dict):
        envelope["data"] = {key: data[key] for key in _ASIN_FIELDS if key in data}
        return envelope
    if tool == "product_node" and isinstance(data, list):
        envelope["data"] = [
            {
                key: row[key]
                for key in ("nodeIdPath", "nodeLabelPath", "nodeLabelPathLocale", "products")
                if key in row
            }
            for row in data[:24]
            if isinstance(row, dict)
        ]
        return envelope
    if tool in {"keyword_miner", "keyword_research"} and isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            envelope["data"] = {
                "items": [
                    {key: item[key] for key in _KEYWORD_RESPONSE_FIELDS if key in item}
                    for item in items[:8]
                    if isinstance(item, dict)
                ]
            }
            return envelope
    return value


def _metric_item(
    *,
    key: str,
    value: object,
    provider: str,
    tool: str,
) -> ResearchItem | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        return None
    try:
        decimal = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None
    if not decimal.is_finite() or decimal < 0 or decimal > Decimal(1000000000000):
        return None
    return ResearchItem(
        kind="market_metric",
        key=key,
        value=_decimal_text(decimal),
        provider=provider,
        tool=tool,
    )


def _keyword_market_items(
    payload: object,
    *,
    provider: str,
    tool: str,
) -> tuple[ResearchItem, ...]:
    accepted: list[ResearchItem] = []
    for record in _walk_dicts(payload):
        raw_keyword = next(
            (
                record.get(name)
                for name in ("keyword", "keywords", "term", "query", "keyword_root")
                if isinstance(record.get(name), str)
            ),
            None,
        )
        keyword = parse_marketplace_keyword(raw_keyword)
        if keyword:
            accepted.append(
                ResearchItem(
                    kind="keyword",
                    key="keyword",
                    value=keyword,
                    provider=provider,
                    tool=tool,
                )
            )
        for raw_key, value in record.items():
            canonical = _SELLER_METRIC_FIELDS.get(_snake_case(raw_key))
            if canonical is None:
                canonical = _SELLER_METRIC_FIELDS.get(raw_key.casefold())
            if canonical is None:
                continue
            metric_key = f"{keyword}:{canonical}" if keyword else canonical
            metric = _metric_item(
                key=metric_key,
                value=value,
                provider=provider,
                tool=tool,
            )
            if metric is not None:
                accepted.append(metric)
        if len(accepted) >= 40:
            break
    return tuple(accepted[:40])


def _asin_detail_items(
    payload: object,
    *,
    provider: str,
    tool: str,
) -> tuple[ResearchItem, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return ()
    if str(payload.get("code") or "").upper() not in {"", "OK"}:
        return ()
    data = payload["data"]
    asin = _item_value(data.get("asin"))
    if len(asin) != 10:
        return ()
    items: list[ResearchItem] = []
    for field in _ASIN_FIELDS:
        value = _item_value(data.get(field))
        if not value:
            continue
        items.append(
            ResearchItem(
                kind="product_attribute",
                key=_snake_case(field),
                value=value,
                provider=provider,
                tool=tool,
            )
        )
    return tuple(items)


def _category_items(
    payload: object,
    *,
    provider: str,
    tool: str,
) -> tuple[ResearchItem, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return ()
    accepted: list[ResearchItem] = []
    for row in payload["data"][:24]:
        if not isinstance(row, dict):
            continue
        compact = {
            key: row[key]
            for key in ("nodeIdPath", "nodeLabelPath", "nodeLabelPathLocale", "products")
            if row.get(key) not in {None, ""}
        }
        value = _item_value(compact, limit=1200)
        if value:
            accepted.append(
                ResearchItem(
                    kind="category_candidate",
                    key="browse_node_candidate",
                    value=value,
                    provider=provider,
                    tool=tool,
                )
            )
    return tuple(accepted)


def _schemaless_items(
    payload: object,
    *,
    provider: str,
    tool: str,
) -> tuple[ResearchItem, ...]:
    if tool == "asin_detail":
        return _asin_detail_items(payload, provider=provider, tool=tool)
    if tool == "product_node":
        return _category_items(payload, provider=provider, tool=tool)
    return _keyword_market_items(payload, provider=provider, tool=tool)


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
    elif not output_schema_json.strip() and (provider_name, tool_name) in _SCHEMALESS_TOOLS:
        payload = sanitize_mcp_json(payload_json)
        if payload is None:
            gap_code = "payload_malformed"
        elif payload.limit_code is not None:
            gap_code = payload.limit_code
        else:
            items = _schemaless_items(
                payload.value,
                provider=provider_name,
                tool=tool_name,
            )
            return ToolNormalization(items=items) if items else _gap(
                "payload_rejected", provider_name, tool_name
            )
    elif schema_gap := _schema_gap(output_schema_json):
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
    "compact_tool_payload",
    "normalize_tool_payload",
]
