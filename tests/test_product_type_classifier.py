"""Tests for heuristic + LLM specialized product-type classification."""

from __future__ import annotations

import json

from amazon_copy.agents.product_type_classifier import (
    classify_product_type_llm,
    resolve_product_type,
)
from amazon_copy.automatic_context import infer_product_type
from amazon_copy.schemas import SourceListingCopy
from amazon_copy.specialized_rules.product_types import (
    catalog_product_types,
    infer_product_type_heuristic,
)


def test_catalog_product_types_include_known_profiles() -> None:
    types = catalog_product_types("US")
    assert "SIGN_DISPLAY_STAND" in types
    assert "SWIM_VEST" in types
    assert "DESK_ORGANIZER" in types


def test_heuristic_covers_expanded_phrases() -> None:
    assert infer_product_type_heuristic("Gold Wedding Welcome Sign Stand") == "SIGN_DISPLAY_STAND"
    assert infer_product_type_heuristic("Toddler Swim Vest for Pool") == "SWIM_VEST"
    assert infer_product_type_heuristic("Mesh Zipper Pouch Set") == "MESH_ZIPPER_POUCH"
    assert infer_product_type_heuristic("Acoustic Wood Slat Wall Panel") == (
        "ACOUSTIC_WOOD_SLAT_WALL_PANEL"
    )
    assert infer_product_type("Wedding table decorations and centrepieces") is None


def test_resolve_product_type_prefers_heuristic_over_llm() -> None:
    class _FailLLM:
        call_count = 0

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, user, kwargs
            raise AssertionError("LLM should not run when heuristic matches")

    source = SourceListingCopy(
        title="Gold Adjustable Wedding Welcome Sign Stand",
        bullets=["Metal frame"],
    )
    result = resolve_product_type(source, marketplace="US", llm=_FailLLM())
    assert result == "SIGN_DISPLAY_STAND"


def test_resolve_product_type_uses_llm_when_heuristic_misses() -> None:
    class _ClassifierLLM:
        call_count = 0

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            self.call_count += 1
            payload = json.loads(user)
            assert "DESK_ORGANIZER" in payload["allowed_product_types"]
            return json.dumps(
                {
                    "product_type": "DESK_ORGANIZER",
                    "confidence": 0.91,
                    "rationale": "drawer caddy for pens and stationery",
                }
            )

    # No catalog phrase in title/bullets — must go through LLM.
    source = SourceListingCopy(
        title="Modular Drawer Caddy System for Stationery",
        bullets=["Keeps pens and notes tidy beside the keyboard"],
    )
    assert infer_product_type_heuristic(
        source.title + " " + " ".join(source.bullets)
    ) is None
    llm = _ClassifierLLM()
    result = resolve_product_type(source, marketplace="US", llm=llm)
    assert llm.call_count == 1
    assert result == "DESK_ORGANIZER"


def test_classify_rejects_low_confidence() -> None:
    class _LowLLM:
        call_count = 0

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, user, kwargs
            self.call_count += 1
            return json.dumps(
                {
                    "product_type": "DESK_ORGANIZER",
                    "confidence": 0.2,
                    "rationale": "guess",
                }
            )

    source = SourceListingCopy(title="Generic Household Item", bullets=["Useful everyday product"])
    assert classify_product_type_llm(source, marketplace="US", llm=_LowLLM()) is None
