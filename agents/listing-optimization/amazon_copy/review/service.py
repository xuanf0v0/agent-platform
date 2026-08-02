"""Evidence-first preflight and postflight listing review service."""

from typing import Final, Literal

from amazon_copy.review.bullet_tasks import (
    DECISION_TASK_LABELS_ZH,
    DECISION_TASKS,
    DecisionTaskAssessment,
    DecisionTaskName,
)
from amazon_copy.review.checks import (
    content_findings,
    field_findings,
    highlights_density_findings,
    search_term_findings,
)
from amazon_copy.review.claim_authorization import (
    specialized_requirement_findings,
    unauthorized_new_fact_findings,
)
from amazon_copy.review.dispositions import (
    build_clarification_questions,
    review_disposition,
)
from amazon_copy.review.fact_resolution import fact_priority_findings, resolve_facts
from amazon_copy.review.models import (
    EvidenceSource,
    FactClaim,
    KeywordCoverage,
    ListingReviewReport,
    ListingReviewRequest,
    ReviewDisposition,
    ReviewFinding,
    Severity,
)
from amazon_copy.review.rules import (
    BULLET_TASK_COUNT,
    covered_bullet_tasks,
    duplicate_bullet_pairs,
    finding,
)
from amazon_copy.review.scoring import build_scores

_FACT_FINDING_CODES: Final = frozenset(
    {
        "ACCESSORY_COUNT_AMBIGUITY",
        "FACT_CONFLICT",
        "FACT_PRIORITY_CONFLICT",
        "FACT_QUANTITY_MISMATCH",
        "OVERBROAD_COMPATIBILITY",
        "PRODUCT_CLASSIFICATION_UNRESOLVED",
        "SEARCH_TERM_CLAIM",
        "SPECIALIZED_FACT_UNVERIFIED",
        "THIRD_PARTY_FACT_REJECTED",
        "UNAUTHORIZED_NEW_FACT",
        "UNVERIFIED_PERFORMANCE",
        "UNVERIFIED_SAFETY",
    }
)
_RELEASE_DISPOSITIONS: Final[dict[ReviewDisposition, Literal["release", "clarify", "block"]]] = {
    "terminal": "block",
    "ask_user": "clarify",
    "auto_repair": "release",
}


def bullet_findings(request: ListingReviewRequest) -> list[ReviewFinding]:
    """Check supported bullet count, duplication, and decision-task coverage."""
    findings: list[ReviewFinding] = []
    if len(request.bullets) < request.rules.supported_bullet_count:
        findings.append(
            finding(
                "BULLET_COUNT_OPPORTUNITY",
                "WARN",
                "bullets",
                f"类目支持{request.rules.supported_bullet_count}条，当前只有{len(request.bullets)}条",
            )
        )
    duplicates = duplicate_bullet_pairs(request.bullets)
    if duplicates:
        pairs = "、".join(f"{left}/{right}" for left, right in duplicates)
        findings.append(
            finding("BULLET_DUPLICATION", "WARN", "bullets", "五点内容高度重复：" + pairs)
        )
    tasks = covered_bullet_tasks(request.bullets)
    if len(tasks) < BULLET_TASK_COUNT:
        findings.append(
            finding(
                "BULLET_TASK_COVERAGE",
                "WARN",
                "bullets",
                f"五点只覆盖{len(tasks)}/{BULLET_TASK_COUNT}类购买决策任务",
            )
        )
    return findings


def keyword_coverage(request: ListingReviewRequest) -> tuple[KeywordCoverage, ...]:
    """Locate allowed terms independently in each listing field."""
    terms = tuple(dict.fromkeys((*request.primary_terms, *request.secondary_terms)))
    fields = (
        ("title", request.title),
        ("item_highlights", request.item_highlights),
        ("bullets", " ".join(request.bullets)),
        ("backend_search_terms", request.backend_search_terms),
    )
    rows: list[KeywordCoverage] = []
    for field, text in fields:
        folded = text.casefold()
        rows.append(
            KeywordCoverage.model_validate(
                {
                    "field": field,
                    "covered": tuple(term for term in terms if term.casefold() in folded),
                    "missing": tuple(term for term in terms if term.casefold() not in folded),
                }
            )
        )
    return tuple(rows)


