"""Creation pipeline smoke tests (mock) — gates + evidence."""

from __future__ import annotations

import json

from amazon_create.config import Settings
from amazon_create.mcp.live_research_call import _tool_arguments
from amazon_create.mcp.live_research_data import normalize_tool_payload
from amazon_create.pipeline.creation_pipeline import (
    apply_user_message,
    new_session,
    parse_brief_message,
    run_fast_path,
)
from amazon_create.pipeline.postflight import finalize_deliverable
from amazon_create.schemas.evidence import (
    EvidenceSourceKind,
    EvidenceTier,
    FactRow,
    FactStatus,
    authorize_copy_claims,
    merge_fact_rows,
)
from amazon_create.schemas.workflow import CreationStage
from pydantic import SecretStr


def test_parse_brief_ready() -> None:
    brief = parse_brief_message("产品: Hardware Cloth\n站点: US\n规格: 1/2 inch mesh")
    assert brief.is_ready
    assert brief.product_name == "Hardware Cloth"
    assert brief.marketplace == "US"
    assert any(r.fact == "mesh_opening" for r in brief.fact_ledger)


def test_fast_path_mock() -> None:
    settings = Settings(mock=True)
    session = new_session(fast_path=True)
    session.brief = parse_brief_message("产品: Hardware Cloth\n站点: US")
    session = run_fast_path(session, settings=settings)
    # fast path lands on image handoff when copy passes
    assert session.deliverable is not None
    d = session.deliverable
    assert d.title_chars <= 75
    assert d.item_highlights_chars <= 125
    assert d.search_terms_bytes <= 250
    assert len(d.bullets) == 5
    assert d.policy_status in {"PASS", "WARN", "BLOCK"}
    assert session.stage in {
        CreationStage.IMAGE_HANDOFF,
        CreationStage.FINAL_COPY,
        CreationStage.COMPLETED,
    }


def test_staged_approve_flow() -> None:
    settings = Settings(mock=True)
    session = new_session()
    session = apply_user_message(
        session,
        "产品: Mesh Zipper Pouch\n站点: US\n产品类型: document bag\n"
        "父子体: parent\n媒体类目: no\n规格: A4 mesh bag",
        settings=settings,
    )
    assert session.stage == CreationStage.AUDIENCE
    for _ in range(12):
        if session.stage == CreationStage.COMPLETED:
            break
        if session.stage == CreationStage.IMAGE_HANDOFF:
            session = apply_user_message(session, "不需要图片", settings=settings)
        else:
            session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.COMPLETED
    assert session.deliverable is not None
    assert session.image_design_requested is False


def test_image_handoff_yes() -> None:
    settings = Settings(mock=True)
    session = new_session()
    session = apply_user_message(
        session,
        "产品: Mesh Zipper Pouch\n站点: US\n产品类型: document bag\n"
        "父子体: parent\n媒体类目: no\n规格: A4",
        settings=settings,
    )
    for _ in range(14):
        if session.stage == CreationStage.IMAGE_HANDOFF:
            break
        session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.IMAGE_HANDOFF
    session = apply_user_message(session, "需要图片", settings=settings)
    assert session.stage == CreationStage.IMAGE_ANALYSIS
    assert session.image_design_requested is True
    session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.IMAGE_PLAN
    assert session.image_design_plan is not None
    assert len(session.image_design_plan.images) == 8
    session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.COMPLETED


def test_image_skip_from_final_copy() -> None:
    """不需要图片 should work from final_copy, not just image_handoff."""
    settings = Settings(mock=True)
    session = new_session()
    session = apply_user_message(
        session,
        "产品: Mesh Zipper Pouch\n站点: US\n产品类型: document bag\n"
        "父子体: parent\n媒体类目: no\n规格: A4",
        settings=settings,
    )
    for _ in range(14):
        if session.stage == CreationStage.FINAL_COPY:
            break
        session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.FINAL_COPY
    session = apply_user_message(session, "不需要图片", settings=settings)
    assert session.stage == CreationStage.COMPLETED
    assert session.image_design_requested is False


def test_finalize_clamps_title() -> None:
    long_title = "A" * 100
    d, auth = finalize_deliverable(
        {
            "title": long_title,
            "item_highlights": "Material and use case details for comparison",
            "bullets": [{"text": f"Bullet point number {i} with decision info"} for i in range(5)],
            "search_terms": "mesh pouch document bag classroom",
        }
    )
    assert d.title_chars <= 75
    assert auth.allowed is True


