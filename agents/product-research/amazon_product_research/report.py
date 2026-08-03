"""JSON and Excel artifact generation."""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from .models import ResearchRun


def _sheets(run: ResearchRun) -> dict[str, list[list[object]]]:
    decision = run.result.decision.value if run.result and run.result.decision else ""
    sheets: dict[str, list[list[object]]] = {
        "数据来源说明": [["Evidence ID", "Provider", "Tool", "Claim", "Retrieved At"]],
        "执行摘要": [
            ["Field", "Value"],
            ["Decision", decision],
            ["Mode", run.mode.value],
            ["Marketplace", run.marketplace],
            ["Title", run.title],
        ],
        "候选产品": [["ID", "ASIN", "Title", "Price", "Cost", "Margin %", "Overall", "Decision"]],
        "市场与趋势": [["Candidate", "Search Volume", "Monthly Sales", "Trend %", "Top3 Share %"]],
        "关键词": [["Provider", "Tool", "Claim"]],
        "竞品格局": [["Candidate", "ASIN", "Reviews", "Rating", "Competition Score"]],
        "评论痛点": [["Candidate", "Pain Point"]],
        "单位经济模型": [["Candidate", "Price", "Cost", "Margin %", "Profitability Score"]],
        "供应商与MOQ": [["Candidate", "Supplier Count", "MOQ", "Supply Score"]],
        "风险": [["Candidate", "Risk Flag"]],
        "评分与决策": [
            [
                "Candidate",
                "Demand",
                "Competition",
                "Profitability",
                "Trend",
                "Differentiation",
                "Supply",
                "Risk",
                "Overall",
                "Decision",
            ]
        ],
        "数据缺口": [["Gap"]],
    }
    if not run.result:
        return sheets
    for summary in run.result.executive_summary:
        sheets["执行摘要"].append(["Summary", summary])
    for candidate in run.result.candidates:
        score = candidate.score
        sheets["候选产品"].append(
            [
                candidate.candidate_id,
                candidate.asin,
                candidate.title,
                candidate.price_usd,
                candidate.cost_usd,
                candidate.estimated_margin_pct,
                score.overall if score else "",
                decision,
            ]
        )
        sheets["市场与趋势"].append(
            [
                candidate.title,
                candidate.monthly_search_volume,
                candidate.monthly_sales,
                candidate.trend_pct,
                candidate.top3_share_pct,
            ]
        )
        sheets["竞品格局"].append(
            [
                candidate.title,
                candidate.asin,
                candidate.review_count,
                candidate.rating,
                score.competition if score else "",
            ]
        )
        sheets["单位经济模型"].append(
            [
                candidate.title,
                candidate.price_usd,
                candidate.cost_usd,
                candidate.estimated_margin_pct,
                score.profitability if score else "",
            ]
        )
        sheets["供应商与MOQ"].append(
            [
                candidate.title,
                candidate.supplier_count,
                candidate.moq,
                score.supply if score else "",
            ]
        )
        flags = candidate.risk_flags or ["无已记录风险；不代表无风险"]
        for flag in flags:
            sheets["风险"].append([candidate.title, flag])
            sheets["评论痛点"].append([candidate.title, flag])
        sheets["评分与决策"].append(
            [
                candidate.title,
                score.demand if score else "",
                score.competition if score else "",
                score.profitability if score else "",
                score.trend if score else "",
                score.differentiation if score else "",
                score.supply if score else "",
                score.risk if score else "",
                score.overall if score else "",
                decision,
            ]
        )
    for item in run.result.evidence:
        sheets["数据来源说明"].append(
            [item.evidence_id, item.provider, item.tool, item.claim, item.retrieved_at]
        )
        if "keyword" in item.tool.casefold():
            sheets["关键词"].append([item.provider, item.tool, item.claim])
    for gap in run.result.gaps:
        sheets["数据缺口"].append([gap])
    return sheets


def xlsx_bytes(run: ResearchRun) -> bytes:
    workbook = Workbook()
    for index, (name, rows) in enumerate(_sheets(run).items()):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = name
        for row in rows:
            safe: list[object] = []
            for cell in row:
                value: object = (
                    "" if cell is None else str(cell) if isinstance(cell, (dict, list)) else cell
                )
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
                    value = "'" + value
                safe.append(value)
            sheet.append(safe)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