def keyword_basis(claims: tuple[FactClaim, ...]) -> str:
    """Report whether terms come from text, Amazon data, or third-party data."""
    sources = {claim.source for claim in claims if claim.key.casefold().startswith("keyword")}
    if EvidenceSource.AMAZON_FIRST_PARTY_DATA in sources:
        return "first_party_data"
    if EvidenceSource.THIRD_PARTY_PUBLIC_DATA in sources:
        return "third_party_data"
    return "text_relevance_only"


def _finding_status(findings: tuple[ReviewFinding, ...]) -> Severity:
    severities = tuple(item.severity for item in findings)
    if "BLOCK" in severities:
        return "BLOCK"
    if "WARN" in severities:
        return "WARN"
    return "PASS"


def review_listing(request: ListingReviewRequest) -> ListingReviewReport:
    """Review one listing before generation or after optimization."""
    resolved, conflict_findings = resolve_facts(request.claims)
    specialized_findings = specialized_requirement_findings(request, resolved)
    new_fact_findings = unauthorized_new_fact_findings(request, resolved)
    findings = (
        *conflict_findings,
        *field_findings(request),
        *fact_priority_findings(request, resolved),
        *content_findings(request, resolved),
        *specialized_findings,
        *new_fact_findings,
        *highlights_density_findings(request),
        *bullet_findings(request),
        *search_term_findings(request),
    )
    has_block = any(item.severity == "BLOCK" for item in findings)
    has_warn = any(item.severity == "WARN" for item in findings)
    status = "BLOCK" if has_block else "WARN" if has_warn else "PASS"
    disposition = review_disposition(request.phase, findings)
    questions = build_clarification_questions(findings) if disposition == "ask_user" else ()
    fact_findings = tuple(item for item in findings if item.code in _FACT_FINDING_CODES)
    format_findings = tuple(item for item in findings if item.code not in _FACT_FINDING_CODES)
    release_disposition = _RELEASE_DISPOSITIONS[disposition]
    return ListingReviewReport.model_validate(
        {
            "status": status,
            "format_status": _finding_status(format_findings),
            "fact_status": _finding_status(fact_findings),
            "release_disposition": release_disposition,
            "can_optimize": not has_block,
            "findings": findings,
            "resolved_facts": resolved,
            "keyword_coverage": keyword_coverage(request),
            "keyword_basis": keyword_basis(request.claims),
            "scores": build_scores(findings),
            "overall_score": None,
            "disposition": disposition,
            "clarification_questions": questions,
        }
    )


def apply_semantic_bullet_task_coverage(
    report: ListingReviewReport,
    assessments: tuple[DecisionTaskAssessment, ...],
) -> ListingReviewReport:
    """Replace keyword coverage with complete evidence-backed LLM semantics.

    An empty, partial, duplicated, or otherwise invalid classification leaves
    the deterministic report untouched, making model failures fail open to the
    existing keyword heuristic instead of blocking publication.
    """
    if tuple(item.task for item in assessments) != DECISION_TASKS:
        return report

    covered = tuple(item for item in assessments if item.covered)
    missing: tuple[DecisionTaskName, ...] = tuple(
        item.task for item in assessments if not item.covered
    )
    findings = tuple(
        item for item in report.findings if item.code != "BULLET_TASK_COVERAGE"
    )
    if missing:
        missing_text = "、".join(DECISION_TASK_LABELS_ZH[item] for item in missing)
        message_zh = "".join(
            (
                f"LLM语义判断：五点覆盖{len(covered)}/{BULLET_TASK_COUNT}类",
                f"购买决策任务；未覆盖：{missing_text}",
            )
        )
        findings = (
            *findings,
            finding(
                "BULLET_TASK_COVERAGE",
                "WARN",
                "bullets",
                message_zh,
            ),
        )

    fact_findings = tuple(item for item in findings if item.code in _FACT_FINDING_CODES)
    format_findings = tuple(item for item in findings if item.code not in _FACT_FINDING_CODES)
    return report.model_copy(
        update={
            "status": _finding_status(findings),
            "format_status": _finding_status(format_findings),
            "fact_status": _finding_status(fact_findings),
            "can_optimize": not any(item.severity == "BLOCK" for item in findings),
            "findings": findings,
            "scores": build_scores(findings),
        }
    )


__all__ = ["apply_semantic_bullet_task_coverage", "review_listing"]