def test_finalize_highlights_list_to_string() -> None:
    """LLM may return item_highlights as a JSON array; must join to clean text."""
    d, _ = finalize_deliverable(
        {
            "title": "Test Product Title",
            "item_highlights": [
                "1/2 inch mesh opening for pest exclusion",
                "19 gauge galvanized steel",
                "48 inches wide x 100 feet long",
            ],
            "item_highlights_zh": ["网孔 1/2 英寸", "19 号镀锌钢"],
            "bullets": [{"text": f"Bullet {i}"} for i in range(5)],
            "search_terms": "mesh steel galvanized",
        }
    )
    assert "[" not in d.item_highlights
    assert "'" not in d.item_highlights
    assert "1/2 inch mesh opening" in d.item_highlights
    assert "19 gauge galvanized steel" in d.item_highlights
    assert "[" not in d.item_highlights_zh
    assert "网孔 1/2 英寸" in d.item_highlights_zh


def test_lower_tier_cannot_override_higher() -> None:
    high = FactRow(
        fact="material",
        value="steel",
        source_kind=EvidenceSourceKind.PRODUCT_CONFIRMED,
        status=FactStatus.VERIFIED,
    )
    low = FactRow(
        fact="material",
        value="plastic",
        source_kind=EvidenceSourceKind.COMPETITOR_PUBLIC,
        status=FactStatus.VERIFIED,
    )
    merged = merge_fact_rows((high,), low)
    assert len(merged) == 1
    assert merged[0].value == "steel"
    assert merged[0].tier == EvidenceTier.PRODUCT_CONFIRMED


def test_cert_without_evidence_blocks() -> None:
    auth = authorize_copy_claims(
        title="Steel Mesh UL Listed Barrier",
        item_highlights="For garden use",
        bullets=["Safe outdoor mesh"],
        ledger=(),
    )
    assert auth.allowed is False
    assert any("certification" in c for c in auth.blocked_claims)


def test_mock_keywords_stage_returns_keywords_payload() -> None:
    """Mock keywords stage must not fall through to final_copy payload."""
    from amazon_create.llm.mock import _stage_payload

    # Simulate the real user prompt which always contains "final_copy" in instructions
    prompt = (
        "stage:keywords\n"
        "stage_label:关键词与意图库\n"
        "brief:{}\n"
        "Respond with stage-appropriate JSON. "
        "For final_copy include title, title_zh, item_highlights, "
        "item_highlights_zh, bullets[{text,text_zh}], "
        "search_terms, unresolved[], notes_zh."
    )
    payload = _stage_payload(prompt)
    assert len(payload["top20_roots"]) == 20
    assert len(payload["top20_keywords"]) == 20
    assert "title" not in payload


def test_category_rules_are_loaded_for_matching_product() -> None:
    from amazon_create.rules import category_rule_names

    brief = parse_brief_message(
        "产品: Mesh Zipper Pouch\n站点: US\n产品类型: A4 document bag\n规格: A4"
    )
    assert "mesh-zipper-pouches.md" in category_rule_names(brief)


def test_extended_deliverable_fields_are_preserved() -> None:
    settings = Settings(mock=True)
    session = new_session(fast_path=True)
    session.brief = parse_brief_message(
        "产品: Hardware Cloth\n站点: US\n规格: material: galvanized steel"
    )
    session = run_fast_path(session, settings=settings)
    assert session.deliverable is not None
    assert session.deliverable.product_description
    assert session.deliverable.shopping_questions
    assert session.deliverable.a_plus_modules
    assert session.deliverable.keyword_intent_map
    assert session.deliverable.category_recommendations
    assert len(session.deliverable.title_variants) == 3
    assert len(session.deliverable.shopping_questions) == 10
    assert len(session.deliverable.final_report) == 20
    assert session.deliverable.upload_ready.title == session.deliverable.title


def test_sensitive_category_requires_human_review() -> None:
    settings = Settings(mock=True)
    session = new_session(fast_path=True)
    session.brief = parse_brief_message(
        "产品: Kids Squishy Toys\n站点: US\n产品类型: children party favors\n规格: count: 24"
    )
    session = run_fast_path(session, settings=settings)
    assert session.brief.sensitive_category is True
    assert session.stage == CreationStage.FINAL_COPY
    assert session.human_review_confirmed is False
    session = apply_user_message(session, "人工审核通过", settings=settings)
    assert session.human_review_confirmed is True
    assert session.stage == CreationStage.IMAGE_HANDOFF


