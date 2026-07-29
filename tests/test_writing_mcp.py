"""Writing MCP adapters are optional style signals only."""

from __future__ import annotations

from amazon_copy.config import Settings
from amazon_copy.mcp.writing_mcp import (
    WritingAnalysis,
    analyze_listing_writing,
    merge_writing_into_diagnosis_issues,
    polish_listing_with_editor,
)
from amazon_copy.schemas import OptimizedListingCopy


def test_writing_analysis_disabled_by_default() -> None:
    analysis = analyze_listing_writing(
        Settings(),
        title="Gold Wedding Welcome Sign Stand",
        item_highlights="Metal frame for ceremonies",
        bullets=("Adjustable height display stand",),
    )
    assert analysis.status == "disabled"
    assert analysis.as_prompt_dict()["status"] == "disabled"


def test_writing_analysis_none_settings_is_disabled() -> None:
    analysis = analyze_listing_writing(
        None,
        title="Gold Wedding Welcome Sign Stand",
        item_highlights="Metal frame for ceremonies",
        bullets=("Adjustable height display stand",),
    )
    assert analysis.status == "disabled"
    assert polish_listing_with_editor(None, OptimizedListingCopy(
        title="Toddler Floaties 22-66 lbs",
        item_highlights="Shoulder harness arm wings for pool practice",
        bullets=(
            "Designed for 22-66 lb: Fit range for supervised swim practice.",
            "Shoulder harness: Attached arm wings for training.",
            "Swim training: Practice kicking under adult supervision.",
            "Pool ready: For pools and beaches when used as directed.",
            "Adult supervision required: Not a life-saving device.",
        ),
        backend_search_terms="swim vest buoyancy aid",
    )) is None


def test_merge_writing_issues_from_spell_and_passive() -> None:
    analysis = WritingAnalysis(
        status="ok",
        provider="writing-tools-mcp",
        misspellings=("floatation", "seperately"),
        passive_sentences=("The vest was designed by our team.",),
        readability={"flesch": 42.0},
        clarity_notes=("Prefer shorter sentences.",),
    )
    issues = merge_writing_into_diagnosis_issues(analysis)
    titles = {row["title"] for row in issues}
    assert any("拼写" in title for title in titles)
    assert any("被动" in title for title in titles)
    assert any("可读性" in title for title in titles)
    assert any("清晰度" in title for title in titles)


def test_polish_disabled_returns_none() -> None:
    listing = OptimizedListingCopy(
        title="Toddler Floaties 22-66 lbs",
        item_highlights="Shoulder harness arm wings for pool practice",
        bullets=(
            "Designed for 22-66 lb: Fit range for supervised swim practice.",
            "Shoulder harness: Attached arm wings for training.",
            "Swim training: Practice kicking under adult supervision.",
            "Pool ready: For pools and beaches when used as directed.",
            "Adult supervision required: Not a life-saving device.",
        ),
        backend_search_terms="swim vest buoyancy aid",
    )
    assert polish_listing_with_editor(Settings(), listing) is None
