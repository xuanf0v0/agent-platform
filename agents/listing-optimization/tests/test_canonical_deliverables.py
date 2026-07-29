from __future__ import annotations

import pytest
from amazon_copy.schemas.canonical_deliverables import (
    AuditFinding,
    BaselineEntry,
    BilingualText,
    CanonicalDeliverable,
    CompetitorTitleEntry,
    FullStage1Audit,
    KeywordAuditDeliverable,
    KeywordAuditEntry,
    KeywordCoverageEntry,
    NormalStage2Deliverable,
    ScopedTitleAudit,
    ScoreEntry,
    StrategyEntry,
    ValidationMetric,
    deliverable_kind,
)
from amazon_copy.schemas.canonical_models import CanonicalMarketplace
from pydantic import TypeAdapter, ValidationError

from tests.canonical_full_us_support import full_us_deliverable

_ASIN = "B0ABC12345"


def _bilingual(english: str) -> BilingualText:
    return BilingualText(english=english, chinese=f"ZH {english}")


def _finding() -> AuditFinding:
    return AuditFinding(
        code="title.keyword_gap",
        priority=1,
        summary="Missing primary product phrase",
        evidence_ids=("evidence:keyword:1",),
    )


def _score() -> ScoreEntry:
    return ScoreEntry(dimension="title_relevance", score=72, reason="Primary phrase is absent")


def _keyword_coverage() -> KeywordCoverageEntry:
    return KeywordCoverageEntry(
        keyword="desk organizer",
        intent="organization",
        current_fields=(),
        proposed_fields=("title",),
    )


def _metric() -> ValidationMetric:
    return ValidationMetric(name="indexed terms", window="2-4 weeks", target="increase")


def test_all_canonical_deliverable_variants_round_trip_by_discriminator() -> None:
    # Given: every approved typed deliverable variant with its required sections.
    scoped = ScopedTitleAudit(
        marketplace=CanonicalMarketplace.US,
        asin=_ASIN,
        current_title="Current desk organizer",
        findings=(_finding(),),
        scores=(_score(),),
    )
    stage_one = FullStage1Audit(
        marketplace=CanonicalMarketplace.UK,
        asin=_ASIN,
        diagnosis_summary="Coverage needs improvement",
        baseline_table=(
            BaselineEntry(field="title", current_value="Current title", source_id="pdp:1"),
        ),
        keyword_coverage=(_keyword_coverage(),),
        competitor_title_benchmarks=(
            CompetitorTitleEntry(
                asin="B0XYZ12345",
                title="Competitor title",
                source_id="pdp:competitor",
            ),
        ),
        scores=(_score(),),
        priorities=("Restore verified primary phrase",),
    )
    stage_two = NormalStage2Deliverable(
        marketplace=CanonicalMarketplace.UK,
        asin=_ASIN,
        strategy=(StrategyEntry(action="Lead with product type", rationale="Improve relevance"),),
        title=_bilingual("Optimized desk organizer"),
        item_highlights=_bilingual("Compact storage"),
        bullets=(_bilingual("Fits small desks"),),
        keyword_comparison=(_keyword_coverage(),),
        approval_checklist=("Verify dimensions",),
        validation_metrics=(_metric(),),
    )
    full_us = full_us_deliverable()
    keyword_audit = KeywordAuditDeliverable(
        marketplace=CanonicalMarketplace.US,
        asin=_ASIN,
        rows=(
            KeywordAuditEntry(
                keyword="desk organizer",
                required_locations=("title",),
                observed_locations=("title",),
                embedded=True,
            ),
        ),
        summary="All required roots are embedded",
    )
    deliverables: tuple[CanonicalDeliverable, ...] = (
        scoped,
        stage_one,
        stage_two,
        full_us,
        keyword_audit,
    )
    adapter: TypeAdapter[CanonicalDeliverable] = TypeAdapter(CanonicalDeliverable)

    # When: each deliverable crosses a JSON serialization boundary.
    parsed = tuple(adapter.validate_json(item.model_dump_json()) for item in deliverables)

    # Then: the discriminator selects the same frozen variant exhaustively.
    assert tuple(deliverable_kind(item) for item in parsed) == tuple(
        item.kind for item in deliverables
    )
    assert all(item.model_config.get("frozen") is True for item in parsed)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "kind": "full_stage_1",
            "marketplace": "US",
            "diagnosis_summary": "Missing baseline",
            "baseline_table": [],
            "keyword_coverage": [],
            "scores": [],
            "priorities": [],
        },
        {
            "kind": "normal_stage_2",
            "marketplace": "UK",
            "strategy": [{"action": "A", "rationale": "B"}],
            "title": {"english": "A", "chinese": "B"},
            "item_highlights": {"english": "A", "chinese": "B"},
            "bullets": [],
            "keyword_comparison": [],
            "approval_checklist": [],
            "validation_metrics": [],
        },
        {
            "kind": "full_us",
            "marketplace": "UK",
            "strategy": [],
            "short_field_variants": [],
            "bullet_plan": [],
            "upload_only_bullets": [],
            "compliance_checks": [],
            "validation_metrics": [],
        },
        {
            "kind": "keyword_audit",
            "marketplace": "US",
            "rows": [],
            "summary": "No rows",
        },
    ],
)
def test_deliverable_boundary_rejects_missing_required_sections(
    payload: dict[str, str | list[dict[str, str]] | list[str]],
) -> None:
    # Given: a tagged deliverable missing one or more mandatory typed sections.
    adapter: TypeAdapter[CanonicalDeliverable] = TypeAdapter(CanonicalDeliverable)

    # When / Then: the discriminated Pydantic boundary rejects it.
    with pytest.raises(ValidationError):
        _ = adapter.validate_python(payload)