def test_unsubstantiated_percentages_are_removed() -> None:
    from amazon_create.pipeline.creation_pipeline import _strip_unsubstantiated_percentages

    payload = {"audiences": [{"segment": "parents", "share": "53%"}]}
    cleaned = _strip_unsubstantiated_percentages(payload, {"market_metrics": []})
    assert "53%" not in str(cleaned)
    assert "未测量" in str(cleaned)


def test_marketplace_language_and_asins_are_parsed() -> None:
    brief = parse_brief_message(
        "产品: Mesh Zipper Pouch\n站点: 德国\n产品 ASIN: B012345678\n"
        "竞品: B087654321, B0ABCDEFGH\n父子体: child\n媒体类目: no\n"
        "变体属性: color: blue, size: A4"
    )
    assert brief.marketplace == "DE"
    assert brief.language == "de"
    assert brief.product_asin == "B012345678"
    assert brief.competitors == ("B087654321", "B0ABCDEFGH")
    assert brief.listing_scope == "child"
    assert brief.listing_scope_confirmed is True
    assert brief.media_status_confirmed is True
    assert brief.variation_values == {"color": "blue", "size": "A4"}


def test_parse_brief_does_not_treat_market_metric_label_as_marketplace() -> None:
    brief = parse_brief_message(
        "细分类目\nHanging Wall Files | SellerSprite,US,ASIN详情|\n"
        "核心市场词|'wall file organizer'|SIF关键词信号|"
    )

    assert brief.marketplace == ""
    assert brief.product_asin == ""


def test_sellersprite_nested_request_arguments_include_query_market_and_page() -> None:
    schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "request": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string"},
                        "marketplace": {"type": "string"},
                        "page": {"type": "integer"},
                        "size": {"type": "integer"},
                    },
                    "required": ["marketplace"],
                }
            },
            "required": ["request"],
        }
    )

    assert _tool_arguments(schema, "wall file organizer", marketplace="US") == {
        "request": {
            "keyword": "wall file organizer",
            "marketplace": "US",
            "page": 1,
            "size": 20,
        }
    }


def test_sellersprite_asin_and_keyword_payloads_are_structured() -> None:
    asin_payload = json.dumps(
        {
            "code": "OK",
            "data": {
                "asin": "B0FR8X1S8Y",
                "title": "Hanging Wall File Organizer",
                "brand": "ReePlan",
                "marketplace": "US",
                "price": 17.88,
                "rating": 4.4,
                "ratings": 361,
                "nodeLabelPath": "Office Products:Hanging Wall Files",
                "features": ["Five tiers", "Wall mounted"],
            },
        }
    )
    asin = normalize_tool_payload(
        provider="sellersprite",
        tool="asin_detail",
        output_schema_json="",
        payload_json=asin_payload,
    )
    attributes = {item.key: item.value for item in asin.items}
    assert attributes["asin"] == "B0FR8X1S8Y"
    assert attributes["brand"] == "ReePlan"
    assert attributes["node_label_path"] == "Office Products:Hanging Wall Files"

    keyword_payload = json.dumps(
        {
            "code": "OK",
            "data": {
                "items": [
                    {
                        "keyword": "wall file organizer",
                        "searches": 26601,
                        "monopolyClickRate": 18.5,
                        "products": 277,
                    }
                ]
            },
        }
    )
    keyword = normalize_tool_payload(
        provider="sellersprite",
        tool="keyword_miner",
        output_schema_json="",
        payload_json=keyword_payload,
    )
    values = {(item.kind, item.key): item.value for item in keyword.items}
    assert values[("keyword", "keyword")] == "wall file organizer"
    assert values[("market_metric", "wall file organizer:search_volume")] == "26601"
    assert values[("market_metric", "wall file organizer:product_count")] == "277"


def test_asin_identity_echoes_are_not_effective_product_data(monkeypatch) -> None:
    from amazon_create.config import Settings
    from amazon_create.mcp.live_research_types import ResearchBundle, ResearchItem
    from amazon_create.research_bridge import load_asin_research_context

    bundle = ResearchBundle(
        items=(
            ResearchItem(
                kind="product_attribute",
                key="asin",
                value="B0DSM0RXZK",
                provider="sellersprite",
                tool="asin_detail",
            ),
            ResearchItem(
                kind="product_attribute",
                key="marketplace",
                value="US",
                provider="sellersprite",
                tool="asin_detail",
            ),
        )
    )
    monkeypatch.setattr(
        "amazon_create.mcp.live_research.fetch_live_mcp_research_sync",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        "amazon_create.mcp.live_research.research_bundle_from_snapshots",
        lambda *_args, **_kwargs: bundle,
    )
    settings = Settings(MOCK=False, SELLERSPRITE_MCP_KEY="configured")

    result = load_asin_research_context(
        settings,
        asin="B0DSM0RXZK",
        marketplace="US",
    )

    assert result["mode"] == "degraded"
    assert "asin_no_effective_product_data" in result["gaps"]
    assert "无有效商品数据" in result["guidance"]


