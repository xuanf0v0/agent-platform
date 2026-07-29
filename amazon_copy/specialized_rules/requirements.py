"""Closed fact requirements bound to reviewed specialized profile filenames."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from amazon_copy.review.models import FactCategory, FactRequirement
from amazon_copy.specialized_rules.catalog import (
    ALLOWLISTED_PROFILE_FILENAMES,
    RULE_PROFILES,
)
from amazon_copy.specialized_rules.models import SpecializedRuleSnapshot


@dataclass(frozen=True, slots=True)
class ProfileRequirementMetadata:
    """Reviewed fact categories for one exact allowlisted rule profile."""

    categories: tuple[FactCategory, ...]


_PRODUCT_CATEGORIES: Final = tuple(FactCategory)
_PROCESS_CATEGORIES: Final = (
    FactCategory.BOM,
    FactCategory.COUNT,
    FactCategory.DIMENSION,
    FactCategory.COMPATIBILITY,
    FactCategory.SAFETY,
    FactCategory.PERFORMANCE,
    FactCategory.CERTIFICATION,
    FactCategory.VARIATION,
    FactCategory.EXCLUSION,
)
PROFILE_REQUIREMENT_METADATA: Final[Mapping[str, ProfileRequirementMetadata]] = MappingProxyType(
    {
        profile.filename: ProfileRequirementMetadata(
            categories=(_PRODUCT_CATEGORIES if profile.kind == "product" else _PROCESS_CATEGORIES)
        )
        for profile in RULE_PROFILES
    }
)


def _combine_pattern(*parts: str) -> str:
    return "".join(parts)


SWIM_REQUIREMENTS: Final[tuple[FactRequirement, ...]] = (
    FactRequirement(
        code="swim_weight_range",
        category=FactCategory.DIMENSION,
        fact_key="weight_range",
        key_aliases=("fit_weight",),
        claim_patterns=(
            _combine_pattern(
                r"\b\d+(?:\.\d+)?\s*[-\u2013]\s*",
                r"\d+(?:\.\d+)?\s*(?:lb|lbs|pounds?)\b",
            ),
        ),
        evidence_needed="approved child-weight range",
    ),
    FactRequirement(
        code="swim_age_range",
        category=FactCategory.COMPATIBILITY,
        fact_key="age_range",
        key_aliases=("recommended_age",),
        claim_patterns=(
            _combine_pattern(
                r"\b(?:ages?\s*)?\d+\s*[-\u2013]\s*",
                r"\d+\s*(?:years?|yrs?)(?: old)?\b",
            ),
        ),
        evidence_needed="approved age range",
    ),
    FactRequirement(
        code="swim_components",
        category=FactCategory.BOM,
        fact_key="included_structure",
        key_aliases=("crotch_strap", "shoulder_harness", "arm_bands"),
        claim_patterns=(r"\b(?:crotch strap|shoulder harness|detachable arm bands?)\b",),
        evidence_needed="selected-child packaging BOM",
    ),
    FactRequirement(
        code="swim_certification",
        category=FactCategory.CERTIFICATION,
        fact_key="certification",
        key_aliases=("uscg_approval", "cpc", "cpsc"),
        claim_patterns=(r"\b(?:USCG|CPC|CPSC|Coast Guard)\b[^.;\n]{0,24}",),
        evidence_needed="official compliance or approval document",
    ),
)


_WEDDING_REQUIREMENTS: Final = (
    FactRequirement(
        code="wedding_height_settings",
        category=FactCategory.DIMENSION,
        fact_key="height_settings",
        key_aliases=("two_heights", "adjustable_heights"),
        claim_patterns=(
            r"\b(?:two|2)[ -]height(?:s| settings?)?\b",
            r"\bheight settings?\b",
            _combine_pattern(
                r"\b\d+(?:\.\d+)?\s*(?:in(?:ches)?|ft|feet)\s+",
                r"(?:and|or|/)\s+\d+(?:\.\d+)?\s*(?:in(?:ches)?|ft|feet)\b",
            ),
        ),
        evidence_needed="approved height-setting specification",
    ),
    FactRequirement(
        code="wedding_overall_dimensions",
        category=FactCategory.DIMENSION,
        fact_key="overall_dimensions",
        key_aliases=("frame_dimensions", "overall_size"),
        claim_patterns=(
            r"\b(?:overall|frame) (?:size|dimensions?)\b[^.;\n]{0,36}",
            _combine_pattern(
                r"\b\d+(?:\.\d+)?\s*[x\u00d7]\s*\d+(?:\.\d+)?\s*",
                r"[x\u00d7]\s*\d+(?:\.\d+)?\s*(?:in(?:ches)?|cm)\b",
            ),
        ),
        evidence_needed="approved overall-dimension specification",
    ),
    FactRequirement(
        code="wedding_base_dimensions",
        category=FactCategory.DIMENSION,
        fact_key="base_dimensions",
        key_aliases=("base_size", "footprint"),
        claim_patterns=(
            _combine_pattern(
                r"\b(?:base|footprint)[^.;\n]{0,24}\d+(?:\.\d+)?\s*",
                r"[x\u00d7]\s*\d+",
            ),
        ),
        evidence_needed="approved base-dimension specification",
    ),
    FactRequirement(
        code="wedding_sign_thickness",
        category=FactCategory.DIMENSION,
        fact_key="sign_thickness",
        key_aliases=("maximum_sign_thickness", "board_thickness"),
        claim_patterns=(
            _combine_pattern(
                r"\b(?:up to|max(?:imum)?(?: tested)?)\s+\d+(?:\.\d+)?\s*",
                r"(?:in(?:ch(?:es)?)?|cm|mm)",
                r"(?:\s*/\s*\d+(?:\.\d+)?\s*(?:cm|mm))?",
                r"(?:\s+(?:sign|board))?(?:\s+thick(?:ness)?)?\b",
            ),
        ),
        evidence_needed="tested maximum sign-thickness record",
    ),
    FactRequirement(
        code="wedding_straps",
        category=FactCategory.BOM,
        fact_key="included_straps",
        key_aliases=("strap_count", "strap_material", "strap_colors"),
        claim_patterns=(r"\b(?:includes?|with|comes? with)\b[^.;\n]{0,30}\bstraps?\b",),
        evidence_needed="package BOM confirming strap count, material, and colors",
    ),
    FactRequirement(
        code="wedding_water_bags",
        category=FactCategory.BOM,
        fact_key="included_water_bags",
        key_aliases=("water_bag_count", "water_bags"),
        claim_patterns=(r"\b(?:includes?|with|comes? with)\b[^.;\n]{0,30}\bwater bags?\b",),
        evidence_needed="package BOM confirming water-bag count",
    ),
    FactRequirement(
        code="wedding_screws",
        category=FactCategory.BOM,
        fact_key="included_screws",
        key_aliases=("screws", "package_contents"),
        claim_patterns=(
            r"\bwith screws?\b",
            r"\bscrews? (?:are )?included\b",
            r"\bincludes?\b[^.;\n]{0,20}\bscrews?\b",
        ),
        evidence_needed="package BOM confirming included screws",
        authorization_mode="affirmative",
    ),
    FactRequirement(
        code="wedding_sign_inclusion",
        category=FactCategory.EXCLUSION,
        fact_key="sign_included",
        key_aliases=("sign_excluded", "package_exclusions"),
        claim_patterns=(r"\bsign(?: board| poster)? (?:is )?(?:not )?included\b",),
        evidence_needed="package BOM confirming whether the sign is included",
        authorization_mode="affirmative",
    ),
    FactRequirement(
        code="wedding_decorations_inclusion",
        category=FactCategory.EXCLUSION,
        fact_key="decorations_included",
        key_aliases=("decorations_excluded", "package_exclusions"),
        claim_patterns=(
            _combine_pattern(
                r"\b(?:decorations?|flowers?|greenery|d[eé]cor) ",
                r"(?:are |is )?(?:not )?included\b",
            ),
        ),
        evidence_needed="package BOM confirming decoration exclusions",
        authorization_mode="affirmative",
    ),
    FactRequirement(
        code="wedding_outdoor_conditions",
        category=FactCategory.PERFORMANCE,
        fact_key="outdoor_use_conditions",
        key_aliases=("outdoor_use", "supervised_outdoor_use"),
        claim_patterns=(
            r"\bsupervised outdoor (?:displays?|setups?|use)\b",
            r"\b(?:designed|suitable|recommended) for (?:supervised )?outdoor\b[^.;\n]{0,20}",
        ),
        evidence_needed="approved outdoor-use conditions and supervision requirements",
    ),
    FactRequirement(
        code="wedding_wind",
        category=FactCategory.PERFORMANCE,
        fact_key="wind_performance",
        key_aliases=("wind_resistance",),
        claim_patterns=(r"\b(?:wind[ -]?resistant|windproof|stable in (?:any )?wind)\b",),
        evidence_needed="本产品的风况测试报告或经批准的产品技术资料",
    ),
    FactRequirement(
        code="wedding_rust",
        category=FactCategory.PERFORMANCE,
        fact_key="rust_performance",
        key_aliases=("rust_resistance", "corrosion_resistance"),
        claim_patterns=(r"\b(?:rust[ -]?proof|anti[ -]?rust|rust[ -]?resistant)\b",),
        evidence_needed="本产品的材质、涂层规格或耐腐蚀测试报告",
    ),
    FactRequirement(
        code="wedding_heavy_duty",
        category=FactCategory.PERFORMANCE,
        fact_key="heavy_duty",
        key_aliases=("load_capacity",),
        claim_patterns=(r"\bheavy[ -]?duty\b",),
        evidence_needed="本产品的承重、材料规格或耐久测试报告",
        authorization_mode="affirmative",
    ),
)

_PROFILE_REQUIREMENTS: Final[Mapping[str, tuple[FactRequirement, ...]]] = MappingProxyType(
    {
        "us-adjustable-wedding-sign-stands.md": _WEDDING_REQUIREMENTS,
        "us-childrens-swim-aid-listing-audit.md": SWIM_REQUIREMENTS,
    }
)


def requirements_for_snapshots(
    snapshots: tuple[SpecializedRuleSnapshot, ...],
) -> tuple[FactRequirement, ...]:
    """Return code-reviewed requirements for loaded filenames only."""
    return tuple(
        requirement
        for snapshot in snapshots
        for requirement in _PROFILE_REQUIREMENTS.get(snapshot.profile_filename, ())
    )


__all__ = [
    "ALLOWLISTED_PROFILE_FILENAMES",
    "PROFILE_REQUIREMENT_METADATA",
    "ProfileRequirementMetadata",
    "requirements_for_snapshots",
]
