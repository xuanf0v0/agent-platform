"""Small, allowlisted MCP client and marketplace payload normalizer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import Settings
from .models import Candidate, Evidence, ResearchMode

TOOLS: dict[ResearchMode, tuple[str, ...]] = {
    ResearchMode.DISCOVER: (
        "search_categories_broadly",
        "category_search_from_top_node",
        "category_report",
        "category_trend",
        "category_keywords",
        "keyword_detail",
        "potential_product",
        "product_search",
        "ali1688_similar_product",
    ),
    ResearchMode.VALIDATE: (
        "category_search_from_product_name",
        "category_report",
        "category_trend",
        "keyword_detail",
        "product_search",
        "product_detail",
        "product_reviews",
        "product_trend",
        "ali1688_similar_product",
    ),
    ResearchMode.COMPARE: (
        "product_detail",
        "product_reviews",
        "product_trend",
        "product_variations",
        "competitor_product_keywords",
        "ali1688_similar_product",
    ),
}


def _with_key(url: str, key: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("key", key)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _arguments(schema: dict[str, Any], query: str, marketplace: str) -> dict[str, Any]:
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = schema.get("required", []) if isinstance(schema, dict) else []
    output: dict[str, Any] = {}
    for name in props:
        key = str(name).casefold()
        if key in {"market", "marketplace", "marketplace_id", "site"}:
            output[name] = marketplace
        elif key in {"query", "keyword", "keywords", "term", "product_name", "search_term", "text"}:
            output[name] = query
        elif key in {"asin", "asins", "product_id", "product_ids"}:
            tokens = [
                item.strip().upper() for item in query.replace(",", " ").split() if item.strip()
            ]
            output[name] = tokens if key.endswith("s") else (tokens[0] if tokens else query)
        elif key in {"limit", "page_size", "size", "top_n"}:
            output[name] = 100
        elif name in required:
            output[name] = query
    return output


def _content(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    if isinstance(result, dict) and result.get("structuredContent") is not None:
        return result["structuredContent"]
    blocks = result.get("content", []) if isinstance(result, dict) else []
    texts = [
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    text = "\n".join(item for item in texts if item)
    if not text:
        return result
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text[:10000]}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _pick(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def normalize_candidates(
    payloads: list[tuple[str, str, Any]], query: str
) -> tuple[list[Candidate], list[Evidence]]:
    candidates: list[Candidate] = []
    evidence: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    now = datetime.now(UTC).isoformat()
    for provider, tool, payload in payloads:
        for row in _walk(payload):
            title = _pick(row, "title", "product_title", "product_name", "name", "item_name")
            asin = str(_pick(row, "asin", "ASIN", "product_id") or "").upper()
            if not title and not asin:
                continue
            title = str(title or asin or query).strip()[:240]
            identity = (asin, title.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            evidence_id = f"{provider}:{tool}:{len(evidence)}"
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    provider=provider,
                    tool=tool,
                    claim=f"{title} returned by {tool}",
                    value={k: v for k, v in row.items() if isinstance(v, (str, int, float, bool))},
                    retrieved_at=now,
                )
            )
            candidates.append(
                Candidate(
                    asin=asin,
                    title=title,
                    category=str(_pick(row, "category", "category_name", "node_name") or ""),
                    price_usd=_number(
                        _pick(row, "price", "price_usd", "selling_price", "current_price")
                    ),
                    cost_usd=_number(
                        _pick(row, "cost", "cost_usd", "supplier_price", "purchase_price")
                    ),
                    monthly_search_volume=_number(
                        _pick(row, "search_volume", "monthly_search_volume", "volume", "demand")
                    ),
                    monthly_sales=_number(
                        _pick(row, "monthly_sales", "sales", "estimated_sales", "units")
                    ),
                    review_count=int(
                        _number(_pick(row, "review_count", "reviews", "number_of_reviews")) or 0
                    )
                    or None,
                    rating=_number(_pick(row, "rating", "stars", "review_rating")),
                    trend_pct=_number(_pick(row, "trend", "trend_pct", "growth", "growth_rate")),
                    top3_share_pct=_number(
                        _pick(row, "top3_share", "top_3_share", "brand_concentration")
                    ),
                    supplier_count=int(_number(_pick(row, "supplier_count", "suppliers")) or 0)
                    or None,
                    moq=int(_number(_pick(row, "moq", "minimum_order_quantity")) or 0) or None,
                    evidence_ids=[evidence_id],
                )
            )
            if len(candidates) >= 100:
                return candidates, evidence
    return candidates, evidence


async def collect_research(
    settings: Settings, *, mode: ResearchMode, query: str, marketplace: str
) -> tuple[list[Candidate], list[Evidence], list[str]]:
    providers = [
        ("sorftime", settings.sorftime_mcp_url, settings.sorftime_mcp_key.get_secret_value(), True)
    ]
    providers.extend(
        [
            (
                "sellersprite",
                settings.sellersprite_mcp_url,
                settings.sellersprite_mcp_key.get_secret_value(),
                False,
            ),
            ("sif", settings.sif_mcp_url, settings.sif_mcp_key.get_secret_value(), False),
        ]
    )
    configured = [(name, url, key, primary) for name, url, key, primary in providers if key]
    if not configured:
        raise RuntimeError(
            "共享配置中未找到 Sorftime、SellerSprite 或 SIF 密钥；"
            "请在 Listing 创作或 Listing 优化 Agent 中配置后重启选品 Agent"
        )
    payloads: list[tuple[str, str, Any]] = []
    gaps: list[str] = []
    for provider, base_url, key, primary in configured:
        url = _with_key(base_url, key) if provider == "sorftime" else base_url
        headers = {"secret-key": key} if provider != "sorftime" else {}
        try:
            async with (
                httpx.AsyncClient(
                    headers=headers,
                    follow_redirects=False,
                    trust_env=False,
                    timeout=settings.remote_mcp_timeout_seconds,
                ) as client,
                streamable_http_client(url, http_client=client) as streams,
                ClientSession(streams[0], streams[1]) as session,
            ):
                await session.initialize()
                listed = await session.list_tools()
                available = {tool.name: tool for tool in listed.tools}
                targets = [name for name in TOOLS[mode] if name in available]
                if not targets:
                    gaps.append(f"{provider}: 没有可用的选品工具")
                    continue
                for tool_name in targets[: settings.max_mcp_calls]:
                    tool = available[tool_name]
                    schema = getattr(tool, "inputSchema", {}) or {}
                    result = await session.call_tool(
                        tool_name, _arguments(schema, query, marketplace)
                    )
                    payloads.append((provider, tool_name, _content(result)))
        except Exception as exc:  # noqa: BLE001 -- provider failures become evidence gaps
            gaps.append(f"{provider}: {type(exc).__name__}")
            if primary and not payloads:
                continue
    candidates, evidence = normalize_candidates(payloads, query)
    if not candidates:
        gaps.append("没有从已配置数据源返回可识别的候选产品")
    return candidates, evidence, gaps
