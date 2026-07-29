from datetime import UTC, datetime

from amazon_copy.schemas.canonical_deliverables import (
    BaselineEntry,
    BilingualText,
    FullStage1Audit,
    KeywordCoverageEntry,
    NormalStage2Deliverable,
    ScoreEntry,
    StrategyEntry,
    ValidationMetric,
)
from amazon_copy.schemas.canonical_models import CanonicalMarketplace

ASIN = "B0ABC12345"
AUTHORIZED_AT = datetime(2026, 7, 27, 5, 0, tzinfo=UTC)


def audit() -> FullStage1Audit:
    return FullStage1Audit(
        marketplace=CanonicalMarketplace.US,
        asin=ASIN,
        diagnosis_summary="Title coverage needs improvement",
        baseline_table=(
            BaselineEntry(field="title", current_value="Current title", source_id="pdp:1"),
        ),
        keyword_coverage=(
            KeywordCoverageEntry(
                keyword="desk organizer",
                intent="organization",
                current_fields=(),
                proposed_fields=("title",),
            ),
        ),
        scores=(ScoreEntry(dimension="title", score=70, reason="Keyword gap"),),
        priorities=("Restore primary phrase",),
    )


def stage_two() -> NormalStage2Deliverable:
    return NormalStage2Deliverable(
        marketplace=CanonicalMarketplace.US,
        asin=ASIN,
        strategy=(StrategyEntry(action="Lead with product type", rationale="Relevance"),),
        title=BilingualText(english="Optimized title", chinese="ZH optimized title"),
        item_highlights=BilingualText(english="Compact storage", chinese="ZH compact storage"),
        bullets=(BilingualText(english="Organizes supplies", chinese="ZH organizes supplies"),),
        keyword_comparison=(
            KeywordCoverageEntry(
                keyword="desk organizer",
                intent="organization",
                current_fields=(),
                proposed_fields=("title",),
            ),
        ),
        approval_checklist=("Verify dimensions",),
        validation_metrics=(
            ValidationMetric(name="indexed terms", window="2-4 weeks", target="increase"),
        ),
    )
