"""Creation pipeline smoke tests (mock) — gates + evidence."""

from __future__ import annotations

from amazon_create.config import Settings
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
        "产品: Mesh Zipper Pouch\n站点: US\n规格: A4 mesh bag",
        settings=settings,
    )
    assert session.stage == CreationStage.BRIEF
    session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.AUDIENCE
    for _ in range(12):
        if session.stage == CreationStage.COMPLETED:
            break
        if session.stage == CreationStage.COMPETITOR:
            session = apply_user_message(session, "跳过竞品", settings=settings)
        elif session.stage == CreationStage.IMAGE_HANDOFF:
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
        "产品: Mesh Zipper Pouch\n站点: US\n规格: A4",
        settings=settings,
    )
    for _ in range(14):
        if session.stage == CreationStage.IMAGE_HANDOFF:
            break
        if session.stage == CreationStage.COMPETITOR:
            session = apply_user_message(session, "跳过竞品", settings=settings)
        else:
            session = apply_user_message(session, "认可", settings=settings)
    assert session.stage == CreationStage.IMAGE_HANDOFF
    session = apply_user_message(session, "需要图片", settings=settings)
    assert session.stage == CreationStage.COMPLETED
    assert session.image_design_requested is True


def test_image_skip_from_final_copy() -> None:
    """不需要图片 should work from final_copy, not just image_handoff."""
    settings = Settings(mock=True)
    session = new_session()
    session = apply_user_message(
        session,
        "产品: Mesh Zipper Pouch\n站点: US\n规格: A4",
        settings=settings,
    )
    for _ in range(14):
        if session.stage == CreationStage.FINAL_COPY:
            break
        if session.stage == CreationStage.COMPETITOR:
            session = apply_user_message(session, "跳过竞品", settings=settings)
        else:
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
    assert "core_keywords" in payload
    assert "title" not in payload
