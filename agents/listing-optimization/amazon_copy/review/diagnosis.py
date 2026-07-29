"""Build structured listing diagnosis reports for the automatic workbench."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, Literal

from amazon_copy.review.diagnosis_models import (
    DIMENSION_LABELS_ZH,
    BackendTermsDiagnosis,
    EditorialScore,
    FieldCheckRow,
    ListingDiagnosisReport,
    PriorityIssue,
    ScoreDimension,
)
from amazon_copy.review.search_terms import (
    BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES,
    incremental_search_term_tokens,
    search_term_duplication_pct,
    unverified_search_term_claims,
)
from amazon_copy.utils.text_metrics import plain_len

if TYPE_CHECKING:
    from collections.abc import Sequence

    from amazon_copy.review.models import ListingReviewReport, ListingReviewRequest, ReviewFinding

_DIMENSION_ORDER: Final[tuple[ScoreDimension, ...]] = (
    "compliance",
    "a9_seo",
    "semantic_coverage",
    "grammar",
    "readability",
    "selling_points",
    "localization",
    "technical_accuracy",
    "emotional_appeal",
    "purchase_motivation",
)

_FIELD_LABELS: Final[dict[str, str]] = {
    "title": "Title",
    "item_highlights": "Item Highlights",
    "bullets": "Bullet Points",
    "backend_search_terms": "Search Terms",
    "listing": "Listing",
}

_FRAGMENT_RE: Final = re.compile(
    r"(?:\b(?:or|and|with|for|to|of|the|a|an)\s*[—–-]\s*(?:or|and|with|for)?\b)"
    r"|(?:\b\w{1,2}\s*,)"
    r"|(?:^[a-z]\s+\w+)"
    r"|(?:\bws,\b)",
    re.IGNORECASE,
)
_EMPTY_HEIGHT_RE: Final = re.compile(
    r"heights?\s*[—–-]\s*(?:or\s*)?[—–-]?",
    re.IGNORECASE,
)


def _worst(statuses: Sequence[str]) -> str:
    if any(status == "BLOCK" for status in statuses):
        return "BLOCK"
    if any(status == "WARN" for status in statuses):
        return "WARN"
    return "PASS"


def _field_findings(
    findings: Sequence[ReviewFinding],
    field: str,
) -> tuple[ReviewFinding, ...]:
    if field == "bullets":
        return tuple(
            finding
            for finding in findings
            if finding.field == "bullets" or finding.field.startswith("bullet")
        )
    return tuple(finding for finding in findings if finding.field == field)


def _metric_note(
    *,
    metric: str,
    status: str,
    findings: Sequence[ReviewFinding],
    empty_note: str,
) -> str:
    if findings:
        return "；".join(finding.message_zh for finding in findings[:3])
    if status == "PASS":
        return empty_note
    return metric


def build_field_checks(
    request: ListingReviewRequest,
    report: ListingReviewReport,
) -> tuple[FieldCheckRow, ...]:
    """Build PASS/WARN/BLOCK rows for title, highlights, each bullet, and search terms."""
    rules = request.rules
    rows: list[FieldCheckRow] = []

    title_findings = _field_findings(report.findings, "title")
    title_status = _worst(tuple(finding.severity for finding in title_findings) or ("PASS",))
    title_len = plain_len(request.title)
    rows.append(
        FieldCheckRow(
            field="Title",
            metric=f"{title_len}/{rules.title_max} characters",
            status=title_status,  # type: ignore[arg-type]
            note_zh=_metric_note(
                metric=f"{title_len}/{rules.title_max}",
                status=title_status,
                findings=title_findings,
                empty_note="长度合规",
            ),
        )
    )

    ih_findings = _field_findings(report.findings, "item_highlights")
    ih_text = request.item_highlights.strip()
    ih_len = plain_len(ih_text) if ih_text else 0
    ih_statuses = [finding.severity for finding in ih_findings]
    if not ih_text:
        ih_statuses.append("WARN")
    elif _looks_fragmented(ih_text):
        ih_statuses.append("BLOCK")
    ih_status = _worst(ih_statuses or ("PASS",))
    ih_note = _metric_note(
        metric=f"{ih_len}/{rules.item_highlights_max}",
        status=ih_status,
        findings=ih_findings,
        empty_note="长度合规",
    )
    if not ih_text:
        ih_note = "缺失 Item Highlights"
    elif _looks_fragmented(ih_text) and not ih_findings:
        ih_note = "内容疑似残句或不完整"
    rows.append(
        FieldCheckRow(
            field="Item Highlights",
            metric=(
                f"{ih_len}/{rules.item_highlights_max} characters"
                if ih_text
                else "缺失"
            ),
            status=ih_status,  # type: ignore[arg-type]
            note_zh=ih_note,
        )
    )

    supported = rules.supported_bullet_count
    bullet_findings_all = _field_findings(report.findings, "bullets")
    for index in range(1, max(supported, len(request.bullets)) + 1):
        if index <= len(request.bullets):
            text = request.bullets[index - 1]
            length = plain_len(text)
            local = tuple(
                finding
                for finding in bullet_findings_all
                if finding.field in {f"bullet_{index}", f"bullets[{index}]", "bullets"}
            )
            statuses = [finding.severity for finding in local]
            if _looks_fragmented(text) or _EMPTY_HEIGHT_RE.search(text):
                statuses.append("BLOCK")
            status = _worst(statuses or ("PASS",))
            note = _metric_note(
                metric=f"{length} characters",
                status=status,
                findings=local,
                empty_note="结构可读",
            )
            if _looks_fragmented(text) and not local:
                note = "内容疑似残句或损坏"
            elif _EMPTY_HEIGHT_RE.search(text) and not local:
                note = "高度或其他关键参数缺失"
            metric = f"{length} characters"
        else:
            status = "WARN"
            note = "缺失"
            metric = "缺失"
            if index == supported and len(request.bullets) < supported:
                count_findings = tuple(
                    finding
                    for finding in bullet_findings_all
                    if finding.code == "BULLET_COUNT_OPPORTUNITY"
                )
                if count_findings:
                    note = count_findings[0].message_zh
        rows.append(
            FieldCheckRow(
                field=f"Bullet {index}",
                metric=metric,
                status=status,  # type: ignore[arg-type]
                note_zh=note,
            )
        )

    st_findings = _field_findings(report.findings, "backend_search_terms")
    terms = request.backend_search_terms.strip()
    max_bytes = min(rules.backend_search_terms_max_bytes, BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES)
    used = len(terms.encode("utf-8")) if terms else 0
    st_statuses = [finding.severity for finding in st_findings]
    if not terms:
        st_statuses.append("WARN")
    st_status = _worst(st_statuses or ("PASS",))
    st_note = _metric_note(
        metric=f"{used}/{max_bytes} UTF-8 bytes",
        status=st_status,
        findings=st_findings,
        empty_note="长度合规",
    )
    if not terms:
        st_note = "源稿未提供后台词"
    rows.append(
        FieldCheckRow(
            field="Search Terms",
            metric=f"{used}/{max_bytes} UTF-8 bytes" if terms else "缺失",
            status=st_status,  # type: ignore[arg-type]
            note_zh=st_note,
        )
    )
    return tuple(rows)


def _looks_fragmented(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 8:
        return True
    if stripped[:1].islower() and " " in stripped:
        return True
    if _FRAGMENT_RE.search(stripped):
        return True
    if "—" in stripped and re.search(r"[—–-]\s*(?:or\s*)?[—–-]", stripped):
        return True
    return bool(re.search(r"\bws,\b", stripped, re.IGNORECASE))


def build_backend_diagnosis(
    request: ListingReviewRequest,
    report: ListingReviewReport,
) -> BackendTermsDiagnosis:
    """Diagnose backend search-term budget, duplication, and candidate gaps."""
    terms = request.backend_search_terms.strip()
    max_bytes = min(
        request.rules.backend_search_terms_max_bytes,
        BACKEND_SEARCH_TERMS_GLOBAL_MAX_BYTES,
    )
    used = len(terms.encode("utf-8")) if terms else 0
    tokens = tuple(token for token in terms.split() if token)
    duplication = search_term_duplication_pct(
        terms,
        request.title,
        request.item_highlights,
        request.bullets,
    )
    incremental = incremental_search_term_tokens(
        terms,
        request.title,
        request.item_highlights,
        request.bullets,
    )
    visible = _visible_roots(request.title, request.item_highlights, request.bullets)
    repeated = tuple(
        token for token in tokens if token.casefold() in visible and token.casefold() not in {
            "for",
            "with",
            "and",
            "the",
            "a",
            "an",
            "of",
            "in",
            "on",
            "to",
        }
    )
    # Prefer unique order-preserving roots.
    seen: set[str] = set()
    repeated_unique: list[str] = []
    for token in repeated:
        folded = token.casefold()
        if folded not in seen:
            seen.add(folded)
            repeated_unique.append(token.casefold())

    uncovered: list[str] = []
    for row in report.keyword_coverage:
        if row.field == "backend_search_terms":
            uncovered.extend(row.missing)
        elif row.field in {"title", "item_highlights", "bullets"}:
            for term in row.missing:
                if term.casefold() not in {item.casefold() for item in uncovered}:
                    uncovered.append(term)

    risks: list[str] = []
    claim_hits = unverified_search_term_claims(terms)
    if claim_hits:
        risks.append("后台词含未证实性能宣称：" + "、".join(claim_hits))
    if used > max_bytes:
        risks.append(f"超过 {max_bytes} UTF-8 字节硬限制")
    if duplication >= 50.0 and tokens:
        risks.append(f"与可见字段重复约 {duplication:.0f}%")
    if not terms:
        risks.append("源稿未提供 Backend Search Terms")
    if "easel" in terms.casefold():
        risks.append("easel 可能误导为传统三脚画架，需结合产品形态谨慎使用")

    if not terms:
        summary = "源稿未提供后台词；优化阶段将按去重规则重新生成。"
    elif used > max_bytes:
        summary = f"{used}/{max_bytes} UTF-8 bytes：超限，不可上传。"
    elif duplication >= 50.0:
        summary = (
            f"{used}/{max_bytes} UTF-8 bytes：长度合规，但与可见字段重复约 "
            f"{duplication:.0f}%，增量词根利用率一般。"
        )
    else:
        summary = f"{used}/{max_bytes} UTF-8 bytes：长度合规。"

    return BackendTermsDiagnosis(
        terms=terms,
        bytes_used=used,
        max_bytes=max_bytes,
        token_count=len(tokens),
        duplication_pct=round(duplication, 1),
        repeated_roots=tuple(repeated_unique),
        incremental_roots=incremental,
        uncovered_candidates=tuple(uncovered[:12]),
        risk_notes_zh=tuple(risks),
        summary_zh=summary,
    )


def _visible_roots(title: str, item_highlights: str, bullets: Sequence[str]) -> frozenset[str]:
    text = " ".join((title, item_highlights, *bullets)).casefold()
    return frozenset(re.findall(r"[\w+\-]+", text, flags=re.UNICODE))


def build_rule_issues(
    report: ListingReviewReport,
    field_checks: Sequence[FieldCheckRow],
) -> tuple[PriorityIssue, ...]:
    """Map BLOCK→P0 and WARN→P1 from findings and fragmented field checks."""
    issues: list[PriorityIssue] = []
    seen: set[str] = set()

    for row in field_checks:
        if row.status == "BLOCK":
            key = f"field:{row.field}"
            if key not in seen:
                seen.add(key)
                issues.append(
                    PriorityIssue(
                        level="P0",
                        title=f"{row.field} 需立即修复",
                        detail_zh=row.note_zh,
                    )
                )
        elif row.status == "WARN" and row.field.startswith("Bullet") and "缺失" in row.note_zh:
            key = f"missing:{row.field}"
            if key not in seen:
                seen.add(key)
                issues.append(
                    PriorityIssue(
                        level="P1",
                        title=f"{row.field} 缺失",
                        detail_zh=row.note_zh,
                    )
                )

    for finding in report.findings:
        if finding.severity not in {"BLOCK", "WARN"}:
            continue
        key = f"{finding.code}:{finding.field}"
        if key in seen:
            continue
        seen.add(key)
        label = _FIELD_LABELS.get(finding.field, finding.field)
        level: Literal["P0", "P1"] = "P0" if finding.severity == "BLOCK" else "P1"
        issues.append(
            PriorityIssue(
                level=level,
                title=f"{label} · {finding.code}",
                detail_zh=finding.message_zh,
            )
        )
    return tuple(issues)


def build_rule_scores(report: ListingReviewReport) -> tuple[EditorialScore, ...]:
    """Convert deterministic review scores into editorial score rows."""
    by_dim = {score.dimension: score for score in report.scores}
    rows: list[EditorialScore] = []
    for dimension in _DIMENSION_ORDER:
        score = by_dim[dimension]
        rows.append(
            EditorialScore(
                dimension=dimension,
                label_zh=DIMENSION_LABELS_ZH[dimension],
                score=score.score,
                rationale_zh=score.rationale_zh,
            )
        )
    return tuple(rows)


def build_fix_order(issues: Sequence[PriorityIssue]) -> tuple[str, ...]:
    """Suggest a stable fix order from prioritized issues."""
    if not issues:
        return ("当前未定位必须优先处理的问题；可直接进入优化终稿。",)
    order: list[str] = []
    p0 = [issue for issue in issues if issue.level == "P0"]
    p1 = [issue for issue in issues if issue.level == "P1"]
    if p0:
        order.append("立即修复残句、缺失参数与 BLOCK 项——P0，必须完成。")
        for issue in p0[:4]:
            order.append(f"处理 P0：{issue.title}")
    if p1:
        order.append("确认 WARN 与卖点完整性问题——P1。")
        for issue in p1[:3]:
            order.append(f"处理 P1：{issue.title}")
    order.append("定稿可见字段后，重新生成去重的后台词。")
    return tuple(order)


def build_rules_diagnosis(
    request: ListingReviewRequest,
    report: ListingReviewReport,
) -> ListingDiagnosisReport:
    """Build a full diagnosis report from deterministic review only."""
    field_checks = build_field_checks(request, report)
    backend = build_backend_diagnosis(request, report)
    issues = build_rule_issues(report, field_checks)
    scores = build_rule_scores(report)
    average = round(sum(score.score for score in scores) / len(scores), 1)
    return ListingDiagnosisReport(
        field_checks=field_checks,
        issues=issues,
        backend=backend,
        scores=scores,
        average_score=average,
        fix_order=build_fix_order(issues),
        scoring_source="rules",
    )


__all__ = [
    "build_backend_diagnosis",
    "build_field_checks",
    "build_fix_order",
    "build_rule_issues",
    "build_rule_scores",
    "build_rules_diagnosis",
]
