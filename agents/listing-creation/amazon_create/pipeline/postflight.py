"""Clamp, lint, and evidence-authorize final creation deliverable."""

from __future__ import annotations

import re

from amazon_create.compliance.lint_bridge import lint_deliverable
from amazon_create.compliance.paste_ready import (
    PASTE_ITEM_HIGHLIGHTS_MAX,
    clamp_paste_ready_lengths,
    clamp_plain_text,
)
from amazon_create.schemas.deliverable import (
    BulletDeliverable,
    CategoryRecommendation,
    ClaimEvidenceMap,
    CreationDeliverable,
    PlusModule,
    RiskItem,
    ShoppingQuestion,
    TitleVariant,
    UploadReadyCopy,
)
from amazon_create.schemas.evidence import (
    ClaimAuthorizationResult,
    FactRow,
    authorize_copy_claims,
)
from amazon_create.utils.text_metrics import plain_len, strip_md_bold


def _coerce_text(value: object) -> str:
    """Coerce a raw LLM field to clean text, joining lists with ', '."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value or "")


def _coerce_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _coerce_question_list(value: object) -> list[ShoppingQuestion]:
    if not isinstance(value, list):
        return []
    questions: list[ShoppingQuestion] = []
    for item in value[:12]:
        if not isinstance(item, dict) or not str(item.get("question") or "").strip():
            continue
        questions.append(ShoppingQuestion.model_validate(item))
    return questions


def _coerce_plus_modules(value: object) -> list[PlusModule]:
    if not isinstance(value, list):
        return []
    modules: list[PlusModule] = []
    for item in value[:10]:
        if not isinstance(item, dict) or not str(item.get("module") or "").strip():
            continue
        modules.append(PlusModule.model_validate(item))
    return modules


def _coerce_categories(value: object) -> list[CategoryRecommendation]:
    if not isinstance(value, list):
        return []
    categories: list[CategoryRecommendation] = []
    for item in value[:6]:
        if not isinstance(item, dict) or not str(item.get("path") or "").strip():
            continue
        categories.append(
            CategoryRecommendation.model_validate(
                {**item, "verification": "manual_validation_required"}
            )
        )
    return categories


def _coerce_claim_map(value: object) -> list[ClaimEvidenceMap]:
    if not isinstance(value, list):
        return []
    rows: list[ClaimEvidenceMap] = []
    for item in value[:30]:
        if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
            continue
        rows.append(ClaimEvidenceMap.model_validate(item))
    return rows


def _coerce_keyword_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, items in value.items():
        if isinstance(items, list):
            result[str(key)] = [str(item).strip() for item in items if str(item).strip()]
    return result


def _coerce_risks(value: object) -> list[RiskItem]:
    if not isinstance(value, list):
        return []
    risks: list[RiskItem] = []
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        normalized = {
            "risk_type": str(item.get("risk_type") or item.get("type") or "未分类风险"),
            "issue": str(item.get("issue") or item.get("problem") or "待确认"),
            "level": str(item.get("level") or "中"),
            "recommended_location": str(
                item.get("recommended_location") or item.get("placement") or "Product Description"
            ),
            "needs_confirmation": bool(item.get("needs_confirmation", False)),
        }
        if normalized["level"] not in {"低", "中", "高", "BLOCK"}:
            normalized["level"] = "中"
        risks.append(RiskItem.model_validate(normalized))
    return risks


def _coerce_title_variants(
    raw: dict[str, object],
    *,
    media_category: bool,
) -> list[TitleVariant]:
    value = raw.get("title_variants")
    variants: list[TitleVariant] = []
    if isinstance(value, list):
        for index, item in enumerate(value[:3]):
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "ABC"[index]).upper()
            if code not in {"A", "B", "C"}:
                code = "ABC"[index]
            title = strip_md_bold(_coerce_text(item.get("title"))).strip()
            highlights = strip_md_bold(_coerce_text(item.get("item_highlights"))).strip()
            if media_category:
                highlights = clamp_plain_text(highlights, PASTE_ITEM_HIGHLIGHTS_MAX)
            else:
                title, highlights = clamp_paste_ready_lengths(title, highlights)
            if not title or not highlights:
                continue
            variants.append(
                TitleVariant(
                    code=code,
                    strategy_zh=str(item.get("strategy_zh") or f"版本 {code}"),
                    title=title,
                    title_zh=_coerce_text(item.get("title_zh")),
                    title_chars=plain_len(title),
                    primary_keywords=_coerce_string_tuple(item.get("primary_keywords")),
                    item_highlights=highlights,
                    item_highlights_zh=_coerce_text(item.get("item_highlights_zh")),
                    item_highlights_chars=plain_len(highlights),
                )
            )
    if variants:
        return variants
    title = strip_md_bold(_coerce_text(raw.get("title"))).strip()
    highlights = strip_md_bold(_coerce_text(raw.get("item_highlights"))).strip()
    if media_category:
        highlights = clamp_plain_text(highlights, PASTE_ITEM_HIGHLIGHTS_MAX)
    else:
        title, highlights = clamp_paste_ready_lengths(title, highlights)
    return [
        TitleVariant(
            code="A",
            strategy_zh="SEO与转化平衡版",
            title=title or "Product Title 待确认",
            title_zh=_coerce_text(raw.get("title_zh")),
            title_chars=plain_len(title),
            item_highlights=highlights or "Key verified product details 待确认",
            item_highlights_zh=_coerce_text(raw.get("item_highlights_zh")),
            item_highlights_chars=plain_len(highlights),
        )
    ]


def _build_final_report(
    *,
    approved_artifacts: dict[str, dict[str, object]],
    variants: list[TitleVariant],
    recommended: TitleVariant,
    bullets: list[BulletDeliverable],
    product_description: str,
    product_description_zh: str,
    search_terms: str,
    questions: list[ShoppingQuestion],
    compliance_risks: list[RiskItem],
    return_risks: list[RiskItem],
    creation_logic_zh: str,
    upload_ready: UploadReadyCopy,
) -> dict[str, object]:
    audience = approved_artifacts.get("audience", {})
    product = approved_artifacts.get("product", {})
    competitor = approved_artifacts.get("competitor", {})
    selling = approved_artifacts.get("selling_points", {})
    keywords = approved_artifacts.get("keywords", {})
    return {
        "一、市场与类目分析": audience.get("category_market_overview", []),
        "二、目标受众画像": audience.get("audience_profiles", []),
        "三、消费者购买动机": audience.get("purchase_motivations", []),
        "四、消费者关注问题": audience.get("shopper_concerns", []),
        "五、好评与差评分析": {
            "好评": audience.get("positive_reviews", []),
            "差评": audience.get("negative_reviews", []),
        },
        "六、产品资料与参数解读": product,
        "七、竞品对比分析": competitor,
        "八、产品定位与5个核心卖点": selling.get("selling_points", []),
        "九、TOP20词根": keywords.get("top20_roots", []),
        "十、TOP20关键词": keywords.get("top20_keywords", []),
        "十一、关键词分配表": keywords.get("keyword_allocation", []),
        "十二、3套Title与Item Highlights": [item.model_dump() for item in variants],
        "十三、最终推荐Title与Item Highlights": recommended.model_dump(),
        "十四、5条Bullet Points及中文翻译": [item.model_dump() for item in bullets],
        "十五、Product Description及中文翻译": {
            "English": product_description,
            "中文翻译": product_description_zh,
            "字符数": plain_len(product_description),
        },
        "十六、Search Terms": search_terms,
        "十七、Rufus问答覆盖": [item.model_dump() for item in questions],
        "十八、合规与退货风险": {
            "合规": [item.model_dump() for item in compliance_risks],
            "退货": [item.model_dump() for item in return_risks],
        },
        "十九、创作逻辑说明": creation_logic_zh,
        "二十、可直接上传的最终版本": upload_ready.model_dump(),
    }


def finalize_deliverable(
    raw: dict[str, object],
    *,
    brand: str = "",
    marketplace: str = "US",
    media_category: bool = False,
    listing_scope: str = "parent",
    variation_values: dict[str, str] | None = None,
    sensitive_category: bool = False,
    fact_ledger: tuple[FactRow, ...] | list[FactRow] = (),
    approved_artifacts: dict[str, dict[str, object]] | None = None,
) -> tuple[CreationDeliverable, ClaimAuthorizationResult]:
    """Build deliverable with length clamp, claim auth, and lint."""
    variants = _coerce_title_variants(raw, media_category=media_category)
    recommended_code = str(raw.get("recommended_variant") or "A").upper()
    if recommended_code not in {"A", "B", "C"}:
        recommended_code = "A"
    recommended = next((item for item in variants if item.code == recommended_code), variants[0])
    recommended_code = recommended.code
    title = recommended.title
    highlights = recommended.item_highlights
    highlights_zh = recommended.item_highlights_zh
    if media_category:
        title = strip_md_bold(title).strip()
        highlights = clamp_plain_text(highlights, PASTE_ITEM_HIGHLIGHTS_MAX)
    else:
        title, highlights = clamp_paste_ready_lengths(title, highlights)

    bullets_raw = raw.get("bullets") or []
    bullets: list[BulletDeliverable] = []
    if isinstance(bullets_raw, list):
        for item in bullets_raw[:5]:
            if isinstance(item, dict):
                text = strip_md_bold(str(item.get("text") or "")).strip()
                text_zh = str(item.get("text_zh") or "").strip()
                purchase_intent_zh = str(item.get("purchase_intent_zh") or "").strip()
                covered_keywords = _coerce_string_tuple(item.get("covered_keywords"))
            else:
                text = strip_md_bold(str(item)).strip()
                text_zh = ""
                purchase_intent_zh = ""
                covered_keywords = ()
            if text:
                bullets.append(
                    BulletDeliverable(
                        text=text,
                        text_zh=text_zh,
                        purchase_intent_zh=purchase_intent_zh,
                        covered_keywords=covered_keywords,
                        chars=plain_len(text),
                    )
                )

    while len(bullets) < 5:
        bullets.append(
            BulletDeliverable(
                text="待补 - Add a verified buyer decision with product evidence",
                text_zh="待补 - 补充有证据的购买决策信息",
            )
        )

    search_terms = str(raw.get("search_terms") or "").strip().lower()
    search_terms = re.sub(r"[^a-z0-9\s]", " ", search_terms)
    search_terms = re.sub(r"\b(?:b0[a-z0-9]{8})\b", " ", search_terms)
    if brand.strip():
        for token in brand.casefold().split():
            search_terms = re.sub(rf"\b{re.escape(token)}\b", " ", search_terms)
    search_terms = " ".join(search_terms.split())
    encoded = search_terms.encode("utf-8")
    if len(encoded) > 250:
        search_terms = encoded[:250].decode("utf-8", errors="ignore").rstrip()

    unresolved = raw.get("unresolved") or []
    unresolved_t = tuple(str(x) for x in unresolved) if isinstance(unresolved, list) else ()

    product_description = _coerce_text(raw.get("product_description")).strip()
    product_description_zh = _coerce_text(raw.get("product_description_zh")).strip()
    shopping_questions = _coerce_question_list(raw.get("shopping_questions"))
    a_plus_modules = _coerce_plus_modules(raw.get("a_plus_modules"))
    keyword_intent_map = _coerce_keyword_map(raw.get("keyword_intent_map"))
    category_recommendations = _coerce_categories(raw.get("category_recommendations"))
    claim_evidence_map = _coerce_claim_map(raw.get("claim_evidence_map"))
    attribute_checklist = _coerce_string_tuple(raw.get("attribute_checklist"))
    compliance_notes = _coerce_string_tuple(raw.get("compliance_notes"))
    compliance_risks = _coerce_risks(raw.get("compliance_risks"))
    return_risks = _coerce_risks(raw.get("return_risks"))
    creation_logic_zh = str(raw.get("creation_logic_zh") or "").strip()
    upload_ready = UploadReadyCopy(
        title=title or "Product Title 待确认",
        item_highlights=highlights or "Key verified product details 待确认",
        bullets=tuple(item.text for item in bullets[:5]),
        product_description=product_description,
        search_terms=search_terms,
    )
    final_report = _build_final_report(
        approved_artifacts=approved_artifacts or {},
        variants=variants,
        recommended=recommended,
        bullets=bullets[:5],
        product_description=product_description,
        product_description_zh=product_description_zh,
        search_terms=search_terms,
        questions=shopping_questions,
        compliance_risks=compliance_risks,
        return_risks=return_risks,
        creation_logic_zh=creation_logic_zh,
        upload_ready=upload_ready,
    )

    auth = authorize_copy_claims(
        title=title,
        item_highlights=highlights,
        bullets=[b.text for b in bullets],
        supporting_copy=[
            product_description,
            *(question.answer_basis for question in shopping_questions),
            *(module.content for module in a_plus_modules),
        ],
        ledger=fact_ledger,
    )
    unresolved_merged = tuple(dict.fromkeys([*unresolved_t, *auth.unresolved]))

    draft = CreationDeliverable(
        title=title or "Product Title 待补",
        title_zh=recommended.title_zh or _coerce_text(raw.get("title_zh")),
        title_chars=plain_len(title),
        item_highlights=highlights or "Key verified product details 待补",
        item_highlights_zh=highlights_zh,
        item_highlights_chars=plain_len(highlights),
        title_variants=variants,
        recommended_variant=recommended_code,
        bullets=bullets[:5],
        search_terms=search_terms,
        search_terms_chars=plain_len(search_terms),
        search_terms_bytes=len(search_terms.encode("utf-8")),
        product_description=product_description,
        product_description_zh=product_description_zh,
        product_description_chars=plain_len(product_description),
        shopping_questions=shopping_questions,
        compliance_risks=compliance_risks,
        return_risks=return_risks,
        creation_logic_zh=creation_logic_zh,
        final_report=final_report,
        upload_ready=upload_ready,
        a_plus_modules=a_plus_modules,
        keyword_intent_map=keyword_intent_map,
        category_recommendations=category_recommendations,
        claim_evidence_map=claim_evidence_map,
        attribute_checklist=attribute_checklist,
        compliance_notes=compliance_notes,
        unresolved=unresolved_merged,
        notes_zh=str(raw.get("notes_zh") or ""),
    )

    lint = lint_deliverable(
        draft,
        brand=brand,
        media_category=media_category,
    )
    status = str(lint.get("status") or "PASS")
    if status not in {"PASS", "WARN", "BLOCK"}:
        status = "WARN"
    issues: list[str] = []
    for bucket in ("errors", "warnings"):
        for row in lint.get(bucket) or []:
            if isinstance(row, dict):
                issues.append(f"{row.get('field')}: {row.get('message')}")
    for claim in auth.blocked_claims:
        issues.append(f"evidence:{claim}")
        status = "BLOCK"
    for warn in auth.warnings:
        issues.append(f"evidence_warn:{warn}")
        if status == "PASS":
            status = "WARN"

    if not media_category and marketplace.upper() == "US":
        short_variants = [item.code for item in variants if item.title_chars < 65]
        if short_variants:
            issues.append("title_variants: versions below recommended 65 characters: " + ", ".join(short_variants))
            if status == "PASS":
                status = "WARN"
    if len(variants) != 3:
        issues.append(f"title_variants: expected 3 versions, got {len(variants)}")
        if status == "PASS":
            status = "WARN"
    if len(shopping_questions) != 10:
        issues.append(f"rufus: expected 10 shopping questions, got {len(shopping_questions)}")
        if status == "PASS":
            status = "WARN"
    for index, bullet in enumerate(bullets, 1):
        if bullet.chars > 320:
            issues.append(f"bullet_{index}: exceeds 320 characters")
            status = "BLOCK"
        if not bullet.purchase_intent_zh or not bullet.covered_keywords:
            issues.append(f"bullet_{index}: purchase intent or covered keywords missing")
            if status == "PASS":
                status = "WARN"
    if product_description and not 900 <= plain_len(product_description) <= 1400:
        issues.append("product_description: outside recommended 900-1400 characters")
        if status == "PASS":
            status = "WARN"

    normalized_title = " ".join(title.casefold().split())
    variation_map = variation_values or {}
    if listing_scope == "parent":
        for key, value in variation_map.items():
            normalized_value = " ".join(value.casefold().split())
            if normalized_value and normalized_value in normalized_title:
                issues.append(f"variation: parent title contains child {key}={value}")
                status = "BLOCK"
    elif listing_scope == "child" and variation_map:
        missing_variations = [
            f"{key}={value}"
            for key, value in variation_map.items()
            if " ".join(value.casefold().split()) not in normalized_title
        ]
        if missing_variations:
            issues.append("variation: child title missing " + ", ".join(missing_variations))
            if status == "PASS":
                status = "WARN"

    normalized_highlights = " ".join(highlights.casefold().split())
    if normalized_title and normalized_highlights == normalized_title:
        issues.append("cross_field: Item Highlights duplicate Title")
        if status == "PASS":
            status = "WARN"
    normalized_bullets = [" ".join(b.text.casefold().split()) for b in bullets]
    if len(set(normalized_bullets)) != len(normalized_bullets):
        issues.append("cross_field: duplicate Bullet Points")
        if status == "PASS":
            status = "WARN"
    if media_category:
        unresolved_merged = tuple(
            dict.fromkeys([*unresolved_merged, "media_title_limit_requires_live_category_validator"])
        )
        issues.append("manual_check: retrieve current media category title rule")
        if status == "PASS":
            status = "WARN"
    if sensitive_category:
        issues.append("manual_check: sensitive category requires human compliance review")
        if status == "PASS":
            status = "WARN"

    stats = lint.get("stats") or {}
    deliverable = draft.model_copy(
        update={
            "title_chars": int(stats.get("title_characters") or draft.title_chars),
            "item_highlights_chars": int(
                stats.get("item_highlights_characters") or draft.item_highlights_chars
            ),
            "search_terms_bytes": int(
                stats.get("search_terms_utf8_bytes") or draft.search_terms_bytes
            ),
            "unresolved": unresolved_merged,
            "policy_status": status,
            "policy_issues": tuple(issues[:30]),
        }
    )
    return deliverable, auth
