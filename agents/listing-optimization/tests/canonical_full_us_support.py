from __future__ import annotations

from datetime import UTC, datetime

from amazon_copy.schemas.canonical_deliverables import (
    BilingualText,
    BulletPlanEntry,
    ComplianceCheck,
    DetailedBulletEntry,
    EvidenceHeader,
    FactStatus,
    FactTableEntry,
    FullUsDeliverable,
    KeywordAllocationEntry,
    KeywordClass,
    KeywordEvidenceLabel,
    PositioningAnalysis,
    QuestionFieldMapEntry,
    ShortFieldVariant,
    ShortFieldVariantLabel,
    StrategyEntry,
    ValidationMetric,
)

_ASIN = "B0ABC12345"
_RETRIEVED_AT = datetime(2026, 7, 27, 8, tzinfo=UTC)
_TITLES = {
    ShortFieldVariantLabel.A: "Desk Organizer with Storage Drawers for Office Supplies and Tools",
    ShortFieldVariantLabel.B: "Compact Desk Organizer with Drawers for Office Supplies and Tools",
    ShortFieldVariantLabel.C: "Office Desk Organizer with Drawers for Supplies, Notes, and Tools",
}


def _bilingual(english: str) -> BilingualText:
    return BilingualText(english=english, chinese=f"ZH {english}")


def _short_field_variant(label: ShortFieldVariantLabel) -> ShortFieldVariant:
    title = _TITLES[label]
    highlights = f"{label.value} pair: organized storage for everyday office supplies"
    return ShortFieldVariant(
        label=label,
        title=_bilingual(title),
        title_character_count=len(title),
        item_highlights=_bilingual(highlights),
        item_highlights_character_count=len(highlights),
        main_keywords=("desk organizer", "office supplies"),
        recommended=label is ShortFieldVariantLabel.A,
    )


def _detailed_bullet(position: int) -> DetailedBulletEntry:
    copy = f"Organized Storage: Bullet {position} keeps verified office supplies easy to reach."
    return DetailedBulletEntry(
        position=position,
        content=_bilingual(copy),
        main_intent="Organize frequently used supplies",
        covered_keywords=("desk organizer",),
        character_count=len(copy),
        word_count=len(copy.split()),
    )


def full_us_deliverable() -> FullUsDeliverable:
    detailed_bullets = tuple(_detailed_bullet(position) for position in range(1, 6))
    return FullUsDeliverable(
        asin=_ASIN,
        evidence_header=EvidenceHeader(
            brand="Example Brand",
            product_type="desk organizer",
            pdp_source_id="pdp:B0ABC12345",
            pdp_snapshot_label="snapshot:2026-07-27T08:00:00Z",
            pdp_retrieved_at=_RETRIEVED_AT,
            keyword_source_ids=("autocomplete:desk-organizer",),
            competitor_source_ids=("pdp:B0XYZ12345",),
            limitations=("No review bodies were retrieved",),
        ),
        fact_table=(
            FactTableEntry(
                field="material",
                verified_value="steel",
                source_id="pdp:B0ABC12345",
                status=FactStatus.VERIFIED,
                risk="None observed",
            ),
        ),
        positioning=PositioningAnalysis(
            core_positioning="Compact desktop storage",
            target_users=("home-office users",),
            contexts=("small desks",),
            purchase_decisions=("dimensions", "drawer access"),
            buyer_concerns=("available desk space",),
            advantages=("compact footprint",),
            limitations=("dimensions require confirmation",),
        ),
        keyword_allocation=(
            KeywordAllocationEntry(
                keyword="desk organizer",
                classification=KeywordClass.CORE,
                evidence_label=KeywordEvidenceLabel.AUTOCOMPLETE,
                allocated_fields=("title", "bullet_1"),
            ),
        ),
        strategy=(StrategyEntry(action="Test title pairs", rationale="Compare intent coverage"),),
        short_field_variants=tuple(_short_field_variant(label) for label in ShortFieldVariantLabel),
        bullet_plan=tuple(
            BulletPlanEntry(
                position=position,
                buyer_question=f"What does section {position} answer?",
                core_information="Verified storage benefit",
                keyword_theme="desk organization",
                repetition_to_avoid="compact storage",
            )
            for position in range(1, 6)
        ),
        detailed_bullets=detailed_bullets,
        product_description=_bilingual("Compact desktop storage for verified office supplies."),
        backend_search_terms="desk organizer office storage",
        backend_search_term_bytes=len(b"desk organizer office storage"),
        question_to_field_map=(
            QuestionFieldMapEntry(
                question="Where do supplies go?",
                intent="storage",
                allocated_fields=("bullet_1",),
            ),
        ),
        approval_checklist=("Confirm dimensions",),
        compliance_checks=(
            ComplianceCheck(code="claims_supported", passed=True, detail="Evidence linked"),
        ),
        validation_metrics=(
            ValidationMetric(name="indexed terms", window="2-4 weeks", target="increase"),
        ),
        upload_only_bullets=tuple(item.content.english for item in detailed_bullets),
    )
