"""Dedicated rule-isolated English listing reviewer contract."""

from __future__ import annotations

import json

from amazon_copy.agents.english_listing_reviewer import (
    EnglishListingReview,
    EnglishReviewIssue,
    apply_english_review_suggestions,
    review_english_listing,
)
from amazon_copy.review.models import ReviewFinding
from amazon_copy.schemas import OptimizedListingCopy


class _ReviewerLLM:
    def __init__(self) -> None:
        self.system = ""
        self.payload: dict[str, object] = {}

    @property
    def call_count(self) -> int:
        return 1

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del kwargs
        self.system = system
        self.payload = json.loads(user)
        return json.dumps(
            {
                "issues": [
                    {
                        "location": "Bullet Point 1",
                        "original": "10 Natural River s",
                        "issue_type": "truncation",
                        "suggestion": "10 Natural River Stones",
                    }
                ]
            }
        )


class _NoOpReviewerLLM:
    @property
    def call_count(self) -> int:
        return 1

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        return json.dumps(
            {
                "issues": [
                    {
                        "location": "Bullet Point 1",
                        "original": "each with a smooth surface is ready for painting",
                        "issue_type": "grammar",
                        "suggestion": "each with a smooth surface is ready for painting",
                    },
                    {
                        "location": "Bullet Point 1",
                        "original": "text that is not present",
                        "issue_type": "grammar",
                        "suggestion": "replacement",
                    },
                ]
            }
        )


class _BoundaryBreakingReviewerLLM:
    @property
    def call_count(self) -> int:
        return 1

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        return json.dumps(
            {
                "issues": [
                    {
                        "location": "Bullet Point 1",
                        "original": "each.",
                        "issue_type": "truncation",
                        "suggestion": "each",
                    }
                ]
            }
        )


def test_reviewer_receives_only_listing_fields_and_builds_feedback_table() -> None:
    llm = _ReviewerLLM()
    listing = OptimizedListingCopy(
        title="Natural River Stones for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=["10 Natural River s: Includes ten pieces."],
        backend_search_terms="river stones painting",
    )

    result = review_english_listing(listing, llm=llm)

    assert set(llm.payload) == {
        "title",
        "item_highlights",
        "bullet_points",
        "backend_search_terms",
        "active_blocking_rules",
    }
    assert llm.payload["active_blocking_rules"] == []
    assert "active_blocking_rules" in llm.system
    assert result.issues[0].issue_type == "truncation"
    table = result.as_markdown_table()
    assert "| Location | Original problem | Issue type | Improvement suggestion |" in table
    assert "10 Natural River Stones" in table


def test_reviewer_receives_current_blocking_rules_as_dynamic_context() -> None:
    llm = _ReviewerLLM()
    listing = OptimizedListingCopy(
        title="Natural River Stones for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=("10 Natural River s: Includes ten pieces.",),
        backend_search_terms="river stones painting",
    )
    finding = ReviewFinding(
        code="unsupported_claim",
        severity="BLOCK",
        field="Bullet Point 1",
        message_zh="存在未经证据支持的声明",
        claim_terms=("river s",),
    )

    review_english_listing(listing, llm=llm, rule_findings=(finding,))

    assert llm.payload["active_blocking_rules"] == [
        {
            "code": "unsupported_claim",
            "field": "Bullet Point 1",
            "matched_locations": ["Bullet Point 1"],
            "message": "存在未经证据支持的声明",
            "evidence_required": "",
            "claim_terms": ["river s"],
        }
    ]


def test_review_suggestions_patch_only_the_named_fragment_and_field() -> None:
    listing = OptimizedListingCopy(
        title="Natural River Rocks for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=(
            "Pack Details: Includes 10 natural river s for painting.",
            "Creative Uses: Make garden markers and desk decorations.",
        ),
        backend_search_terms="river rocks painting craft",
    )
    review = EnglishListingReview(
        issues=(
            EnglishReviewIssue(
                location="Bullet Point 1",
                original="river s",
                issue_type="truncation",
                suggestion="river stones",
            ),
        )
    )

    revised = apply_english_review_suggestions(listing, review)

    assert revised.bullets[0] == (
        "Pack Details: Includes 10 natural river stones for painting."
    )
    assert revised.title == listing.title
    assert revised.item_highlights == listing.item_highlights
    assert revised.bullets[1] == listing.bullets[1]
    assert revised.backend_search_terms == listing.backend_search_terms


def test_rule_suggestion_can_delete_only_an_unsupported_claim() -> None:
    listing = OptimizedListingCopy(
        title="Natural River Rocks for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=("Smooth Surface: Guaranteed results for painting projects.",),
        backend_search_terms="river rocks painting craft",
    )
    review = EnglishListingReview(
        issues=(
            EnglishReviewIssue(
                location="Bullet Point 1",
                original="Guaranteed ",
                issue_type="rule_compliance",
                suggestion="",
            ),
        )
    )

    revised = apply_english_review_suggestions(listing, review)

    assert revised.bullets == ("Smooth Surface: results for painting projects.",)


def test_reviewer_discards_identical_and_unapplicable_suggestions() -> None:
    listing = OptimizedListingCopy(
        title="Natural River Rocks for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=(
            "Includes 10 rocks, each with a smooth surface is ready for painting.",
        ),
        backend_search_terms="river rocks painting craft",
    )

    review = review_english_listing(listing, llm=_NoOpReviewerLLM())

    assert review.issues == ()


def test_reviewer_rejects_edit_that_joins_two_sentences() -> None:
    listing = OptimizedListingCopy(
        title="Natural River Rocks for Painting",
        item_highlights="Smooth stones for creative projects.",
        bullets=(
            "Includes 10 rocks measuring 2-3 inches each. "
            "Their smooth surfaces are ready for painting.",
        ),
        backend_search_terms="river rocks painting craft",
    )

    review = review_english_listing(listing, llm=_BoundaryBreakingReviewerLLM())

    assert review.issues == ()
