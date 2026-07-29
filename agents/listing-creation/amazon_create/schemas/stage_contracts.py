"""Machine-readable output contracts for the required creation workflow."""

from typing import Final

from amazon_create.schemas.workflow import CreationStage

STAGE_REQUIRED_KEYS: Final[dict[CreationStage, tuple[str, ...]]] = {
    CreationStage.AUDIENCE: (
        "category_market_overview",
        "audience_profiles",
        "purchase_motivations",
        "shopper_concerns",
        "positive_reviews",
        "negative_reviews",
        "market_conclusion",
        "data_notes",
    ),
    CreationStage.PRODUCT: (
        "parameter_analysis",
        "consistency_checks",
        "product_conclusion",
    ),
    CreationStage.COMPETITOR: (
        "selection_basis",
        "basic_comparison",
        "feature_comparison",
        "title_analysis",
        "bullet_analysis",
        "promise_review_consistency",
        "competitor_conclusion",
    ),
    CreationStage.SELLING_POINTS: ("selling_points",),
    CreationStage.KEYWORDS: (
        "keyword_categories",
        "top20_roots",
        "top20_keywords",
        "keyword_allocation",
    ),
    CreationStage.FINAL_COPY: (
        "title_variants",
        "recommended_variant",
        "bullets",
        "product_description",
        "search_terms",
        "shopping_questions",
        "compliance_risks",
        "return_risks",
        "creation_logic_zh",
    ),
}


STAGE_OUTPUT_INSTRUCTIONS: Final[dict[CreationStage, str]] = {
    CreationStage.AUDIENCE: """
Return all keys below. Chinese analysis only.
category_market_overview[]: {dimension,market_situation,listing_impact} covering category,
forms, material/structure/configuration, dimensions/count/specs, price bands, maturity,
homogeneity, seasonality, peak season, scenarios, core needs, entry barriers and differentiation.
audience_profiles[]: {audience_type,typical_traits,estimated_share,core_needs,scenarios,
purchase_barriers,estimate_basis}; include core, secondary, supplemental and not-recommended.
purchase_motivations[]: 10-20 unique {rank,motivation,need,importance_or_share,placement}.
shopper_concerns[]: 10-20 {rank,question,importance,impact_if_unclear,placement}.
positive_reviews[]: {rank,content,need,frequency_or_importance,convertible_selling_point}.
negative_reviews[]: {rank,content,root_cause,frequency_or_severity,handling}; cover return reasons,
expectation gaps and unresolved competitor problems. market_conclusion must contain seven conclusions.
data_notes[] must state source/time/sample where available; otherwise label ranges as 方向性估算.
""",
    CreationStage.PRODUCT: """
Return parameter_analysis[] with product_parameter_or_function,meaning,consumer_need,audience,
scenario,selling_point_value,recommended_location and classification. Return consistency_checks[]
covering manual/image consistency, product vs package dimensions, unit vs set count, material,
claim evidence, pictured props, age/weight and certification/testing. Unknown values must be 待确认.
Return product_conclusion with core conditions, basics, differentiators and placement decisions.
""",
    CreationStage.COMPETITOR: """
Use 3-5 competitors when evidence is available, never more than 10. If user supplied none, select
direct, leading, same-price, same-spec and differentiated candidates and explain selection_basis;
when live evidence is unavailable, state the data gap and never invent ASIN, price, rating or reviews.
Return basic_comparison[], feature_comparison[], title_analysis[], bullet_analysis[],
promise_review_consistency[] and competitor_conclusion with the seven required decisions.
Competitor attributes are market context only and can never become product facts.
""",
    CreationStage.SELLING_POINTS: """
Return exactly five selling_points[] ordered by priority. Each row contains priority,core_selling_point,
consumer_need,product_evidence,competitor_difference,recommended_location. Cover core value,
material/structure/performance, pain solution, audience/scenario and multi-use value. Do not use risks,
limitations, warnings, purchase reminders or service as a core selling point.
""",
    CreationStage.KEYWORDS: """
Return keyword_categories covering category, use, traffic, conversion, long-tail, attribute, material,
structure, function, performance, scenario, audience, pain, size, count, compatibility, synonyms,
misspellings, competitor advantages, product gaps, irrelevant and prohibited/infringing terms.
Return exactly 20 top20_roots[] with rank,root,type,search_intent,relevance,recommended_location;
exactly 20 top20_keywords[] with rank,keyword,search_intent,traffic_level,conversion_intent,
product_match,recommended_location; and keyword_allocation[] across Title, Item Highlights, Bullet,
Description and Search Terms. Never sacrifice natural language for coverage.
""",
    CreationStage.FINAL_COPY: """
Return title_variants with exactly A/B/C strategies: SEO与转化平衡、核心差异化、简洁高可读性.
Every non-media US Title must be 65-75 characters and never exceed 75. Each variant includes one
natural Item Highlights no longer than 125 characters. Set recommended_variant to A, B or C and also
copy that variant into title/item_highlights compatibility fields. Return exactly five bullets, each
with text,text_zh,purchase_intent_zh,covered_keywords and chars; use 3-7 Title Case lead words, one
purchase question, Feature+Benefit+real scenario, 210-300 suggested chars and <=320 chars. Risks and
limitations belong in description/risk tables, never bullets. Return a 3-4 paragraph 900-1400 char
product_description plus translation and character count. Return lowercase punctuation-free Search
Terms, excluding brands/ASINs/covered Title phrases, with chars and UTF-8 bytes. Return exactly 10
shopping_questions with coverage/location/clarity/missing information, compliance_risks[],
return_risks[], creation_logic_zh, and final_report. Never fabricate any product fact.
""",
}


def missing_stage_keys(stage: CreationStage, payload: dict[str, object]) -> tuple[str, ...]:
    """Return mandatory artifact keys absent from one generated stage."""
    return tuple(key for key in STAGE_REQUIRED_KEYS.get(stage, ()) if key not in payload)


def stage_payload_issues(stage: CreationStage, payload: dict[str, object]) -> tuple[str, ...]:
    """Validate cardinalities that are essential to the requested workflow."""
    issues = list(missing_stage_keys(stage, payload))
    expected_counts = {
        (CreationStage.AUDIENCE, "purchase_motivations"): (10, 20),
        (CreationStage.AUDIENCE, "shopper_concerns"): (10, 20),
        (CreationStage.SELLING_POINTS, "selling_points"): (5, 5),
        (CreationStage.KEYWORDS, "top20_roots"): (20, 20),
        (CreationStage.KEYWORDS, "top20_keywords"): (20, 20),
        (CreationStage.FINAL_COPY, "title_variants"): (3, 3),
        (CreationStage.FINAL_COPY, "bullets"): (5, 5),
        (CreationStage.FINAL_COPY, "shopping_questions"): (10, 10),
    }
    for (contract_stage, key), (minimum, maximum) in expected_counts.items():
        if stage != contract_stage or key not in payload:
            continue
        value = payload[key]
        size = len(value) if isinstance(value, list) else 0
        if not minimum <= size <= maximum:
            issues.append(f"{key}数量应为{minimum}" if minimum == maximum else f"{key}数量应为{minimum}-{maximum}")
    return tuple(issues)


__all__ = ["STAGE_OUTPUT_INSTRUCTIONS", "STAGE_REQUIRED_KEYS", "stage_payload_issues"]
