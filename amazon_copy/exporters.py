"""Stable JSON and Markdown export surfaces for an Amazon copy package."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from amazon_copy.mcp.security import REDACTED, is_secret_key, sanitize_mcp_text

# Runtime imports needed for isinstance checks in export_studio_report
from amazon_copy.schemas.studio_output import (
    DegradedOutcome,
    FailureOutcome,
    NoWinnerOutcome,
    OptimizationReport,
    SuccessOutcome,
    render_seller_ready,
)
from amazon_copy.utils.text_metrics import strip_md_bold

if TYPE_CHECKING:
    from collections.abc import Iterable

    from amazon_copy.schemas import EmbedRow, FinalPackage, SEOCheck


def _sanitize_string(value: str) -> str:
    """Redact sensitive patterns from a string."""
    return sanitize_mcp_text(value)


def _sanitize_value(value: object) -> object:
    """Recursively sanitize a value tree: remove raw_payload keys, redact secrets."""
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return {
            str(key): REDACTED if is_secret_key(str(key)) else _sanitize_value(item)
            for key, item in mapping.items()
            if str(key).casefold() != "raw_payload"
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in cast("list[object]", value)]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in cast("tuple[object, ...]", value)]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def _listing_markdown(package: FinalPackage, *, marked: bool) -> str:
    listing = package.listing
    if listing is None:
        return "# Amazon Listing\n\n_No listing was generated._\n"
    clean = (lambda value: value) if marked else strip_md_bold
    lines = [
        "# Amazon Listing",
        "",
        "## Title",
        "",
        clean(listing.title),
        "",
        "## Bullet Points",
        "",
    ]
    lines.extend(f"- {clean(bullet.text)}" for bullet in listing.bullets)
    lines.extend(["", "## 中文参考", "", f"### 标题\n\n{listing.title_zh}", "", "### 五点描述", ""])
    lines.extend(f"- {bullet.text_zh}" for bullet in listing.bullets)
    return "\n".join(lines).rstrip() + "\n"


def _table(title: str, rows: Iterable[EmbedRow]) -> list[str]:
    values = list(rows)
    lines = [f"### {title}", "", "| Item | Status |", "| --- | --- |"]
    for row in values:
        escaped_item = row.item.replace("|", "\\|")
        lines.append(f"| {escaped_item} | {row.mark} |")
    if not values:
        lines.append("| _None_ | X |")
    return [*lines, ""]


def _seo_report(label: str, seo: SEOCheck) -> list[str]:
    lines = [f"## {label}", ""]
    lines.extend(_table("Intent", seo.intent_rows))
    lines.extend(_table("Rootwords", seo.rootword_rows))
    lines.extend(_table("Keywords", seo.keyword_rows))
    if seo.narrative:
        lines.extend(["### Narrative", "", seo.narrative, ""])
    return lines


def _report_markdown(package: FinalPackage) -> str:
    lines = ["# Amazon Copywriting Report", "", "## Research", ""]
    research = package.research
    if research is None:
        lines.append("_Not run for this workflow._")
    else:
        lines.extend(
            [
                f"**Audience:** {research.audience.summary}",
                "",
                f"**Product:** {research.product_intro}",
                "",
                f"**Instruction decode:** {research.instruction_decode}",
                "",
                "### Motives",
                "",
            ]
        )
        lines.extend(f"- {item.motive}: {item.evidence}" for item in research.motives)
        lines.extend(["", "### Competitor notes", ""])
        competitor_notes = (
            research.competitor.parameters
            + research.competitor.selling_points
            + research.competitor.copy_notes
        )
        lines.extend(f"- {note}" for note in competitor_notes)
        if research.competitor.raw_blocks:
            lines.append(
                f"- {len(research.competitor.raw_blocks)} raw competitor block(s) analyzed"
            )
        if not competitor_notes and not research.competitor.raw_blocks:
            lines.append("- No pasted competitor copy supplied; competitor analysis was skipped")
    lines.extend(["", "## Selling Points", ""])
    lines.extend(
        f"{point.rank}. {point.text_en} / {point.text_zh} — {point.rationale}"
        for point in package.selling_points
    )
    if not package.selling_points:
        lines.append("_Not run for this workflow._")
    lines.append("")
    if package.seo is not None:
        lines.extend(_seo_report("SEO", package.seo))
    else:
        lines.extend(["## SEO", "", "_Not run for this workflow._", ""])
    if package.seo2 is not None:
        lines.extend(_seo_report("SEO After Optimization", package.seo2))
    lines.extend(["## Score", ""])
    if package.scorecard is None:
        lines.append("_Not run for this workflow._")
    else:
        lines.extend(["| Dimension | Score | Rationale |", "| --- | ---: | --- |"])
        lines.extend(
            f"| {dim.label_zh} ({dim.key.value}) | {dim.score:.1f} | {dim.rationale} |"
            for dim in package.scorecard.dimensions
        )
        lines.extend(["", f"**Overall: {package.scorecard.overall:.1f}/10**"])
    return "\n".join(lines).rstrip() + "\n"


def _write_atomic(path: Path, content: str) -> None:
    """Replace one export atomically and remove the staging file on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def export_package(package: FinalPackage, output_dir: str | Path) -> dict[str, Path]:
    """Write the full package and its three human-readable delivery surfaces."""
    destination = Path(output_dir)
    paths = {
        "json": destination / "listing.json",
        "listing": destination / "listing.md",
        "listing_marked": destination / "listing_marked.md",
        "report": destination / "report.md",
    }
    payloads = {
        "json": json.dumps(
            _sanitize_value(package.model_dump(mode="json")),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "listing": _sanitize_string(_listing_markdown(package, marked=False)),
        "listing_marked": _sanitize_string(_listing_markdown(package, marked=True)),
        "report": _sanitize_string(_report_markdown(package)),
    }
    for key, path in paths.items():
        _write_atomic(path, payloads[key])
    return paths


def _seller_md_from_report(report: OptimizationReport, *, marked: bool) -> str:
    """Build seller-facing markdown from an optimization report."""
    clean = (lambda v: v) if marked else strip_md_bold
    lines = [
        "# Amazon Listing",
        "",
        "## Title Options",
        "",
    ]
    for i, opt in enumerate(report.title_options, 1):
        lines.append(f"### Option {i}")
        lines.append("")
        lines.append(clean(opt.text))
        lines.append("")
    lines.append("## Bullet Points")
    lines.append("")
    for b in report.bullets:
        lines.append(f"- {clean(b.text)}")
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(clean(report.description))
    lines.append("")
    lines.append("## Search Terms")
    lines.append("")
    lines.append(report.search_terms)
    return "\n".join(lines).rstrip() + "\n"


def _studio_report_markdown(report: OptimizationReport) -> str:
    """Build report section markdown from an optimization report."""
    lines = ["# Studio Report", ""]
    if report.analysis:
        lines.extend(["## Analysis", "", report.analysis, ""])
    if report.evidence_gaps:
        lines.extend(["## Evidence Gaps", ""])
        for gap in report.evidence_gaps:
            lines.append(f"- **{gap.field}**: {gap.reason}")
        lines.append("")
    if report.keyword_allocation:
        lines.extend(["## Keyword Allocation", ""])
        for alloc in report.keyword_allocation:
            placements = ", ".join(alloc.placements) if alloc.placements else "—"
            lines.append(f"- {alloc.keyword}: {placements}")
        lines.append("")
    if report.compliance_notes:
        lines.extend(["## Compliance Notes", ""])
        for note in report.compliance_notes:
            lines.append(f"- {note}")
        lines.append("")
    if report.return_risk_notes:
        lines.extend(["## Return Risk Notes", ""])
        for note in report.return_risk_notes:
            lines.append(f"- {note}")
        lines.append("")
    if report.citations:
        lines.extend(["## Citations", ""])
        for c in report.citations:
            loc = f" ({c.locator})" if c.locator else ""
            lines.append(f"- {c.claim_id} \u2190 {c.source_id}{loc}")
        lines.append("")
    if report.audit:
        lines.extend(["## Audit", ""])
        a = report.audit
        audit_parts = [f"- **Run ID**: {a.run_id}"]
        if a.llm_calls:
            audit_parts.append(f"- **LLM calls**: {a.llm_calls}")
        if a.mcp_calls:
            audit_parts.append(f"- **MCP calls**: {a.mcp_calls}")
        if a.duration_ms:
            audit_parts.append(f"- **Duration**: {a.duration_ms}ms")
        lines.extend(audit_parts)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _studio_export_payload(export_value: object) -> tuple[object, str, str, str]:
    if isinstance(export_value, (SuccessOutcome, DegradedOutcome)):
        report = export_value.report
        listing = render_seller_ready(export_value)
        return (
            _sanitize_value(export_value.model_dump(mode="json")),
            listing,
            listing,
            _studio_report_markdown(report),
        )
    if isinstance(export_value, (NoWinnerOutcome, FailureOutcome)):
        diagnostic = render_seller_ready(export_value)
        return (
            _sanitize_value(export_value.model_dump(mode="json")),
            diagnostic,
            diagnostic,
            f"# Studio Report\n\n{diagnostic}\n",
        )
    if isinstance(export_value, OptimizationReport):
        return (
            _sanitize_value(export_value.model_dump(mode="json")),
            _seller_md_from_report(export_value, marked=False),
            _seller_md_from_report(export_value, marked=True),
            _studio_report_markdown(export_value),
        )
    message = f"Unsupported type: {type(export_value).__name__}"
    raise TypeError(message)


def export_studio_report(
    report_or_outcome: OptimizationReport
    | SuccessOutcome
    | DegradedOutcome
    | NoWinnerOutcome
    | FailureOutcome,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write studio report to four export files using seller-ready renderers.

    For ``SuccessOutcome`` / ``DegradedOutcome`` the listing content is derived
    from ``render_seller_ready``; for a bare ``OptimizationReport`` it is built
    from *title_options*, *bullets*, *description*, and *search_terms*.
    All output is sanitized (secrets redacted, ``raw_payload`` keys stripped).
    """
    destination = Path(output_dir)
    paths = {
        "json": destination / "listing.json",
        "listing": destination / "listing.md",
        "listing_marked": destination / "listing_marked.md",
        "report": destination / "report.md",
    }

    json_data, listing, listing_marked, report_md = _studio_export_payload(report_or_outcome)

    payloads: dict[str, str] = {
        "json": json.dumps(json_data, ensure_ascii=False, indent=2) + "\n",
        "listing": _sanitize_string(listing) + "\n",
        "listing_marked": _sanitize_string(listing_marked) + "\n",
        "report": _sanitize_string(report_md) + "\n",
    }
    for key, path in paths.items():
        _write_atomic(path, payloads[key])
    return paths


__all__ = ["export_package", "export_studio_report"]
