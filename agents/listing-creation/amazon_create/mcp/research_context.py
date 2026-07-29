"""Research context for review, diagnosis, and rewrite (MCP market evidence)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from amazon_create.mcp.live_research_models import McpToolSnapshot
    from amazon_create.mcp.live_research_types import ResearchBundle
    from amazon_create.review.diagnosis_models import ListingDiagnosisReport
    from amazon_create.review.models import ListingReviewReport


def build_research_context(
    research: ResearchBundle,
    *,
    snapshots: tuple[McpToolSnapshot, ...] | list[McpToolSnapshot] = (),
    max_keywords: int = 24,
    max_metrics: int = 16,
    max_gaps: int = 12,
    max_cited: int = 32,
    max_call_snippets: int = 6,
    max_product_attributes: int = 32,
    max_category_candidates: int = 24,
) -> dict[str, Any]:
    """Build a JSON-safe research brief for every automatic-pipeline layer.

    Retrieved MCP rows become **citable market evidence** (keywords, demand,
    competition). They still cannot invent private product/BOM/safety facts.
    """
    keywords = list(research.allowed_keywords)[:max_keywords]
    metrics: list[dict[str, str]] = []
    product_attributes: list[dict[str, str]] = []
    category_candidates: list[dict[str, str]] = []
    cited: list[dict[str, str]] = []
    seen_metrics: set[tuple[str, str, str]] = set()
    for item in research.items:
        if item.kind == "keyword":
            if len(cited) < max_cited:
                cited.append(
                    {
                        "kind": "keyword",
                        "claim": item.value,
                        "provider": item.provider,
                        "tool": item.tool,
                        "use_for": "seo_and_backend_terms",
                    }
                )
            continue
        if item.kind == "product_attribute":
            if len(product_attributes) < max_product_attributes:
                product_attributes.append(
                    {
                        "key": item.key,
                        "value": item.value,
                        "provider": item.provider,
                        "tool": item.tool,
                    }
                )
            continue
        if item.kind == "category_candidate":
            if len(category_candidates) < max_category_candidates:
                category_candidates.append(
                    {
                        "key": item.key,
                        "value": item.value,
                        "provider": item.provider,
                        "tool": item.tool,
                    }
                )
            continue
        if item.kind != "market_metric":
            continue
        identity = (item.key.casefold(), item.value.casefold(), item.provider.casefold())
        if identity in seen_metrics:
            continue
        seen_metrics.add(identity)
        row = {
            "key": item.key,
            "value": item.value,
            "provider": item.provider,
            "tool": item.tool,
        }
        metrics.append(row)
        if len(cited) < max_cited:
            cited.append(
                {
                    "kind": "market_metric",
                    "claim": f"{item.key}={item.value}",
                    "provider": item.provider,
                    "tool": item.tool,
                    "use_for": "seo_priority_and_demand_context",
                }
            )
        if len(metrics) >= max_metrics:
            break
    gaps: list[dict[str, str]] = []
    for gap in research.gaps[:max_gaps]:
        gaps.append(
            {
                "code": gap.code,
                "provider": gap.provider,
                "tool": gap.tool,
            }
        )
    providers: list[dict[str, object]] = []
    call_snippets: list[dict[str, str]] = []
    for snapshot in snapshots:
        providers.append(
            {
                "provider": snapshot.provider,
                "status": snapshot.status,
                "tool_count": snapshot.tool_count,
                "tools_sample": list(snapshot.tools_sample)[:8],
                "calls": [
                    {
                        "tool": call.get("tool", ""),
                        "ok": bool(call.get("ok")),
                    }
                    for call in list(snapshot.calls)[:4]
                ],
            }
        )
        for call in list(snapshot.calls)[:4]:
            if not call.get("ok"):
                continue
            if len(call_snippets) >= max_call_snippets:
                break
            summary = str(call.get("summary_text") or "").strip()
            if not summary:
                continue
            call_snippets.append(
                {
                    "provider": snapshot.provider,
                    "tool": str(call.get("tool") or ""),
                    "summary_excerpt": summary[:500],
                }
            )
            if len(cited) < max_cited:
                cited.append(
                    {
                        "kind": "tool_summary",
                        "claim": summary[:280],
                        "provider": snapshot.provider,
                        "tool": str(call.get("tool") or ""),
                        "use_for": "market_language_and_seo_context",
                    }
                )
    has_evidence = bool(
        keywords or metrics or product_attributes or category_candidates or call_snippets
    )
    return {
        "authority": "third_party_public_market_evidence",
        "priority": 6,
        "trusted_for_product_facts": False,
        "trusted_for_market_seo": has_evidence,
        "has_retrieved_evidence": has_evidence,
        "keywords": keywords,
        "market_metrics": metrics,
        "product_attributes": product_attributes,
        "category_candidates": category_candidates,
        "cited_evidence": cited,
        "tool_summaries": call_snippets,
        "gaps": gaps,
        "providers": providers,
        "usage_note": (
            "When has_retrieved_evidence is true, cite retrieved keywords and metrics "
            "for SEO prioritization, title/bullet keyword placement, and backend terms. "
            "Do not invent private product facts (material, package BOM, safety rating, "
            "certification, load, dimensions) that are absent from source/verified facts. "
            "If a metric was retrieved (e.g. search_volume), you may use it as market "
            "context in strategy; do not paste raw numbers into customer-facing copy "
            "unless the source already states them."
        ),
    }


def build_review_summary(report: ListingReviewReport, *, max_findings: int = 20) -> dict[str, Any]:
    """Compact source/postflight review findings for downstream prompts."""
    findings = [
        {
            "code": finding.code,
            "severity": finding.severity,
            "field": finding.field,
            "message_zh": finding.message_zh,
        }
        for finding in report.findings[:max_findings]
        if finding.severity in {"BLOCK", "WARN"}
    ]
    return {
        "status": report.status,
        "format_status": report.format_status,
        "fact_status": report.fact_status,
        "release_disposition": report.release_disposition,
        "findings": findings,
        "keyword_coverage": [
            {
                "field": row.field,
                "covered": list(row.covered)[:12],
                "missing": list(row.missing)[:12],
            }
            for row in report.keyword_coverage
        ],
        "scores": [
            {
                "dimension": score.dimension,
                "score": score.score,
                "rationale_zh": score.rationale_zh,
            }
            for score in report.scores
        ],
    }


def build_diagnosis_summary(
    diagnosis: ListingDiagnosisReport | None,
    *,
    max_issues: int = 12,
) -> dict[str, Any] | None:
    """Compact editorial diagnosis for the rewrite prompt."""
    if diagnosis is None:
        return None
    return {
        "scoring_source": diagnosis.scoring_source,
        "average_score": diagnosis.average_score,
        "field_checks": [
            {
                "field": row.field,
                "metric": row.metric,
                "status": row.status,
                "note_zh": row.note_zh,
            }
            for row in diagnosis.field_checks
        ],
        "issues": [
            {
                "level": issue.level,
                "title": issue.title,
                "detail_zh": issue.detail_zh,
            }
            for issue in diagnosis.issues[:max_issues]
        ],
        "backend": diagnosis.backend.model_dump(mode="json"),
        "scores": [
            {
                "dimension": score.dimension,
                "label_zh": score.label_zh,
                "score": score.score,
                "rationale_zh": score.rationale_zh,
            }
            for score in diagnosis.scores
        ],
        "fix_order": list(diagnosis.fix_order),
        "disclaimer_zh": diagnosis.disclaimer_zh,
    }


__all__ = [
    "build_diagnosis_summary",
    "build_research_context",
    "build_review_summary",
]