def test_asin_descriptive_attribute_is_effective_product_data(monkeypatch) -> None:
    from amazon_create.config import Settings
    from amazon_create.mcp.live_research_types import ResearchBundle, ResearchItem
    from amazon_create.research_bridge import load_asin_research_context

    bundle = ResearchBundle(
        items=(
            ResearchItem(
                kind="product_attribute",
                key="asin",
                value="B08N5WRWNW",
                provider="sellersprite",
                tool="asin_detail",
            ),
            ResearchItem(
                kind="product_attribute",
                key="brand",
                value="Apple",
                provider="sellersprite",
                tool="asin_detail",
            ),
        )
    )
    monkeypatch.setattr(
        "amazon_create.mcp.live_research.fetch_live_mcp_research_sync",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        "amazon_create.mcp.live_research.research_bundle_from_snapshots",
        lambda *_args, **_kwargs: bundle,
    )
    settings = Settings(MOCK=False, SELLERSPRITE_MCP_KEY="configured")

    result = load_asin_research_context(
        settings,
        asin="B08N5WRWNW",
        marketplace="US",
    )

    assert result["mode"] == "live"
    assert "asin_no_effective_product_data" not in result["gaps"]


def test_media_title_is_not_clamped_to_non_media_limit() -> None:
    title = "A" * 90
    deliverable, _ = finalize_deliverable(
        {
            "title": title,
            "item_highlights": "Verified media edition details",
            "bullets": [{"text": f"Bullet {i}"} for i in range(5)],
        },
        media_category=True,
    )
    assert deliverable.title == title
    assert "media_title_limit_requires_live_category_validator" in deliverable.unresolved
    assert deliverable.policy_status == "WARN"


def test_parent_title_blocks_child_variation_value() -> None:
    deliverable, _ = finalize_deliverable(
        {
            "title": "Brand Storage Pouch Blue",
            "item_highlights": "Mesh document storage for school and office",
            "bullets": [{"text": f"Bullet {i}"} for i in range(5)],
        },
        listing_scope="parent",
        variation_values={"color": "Blue"},
    )
    assert deliverable.policy_status == "BLOCK"
    assert any("parent title contains child" in issue for issue in deliverable.policy_issues)


def test_no_credentials_never_uses_fixture_market_data() -> None:
    from amazon_create.research_bridge import load_research_context

    research = load_research_context(
        Settings(
            mock=False,
            SELLERSPRITE_MCP_KEY=SecretStr(""),
            SORFTIME_MCP_KEY=SecretStr(""),
            SIF_MCP_KEY=SecretStr(""),
        ),
        product_name="Mesh Zipper Pouch",
        marketplace="UK",
        specs="A4",
    )
    assert research["mode"] == "unavailable"
    assert research["marketplace"] == "UK"
    assert research["allowed_keywords"] == []


def test_supporting_copy_is_evidence_scanned() -> None:
    deliverable, auth = finalize_deliverable(
        {
            "title": "Steel Garden Barrier",
            "item_highlights": "Outdoor project mesh",
            "bullets": [{"text": f"Bullet {i}"} for i in range(5)],
            "product_description": "This product is UL Listed for guaranteed safety",
        }
    )
    assert auth.allowed is False
    assert deliverable.policy_status == "BLOCK"


def test_brief_gate_requires_policy_context_fields() -> None:
    settings = Settings(mock=True)
    session = new_session()
    session = apply_user_message(session, "产品: Storage Pouch\n站点: US", settings=settings)
    session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.BRIEF
    assert "产品类型/类目" in session.last_message_zh
    assert "是否 media 类目" in session.last_message_zh
    assert "父体/子体范围" in session.last_message_zh


def test_image_task_type_is_preserved() -> None:
    settings = Settings(mock=True)
    session = new_session()
    session.stage = CreationStage.IMAGE_HANDOFF
    session = apply_user_message(session, "图片优化", settings=settings)
    assert session.image_task_type == "image_optimization"
    assert session.stage == CreationStage.IMAGE_ANALYSIS
