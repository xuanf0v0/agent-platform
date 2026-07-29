"""Clamp, lint, and evidence-authorize final creation deliverable."""

from __future__ import annotations

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
    ShoppingQuestion,
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


def finalize_deliverable(
    raw: dict[str, object],
    *,
    brand: str = "",
    media_category: bool = False,
    listing_scope: str = "parent",
    variation_values: dict[str, str] | None = None,
    sensitive_category: bool = False,
    fact_ledger: tuple[FactRow, ...] | list[FactRow] = (),
) -> tuple[CreationDeliverable, ClaimAuthorizationResult]:
    """Build deliverable with length clamp, claim auth, and lint."""
    title = strip_md_bold(_coerce_text(raw.get("title"))).strip()
    highlights = strip_md_bold(_coerce_text(raw.get("item_highlights"))).strip()
    highlights_zh = _coerce_text(raw.get("item_highlights_zh"))
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
            else:
                text = strip_md_bold(str(item)).strip()
                text_zh = ""
            if text:
                bullets.append(BulletDeliverable(text=text, text_zh=text_zh))

    while len(bullets) < 5:
        bullets.append(
            BulletDeliverable(
                text="待补 - Add a verified buyer decision with product evidence",
                text_zh="待补 - 补充有证据的购买决策信息",
            )
        )

    search_terms = str(raw.get("search_terms") or "").strip().lower()
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
        title_zh=_coerce_text(raw.get("title_zh")),
        title_chars=plain_len(title),
        item_highlights=highlights or "Key verified product details 待补",
        item_highlights_zh=highlights_zh,
        item_highlights_chars=plain_len(highlights),
        bullets=bullets[:5],
        search_terms=search_terms,
        search_terms_bytes=len(search_terms.encode("utf-8")),
        product_description=product_description,
        product_description_zh=product_description_zh,
        shopping_questions=shopping_questions,
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
