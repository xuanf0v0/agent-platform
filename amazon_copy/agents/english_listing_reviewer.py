"""Rule-isolated US English listing reviewer used inside the quality loop."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from amazon_copy.prompt_loader import load_prompt
from amazon_copy.utils.json_extract import JsonExtractError, extract_json_object

if TYPE_CHECKING:
    from amazon_copy.llm import LLMClient
    from amazon_copy.review.models import ReviewFinding
    from amazon_copy.schemas import OptimizedListingCopy

IssueType = Literal[
    "spelling",
    "grammar",
    "word_choice",
    "unnatural_expression",
    "truncation",
    "us_localization",
    "rule_compliance",
]


class EnglishReviewIssue(BaseModel):
    """One actionable English copy defect at an exact listing location."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    location: str = Field(min_length=1)
    original: str = Field(min_length=1)
    issue_type: IssueType
    suggestion: str


class EnglishListingReview(BaseModel):
    """Structured output from the isolated US English reviewer."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    issues: tuple[EnglishReviewIssue, ...] = ()

    def as_markdown_table(self) -> str:
        """Render reviewer issues in the feedback table required by the loop."""
        if not self.issues:
            return ""
        lines = [
            "| Location | Original problem | Issue type | Improvement suggestion |",
            "|---|---|---|---|",
        ]
        for issue in self.issues:
            cells = (
                issue.location,
                issue.original,
                issue.issue_type,
                issue.suggestion,
            )
            escaped = [cell.replace("|", "\\|").replace("\n", " ") for cell in cells]
            lines.append("| " + " | ".join(escaped) + " |")
        return "\n".join(lines)


class EnglishListingReviewError(ValueError):
    """Raised when the dedicated reviewer does not return its contract."""


def review_english_listing(
    listing: OptimizedListingCopy,
    *,
    llm: LLMClient,
    rule_findings: tuple[ReviewFinding, ...] = (),
) -> EnglishListingReview:
    """Review generated copy plus the active blocking postflight findings."""
    payload = {
        "title": listing.title,
        "item_highlights": listing.item_highlights,
        "bullet_points": list(listing.bullets),
        "backend_search_terms": listing.backend_search_terms,
        "active_blocking_rules": [
            {
                "code": finding.code,
                "field": finding.field,
                "matched_locations": _finding_locations(listing, finding),
                "message": finding.message_zh,
                "evidence_required": finding.evidence_required,
                "claim_terms": list(finding.claim_terms),
            }
            for finding in rule_findings
            if finding.severity == "BLOCK"
        ],
    }
    try:
        raw = llm.complete(
            load_prompt("english_listing_reviewer"),
            json.dumps(payload, ensure_ascii=False),
            temperature=0.0,
        )
    except Exception as error:  # isolate provider failures at agent boundary
        message = "English listing reviewer service call failed"
        raise EnglishListingReviewError(message) from error
    try:
        review = EnglishListingReview.model_validate(extract_json_object(raw))
    except (JsonExtractError, ValueError) as error:
        message = "English listing reviewer returned an invalid response"
        raise EnglishListingReviewError(message) from error
    return _actionable_review(listing, review)


def _finding_locations(
    listing: OptimizedListingCopy,
    finding: ReviewFinding,
) -> list[str]:
    """Resolve broad `listing` findings to fields containing their claim terms."""
    fields = {
        "Title": listing.title,
        "Item Highlights": listing.item_highlights,
        **{
            f"Bullet Point {index}": bullet
            for index, bullet in enumerate(listing.bullets, start=1)
        },
        "Backend Search Terms": listing.backend_search_terms,
    }
    terms = tuple(term.casefold() for term in finding.claim_terms)
    if terms:
        matched = [
            location
            for location, text in fields.items()
            if any(
                re.search(
                    rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
                    text,
                    flags=re.IGNORECASE,
                )
                for term in terms
            )
        ]
        if matched:
            return matched
    field = finding.field.strip().casefold()
    aliases = {
        "title": "Title",
        "item_highlights": "Item Highlights",
        "item highlights": "Item Highlights",
        "backend_search_terms": "Backend Search Terms",
        "backend search terms": "Backend Search Terms",
    }
    if field in aliases:
        return [aliases[field]]
    if field == "bullets":
        return [f"Bullet Point {index}" for index in range(1, len(listing.bullets) + 1)]
    return []


def _actionable_review(
    listing: OptimizedListingCopy,
    review: EnglishListingReview,
) -> EnglishListingReview:
    """Keep only exact, changing, non-duplicate edits that can be applied."""
    fields = {
        "title": listing.title,
        "item highlights": listing.item_highlights,
        "item highlight": listing.item_highlights,
        "backend search terms": listing.backend_search_terms,
    }
    for index, bullet in enumerate(listing.bullets, start=1):
        fields[f"bullet point {index}"] = bullet

    actionable: list[EnglishReviewIssue] = []
    seen_targets: set[tuple[str, str]] = set()
    for issue in review.issues:
        location = issue.location.strip().casefold()
        field_text = fields.get(location)
        original = issue.original
        suggestion = issue.suggestion.strip()
        target = (location, original)
        occurrence = field_text.find(original) if field_text is not None else -1
        suffix = (
            field_text[occurrence + len(original) :]
            if field_text is not None and occurrence >= 0
            else ""
        )
        removes_required_sentence_boundary = bool(
            original.rstrip().endswith((".", "!", "?"))
            and not suggestion.rstrip().endswith((".", "!", "?"))
            and suffix.lstrip()[:1].isupper()
        )
        if (
            field_text is None
            or original not in field_text
            or original.strip() == suggestion
            or target in seen_targets
            or removes_required_sentence_boundary
        ):
            continue
        seen_targets.add(target)
        actionable.append(issue.model_copy(update={"suggestion": suggestion}))
    return EnglishListingReview(issues=tuple(actionable))


def apply_english_review_suggestions(
    listing: OptimizedListingCopy,
    review: EnglishListingReview,
) -> OptimizedListingCopy:
    """Apply exact reviewer replacements without rewriting unaffected fields."""
    title = listing.title
    highlights = listing.item_highlights
    bullets = list(listing.bullets)
    backend = listing.backend_search_terms

    def replace_once(text: str, original: str, suggestion: str) -> str:
        if not original or original not in text:
            return text
        return text.replace(original, suggestion.strip(), 1)

    for issue in review.issues:
        location = issue.location.strip().casefold()
        if location == "title":
            title = replace_once(title, issue.original, issue.suggestion)
        elif location in {"item highlights", "item highlight"}:
            highlights = replace_once(highlights, issue.original, issue.suggestion)
        elif location == "backend search terms":
            backend = replace_once(backend, issue.original, issue.suggestion)
        else:
            match = re.fullmatch(r"bullet point\s+(\d+)", location)
            if match is None:
                continue
            index = int(match.group(1)) - 1
            if 0 <= index < len(bullets):
                bullets[index] = replace_once(
                    bullets[index], issue.original, issue.suggestion
                )

    return listing.model_copy(
        update={
            "title": title,
            "item_highlights": highlights,
            "bullets": tuple(bullets),
            "backend_search_terms": backend,
        }
    )
__all__ = [
    "EnglishListingReview",
    "EnglishListingReviewError",
    "EnglishReviewIssue",
    "apply_english_review_suggestions",
    "review_english_listing",
]
