import amazon_copy.review.models as review_models
from amazon_copy.review.fact_resolution import supports_affirmative_term
from amazon_copy.review.models import (
    EvidenceSource,
    FactClaim,
    ListingReviewRequest,
    MarketplaceRules,
    VariationRole,
)
from amazon_copy.review.service import review_listing


def _request(**overrides: object) -> ListingReviewRequest:
    values: dict[str, object] = {
        "title": "10 Large River Rocks for Painting, 2-3 Inch Smooth Stones",
        "item_highlights": "Natural stones for painting projects",
        "bullets": (
            "PAINTING SURFACE: Ten smooth stones provide room for detailed designs",
            "SIZE AND MATERIAL: Each natural river rock measures approximately 2-3 inches",
            "CREATIVE OPTIONS: Suitable for acrylic paint when the surface is prepared",
            "DISPLAY IDEAS: Use finished stones for garden markers or desk decorations",
            "NATURAL VARIATION: Shape color and texture vary from stone to stone",
        ),
        "backend_search_terms": "painting rocks stones craft river rock art",
        "rules": MarketplaceRules(marketplace="US", product_type="ART_CRAFT_MATERIAL"),
        "variation_role": VariationRole.STANDALONE,
        "claims": (
            FactClaim(
                key="quantity",
                value="10",
                source=EvidenceSource.PACKAGING_BOM_USER,
                sku_scope="all",
            ),
            FactClaim(
                key="size",
                value="2-3 inches",
                source=EvidenceSource.PACKAGING_BOM_USER,
                sku_scope="all",
            ),
            FactClaim(
                key="material",
                value="natural river stone",
                source=EvidenceSource.PACKAGING_BOM_USER,
                sku_scope="all",
            ),
        ),
        "primary_terms": ("painting rocks", "river rocks"),
        "secondary_terms": ("craft stones", "rock art"),
    }
    values.update(overrides)
    return ListingReviewRequest.model_validate(values)


def test_clean_listing_passes_without_blocking_findings() -> None:
    report = review_listing(_request())
    assert report.status != "BLOCK"
    assert report.can_optimize is True
    assert len(report.scores) == 10
    assert report.overall_score is None
    # New quality-of-life WARNs are expected for suboptimal-but-legal content.
    codes = {finding.code for finding in report.findings if finding.severity == "WARN"}
    assert codes <= {"HIGHLIGHTS_DENSITY", "SEARCH_TERM_DUPLICATION"}


def test_hard_field_limits_and_search_term_bytes_block() -> None:
    report = review_listing(
        _request(
            title="X" * 76,
            item_highlights="Y" * 126,
            backend_search_terms="石" * 84,
        )
    )
    codes = {finding.code for finding in report.findings if finding.severity == "BLOCK"}
    assert {"TITLE_LENGTH", "HIGHLIGHTS_LENGTH", "SEARCH_TERMS_BYTES"} <= codes
    assert report.can_optimize is False


def test_title_repetition_written_numbers_and_parent_child_spec_are_reported() -> None:
    report = review_listing(
        _request(
            title="Ten Rock Rock Rock Painting Kit Red 10-Piece Set",
            variation_role=VariationRole.PARENT,
            child_only_terms=("Red", "10-Piece"),
        )
    )
    by_code = {finding.code: finding.severity for finding in report.findings}
    assert by_code["TITLE_WORD_REPETITION"] == "WARN"
    assert by_code["TITLE_WRITTEN_NUMBER"] == "WARN"
    assert by_code["PARENT_CHILD_SPEC"] == "BLOCK"


def test_unverified_performance_and_safety_claims_block() -> None:
    report = review_listing(
        _request(
            bullets=(
                "WATERPROOF: Waterproof stones work with all markers",
                "SAFE HANDLING: Non-toxic material is gentle on hands",
                "HEAVY DUTY: Heavy duty stones securely hold every design",
                "CREATIVE USE: Designed for craft projects",
                "PACK CONTENTS: Includes ten natural stones",
            )
        )
    )
    codes = {finding.code for finding in report.findings if finding.severity == "BLOCK"}
    assert "UNVERIFIED_PERFORMANCE" in codes
    assert "UNVERIFIED_SAFETY" in codes
    assert "OVERBROAD_COMPATIBILITY" in codes


def test_safe_rule_does_not_match_inside_safely() -> None:
    report = review_listing(
        _request(
            bullets=(
                "CARE TIPS: Store painted stones safely after they dry",
                "PAINTING: Smooth stones for acrylic painting",
                "PROJECTS: Use finished stones for craft projects",
                "DISPLAY: Place painted stones on a desk or shelf",
                "CONTENTS: Includes natural stones for decorating",
            )
        )
    )

    codes = {finding.code for finding in report.findings}
    assert "UNVERIFIED_SAFETY" not in codes


def test_higher_priority_evidence_wins_and_equal_priority_conflict_blocks() -> None:
    resolved = review_listing(
        _request(
            claims=(
                FactClaim(
                    key="quantity",
                    value="10",
                    source=EvidenceSource.PACKAGING_BOM_USER,
                    sku_scope="all",
                ),
                FactClaim(
                    key="quantity",
                    value="12",
                    source=EvidenceSource.COMPETITOR_LANGUAGE,
                    sku_scope="all",
                ),
            )
        )
    )
    assert resolved.resolved_facts[0].value == "10"
    assert all(f.code != "FACT_CONFLICT" for f in resolved.findings)

    conflicted = review_listing(
        _request(
            claims=(
                FactClaim(
                    key="quantity",
                    value="10",
                    source=EvidenceSource.PACKAGING_BOM_USER,
                    sku_scope="all",
                ),
                FactClaim(
                    key="quantity",
                    value="12",
                    source=EvidenceSource.PACKAGING_BOM_USER,
                    sku_scope="all",
                ),
            )
        )
    )
    assert any(f.code == "FACT_CONFLICT" and f.severity == "BLOCK" for f in conflicted.findings)


def test_resolved_quantity_blocks_superseded_or_unlisted_count() -> None:
    claims = (
        FactClaim(
            key="quantity",
            value="10",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="quantity",
            value="12",
            source=EvidenceSource.COMPETITOR_LANGUAGE,
            sku_scope="all",
        ),
    )
    superseded = review_listing(_request(title="12 Large River Rocks for Painting", claims=claims))
    assert any(
        finding.code in {"FACT_PRIORITY_CONFLICT", "FACT_QUANTITY_MISMATCH"}
        and finding.severity == "BLOCK"
        for finding in superseded.findings
    )

    unlisted = review_listing(
        _request(title="14 Large River Rocks for Painting", claims=claims[:1])
    )
    assert any(
        finding.code == "FACT_QUANTITY_MISMATCH" and finding.severity == "BLOCK"
        for finding in unlisted.findings
    )


def test_quantity_fact_ignores_accessory_counts_and_dimensions() -> None:
    claims = (
        FactClaim(
            key="quantity",
            value="10",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="quantity",
            value="12",
            source=EvidenceSource.COMPETITOR_LANGUAGE,
            sku_scope="all",
        ),
        FactClaim(
            key="paintbrushes",
            value="2",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
    )
    report = review_listing(
        _request(
            title="10 Large River Rocks with 12-Inch Painting Tray",
            bullets=(
                "PAINTING SURFACE: Ten smooth stones provide room for detailed designs",
                "PACK CONTENTS: Includes 2 paintbrushes for decorating the stones",
                "CREATIVE OPTIONS: Suitable for acrylic paint after surface preparation",
                "DISPLAY IDEAS: Use finished stones for garden markers or desk decorations",
                "NATURAL VARIATION: Shape color and texture vary from stone to stone",
            ),
            claims=claims,
        )
    )
    assert all(
        finding.code not in {"FACT_PRIORITY_CONFLICT", "FACT_QUANTITY_MISMATCH"}
        for finding in report.findings
    )


def test_quantity_fact_blocks_nonleading_pack_count() -> None:
    claims = (
        FactClaim(
            key="quantity",
            value="10",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="quantity",
            value="12",
            source=EvidenceSource.COMPETITOR_LANGUAGE,
            sku_scope="all",
        ),
    )
    for title in (
        "Large River Rocks Painting Kit, 12 Count",
        "CraftCo River Rocks 12 Pack for Painting",
        "CraftCo 12 Piece River Rock Painting Kit",
        "CraftCo River Rocks, Pack of 12 Stones",
        "CraftCo River Rocks 12-Piece Painting Set",
    ):
        report = review_listing(_request(title=title, claims=claims))
        assert any(
            finding.code == "FACT_QUANTITY_MISMATCH" and finding.severity == "BLOCK"
            for finding in report.findings
        )


def test_quantity_fact_allows_verified_accessory_piece_count() -> None:
    claims = (
        FactClaim(
            key="quantity",
            value="10",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="paintbrushes",
            value="2",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
    )
    report = review_listing(
        _request(title="10 River Rocks with 2-Piece Paintbrush Set", claims=claims)
    )
    assert all(finding.code != "FACT_QUANTITY_MISMATCH" for finding in report.findings)


def test_accessory_fact_does_not_exempt_distant_product_count() -> None:
    claims = (
        FactClaim(
            key="quantity",
            value="10",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="paintbrushes",
            value="2",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
    )
    for title in (
        "2-Piece River Rock Set with 2 Paintbrushes",
        "2-Piece River Rock Set with Paintbrush Holder",
    ):
        report = review_listing(_request(title=title, claims=claims))
        assert any(finding.code == "FACT_QUANTITY_MISMATCH" for finding in report.findings)


def test_duplicate_and_missing_bullet_decision_tasks_warn() -> None:
    repeated = "CREATIVE FUN: Express creativity and imagination with colorful stone art"
    report = review_listing(_request(bullets=(repeated, repeated, repeated, repeated, repeated)))
    codes = {finding.code for finding in report.findings if finding.severity == "WARN"}
    assert "BULLET_DUPLICATION" in codes
    assert "BULLET_TASK_COVERAGE" in codes


def test_keyword_coverage_is_field_specific_and_does_not_claim_traffic() -> None:
    report = review_listing(_request())
    fields = {row.field for row in report.keyword_coverage}
    assert fields == {"title", "item_highlights", "bullets", "backend_search_terms"}
    assert report.keyword_basis == "text_relevance_only"


def test_blocking_fact_error_is_not_hidden_by_scores() -> None:
    report = review_listing(_request(title="Adjustable Easel with 8"))
    assert report.status == "BLOCK"
    assert report.can_optimize is False
    assert report.overall_score is None
    assert any(score.dimension == "technical_accuracy" for score in report.scores)


def test_source_repairable_block_and_core_fact_block_have_distinct_dispositions() -> None:
    # Given: one mechanically repairable source issue and one unresolved safety fact
    source_phase = getattr(review_models, "ReviewPhase", None)
    assert source_phase is not None
    repairable = review_listing(_request(title="X" * 76, phase=source_phase.SOURCE))
    unresolved = review_listing(
        _request(
            bullets=(
                "SAFE MATERIAL: Child safe stones for supervised craft projects",
                "SIZE: Ten stones measure approximately 2-3 inches",
                "SURFACE: Smooth natural stones are ready for preparation",
                "DISPLAY: Finished stones can become garden markers",
                "VARIATION: Natural shape and color vary by stone",
            ),
            phase=source_phase.SOURCE,
        )
    )

    # When/Then: automatic repair can continue, while missing safety proof asks the seller
    assert repairable.disposition == "auto_repair"
    assert unresolved.disposition == "ask_user"
    assert unresolved.clarification_questions[0].code == "confirm_safety_evidence"
    assert unresolved.clarification_questions[0].fact_key == "safety"


def test_postflight_block_is_terminal() -> None:
    # Given: optimized output that still contains a hard compatibility claim
    source_phase = getattr(review_models, "ReviewPhase", None)
    assert source_phase is not None

    # When: the same deterministic review runs in postflight mode
    report = review_listing(
        _request(
            bullets=(
                "COMPATIBILITY: Works with all paint markers",
                "SIZE: Ten stones measure approximately 2-3 inches",
                "SURFACE: Smooth natural stones are ready for preparation",
                "DISPLAY: Finished stones can become garden markers",
                "VARIATION: Natural shape and color vary by stone",
            ),
            phase=source_phase.POSTFLIGHT,
        )
    )

    # Then: no blocked postflight output is eligible for display
    assert report.disposition == "terminal"
    assert report.can_optimize is False


def test_third_party_data_cannot_prove_product_safety_or_compatibility() -> None:
    # Given: a priority-6 provider claims safety and universal compatibility
    claims = (
        FactClaim(
            key="safety",
            value="child safe",
            source=EvidenceSource.THIRD_PARTY_PUBLIC_DATA,
            sku_scope="all",
        ),
        FactClaim(
            key="compatibility",
            value="works with all markers",
            source=EvidenceSource.THIRD_PARTY_PUBLIC_DATA,
            sku_scope="all",
        ),
    )

    # When: those claims are reviewed against listing copy
    report = review_listing(
        _request(
            bullets=(
                "SAFE MATERIAL: Child safe stones work with all markers",
                "SIZE: Ten stones measure approximately 2-3 inches",
                "SURFACE: Smooth natural stones are ready for preparation",
                "DISPLAY: Finished stones can become garden markers",
                "VARIATION: Natural shape and color vary by stone",
            ),
            claims=claims,
        )
    )

    # Then: priority 6 remains useful for research, never product fact proof
    block_codes = {finding.code for finding in report.findings if finding.severity == "BLOCK"}
    assert {"UNVERIFIED_SAFETY", "OVERBROAD_COMPATIBILITY"} <= block_codes


def test_score_rationales_name_dimension_specific_issues() -> None:
    # Given: a listing with one technical safety issue
    report = review_listing(
        _request(
            bullets=(
                "SAFE MATERIAL: Child safe stones for crafts",
                "SIZE: Ten stones measure approximately 2-3 inches",
                "SURFACE: Smooth natural stones are ready for preparation",
                "DISPLAY: Finished stones can become garden markers",
                "VARIATION: Natural shape and color vary by stone",
            )
        )
    )

    # When: independent review dimensions are scored
    by_dimension = {score.dimension: score for score in report.scores}

    # Then: the affected dimension cites the issue and unaffected dimensions explain their basis
    assert "UNVERIFIED_SAFETY" in by_dimension["technical_accuracy"].rationale_zh
    assert by_dimension["grammar"].rationale_zh != by_dimension["technical_accuracy"].rationale_zh
    assert report.overall_score is None


def test_global_search_term_cap_blocks_custom_rule_above_250_bytes() -> None:
    # Given: a category rule advertises 500 bytes while Amazon's global cap is 250
    rules = MarketplaceRules(
        marketplace="US",
        product_type="ART_CRAFT_MATERIAL",
        backend_search_terms_max_bytes=500,
    )

    # When: postflight receives a 251-byte backend field
    report = review_listing(_request(rules=rules, backend_search_terms="a" * 251))

    # Then: the machine-readable global-cap finding blocks publication
    assert any(
        finding.code == "SEARCH_TERMS_BYTES" and finding.severity == "BLOCK"
        for finding in report.findings
    )


def test_negative_product_evidence_cannot_support_affirmative_claims() -> None:
    # Given: priority-4 facts explicitly negate performance, safety, and compatibility
    claims = (
        FactClaim(
            key="waterproof",
            value="not waterproof",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="safety",
            value="not child safe",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="compatibility",
            value="does not work with all markers",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
    )

    # When: listing copy makes the opposite affirmative claims
    report = review_listing(
        _request(
            bullets=(
                "PERFORMANCE: Waterproof stones for outdoor projects",
                "SAFETY: Child safe stones for supervised crafts",
                "COMPATIBILITY: Works with all paint markers",
                "DISPLAY: Finished projects become garden decorations",
                "VARIATION: Natural shape and texture vary",
            ),
            claims=claims,
        )
    )

    # Then: all three evidence-dependent checks remain blocked
    block_codes = {finding.code for finding in report.findings if finding.severity == "BLOCK"}
    assert {
        "UNVERIFIED_PERFORMANCE",
        "UNVERIFIED_SAFETY",
        "OVERBROAD_COMPATIBILITY",
    } <= block_codes


def test_qualified_negative_evidence_cannot_support_affirmative_claims() -> None:
    # Given: strong facts negate safety and performance through qualified constructions
    claims = (
        FactClaim(
            key="safety",
            value="not independently tested as child safe",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
        FactClaim(
            key="waterproof",
            value="cannot be considered reliably waterproof",
            source=EvidenceSource.PACKAGING_BOM_USER,
            sku_scope="all",
        ),
    )

    # When: listing copy asserts the opposite affirmative claims
    report = review_listing(
        _request(
            bullets=(
                "PERFORMANCE: Waterproof stones for outdoor projects",
                "SAFETY: Child safe stones for supervised crafts",
                "CREATIVE USE: Designed for painting projects",
                "DISPLAY: Finished projects become garden decorations",
                "VARIATION: Natural shape and texture vary",
            ),
            claims=claims,
        )
    )

    # Then: qualified negation cannot authorize either claim
    block_codes = {finding.code for finding in report.findings if finding.severity == "BLOCK"}
    assert {"UNVERIFIED_PERFORMANCE", "UNVERIFIED_SAFETY"} <= block_codes


def test_trailing_negative_markers_cannot_support_affirmative_terms() -> None:
    # Given: three trailing negations and one affirmative claim with an unrelated exclusion
    cases = (
        ("child safe: no", "child safe"),
        ("waterproof? no", "waterproof"),
        ("weighted base is not supported", "weighted base"),
        ("child safe and no latex", "child safe"),
    )

    # When: structured evidence polarity is resolved for each exact term
    supported = {
        value: supports_affirmative_term(
            (
                review_models.ResolvedFact(
                    key="claim",
                    value=value,
                    source=EvidenceSource.PACKAGING_BOM_USER,
                    sku_scope="all",
                ),
            ),
            term,
        )
        for value, term in cases
    }

    # Then: only the legitimate affirmative construction provides support
    assert supported == {
        "child safe: no": False,
        "waterproof? no": False,
        "weighted base is not supported": False,
        "child safe and no latex": True,
    }


def test_trailing_negative_safety_fact_remains_unverified_end_to_end() -> None:
    # Given: priority-4 safety evidence answers the child-safe question with "no"
    claim = FactClaim(
        key="safety",
        value="child safe: no",
        source=EvidenceSource.PACKAGING_BOM_USER,
        sku_scope="all",
    )

    # When: source review evaluates affirmative child-safe listing copy
    report = review_listing(
        _request(
            bullets=(
                "SAFETY: Child safe stones for supervised crafts",
                "SURFACE: Smooth stones provide room for painting",
                "CREATIVE USE: Designed for craft projects",
                "DISPLAY: Finished projects become garden decorations",
                "VARIATION: Natural shape and texture vary",
            ),
            claims=(claim,),
        )
    )

    # Then: the deterministic safety block remains present
    assert any(
        finding.code == "UNVERIFIED_SAFETY" and finding.severity == "BLOCK"
        for finding in report.findings
    )


def test_not_only_construction_preserves_affirmative_safety_support() -> None:
    # Given: strong evidence uses "not only" as emphasis rather than negation
    claim = FactClaim(
        key="safety",
        value="not only independently tested but certified child safe",
        source=EvidenceSource.PACKAGING_BOM_USER,
        sku_scope="all",
    )

    # When: listing copy makes the supported safety claim
    report = review_listing(
        _request(
            bullets=(
                "SAFETY: Child safe stones for supervised crafts",
                "SURFACE: Smooth stones provide room for painting",
                "CREATIVE USE: Designed for craft projects",
                "DISPLAY: Finished projects become garden decorations",
                "VARIATION: Natural shape and texture vary",
            ),
            claims=(claim,),
        )
    )

    # Then: the unrelated word "not" does not create a false negative
    assert all(finding.code != "UNVERIFIED_SAFETY" for finding in report.findings)


def test_no_certification_does_not_resolve_product_classification() -> None:
    # Given: a water-wearable title and an explicitly negative classification fact
    claim = FactClaim(
        key="product_classification",
        value="no certification",
        source=EvidenceSource.PACKAGING_BOM_USER,
        sku_scope="all",
    )

    # When: the source review checks classification support
    report = review_listing(
        _request(
            title="Toddler Swim Vest for Pool Practice",
            bullets=(
                "FIT: Adjustable straps for supervised pool practice",
                "CONTENTS: One vest is included in the package",
                "USE: Follow the supplied instructions during use",
                "CARE: Rinse and air dry after pool sessions",
                "SCOPE: Sizing varies by child measurements",
            ),
            claims=(claim,),
        )
    )

    # Then: a targeted unresolved-classification block remains
    assert any(
        finding.code == "PRODUCT_CLASSIFICATION_UNRESOLVED"
        and finding.severity == "BLOCK"
        for finding in report.findings
    )


# ── Search-term quality checks ─────────────────────────────────────────────


def test_search_term_duplication_warns_above_threshold() -> None:
    """Visible fields contain 'painting', 'rocks', 'stones', 'river', 'rock'.
    Search terms repeat most of them → duplication should exceed 50%."""
    report = review_listing(
        _request(
            backend_search_terms="painting rocks stones craft river rock art",
        )
    )
    dup_findings = [
        f for f in report.findings if f.code == "SEARCH_TERM_DUPLICATION"
    ]
    assert len(dup_findings) == 1
    assert dup_findings[0].severity == "WARN"


def test_search_term_duplication_passes_when_mostly_incremental() -> None:
    """Search terms with mostly novel tokens should not trigger duplication."""
    report = review_listing(
        _request(
            backend_search_terms="craft supply diy project decoration kit polished",
        )
    )
    assert all(
        f.code != "SEARCH_TERM_DUPLICATION" for f in report.findings
    )


def test_search_term_unverified_performance_claim_blocks() -> None:
    """'heavy duty' in search terms must be blocked when no evidence supports it."""
    report = review_listing(
        _request(
            backend_search_terms="heavy duty stone art supplies",
        )
    )
    claim_findings = [
        f for f in report.findings if f.code == "SEARCH_TERM_CLAIM"
    ]
    assert len(claim_findings) == 1
    assert claim_findings[0].severity == "BLOCK"
    assert "heavy duty" in claim_findings[0].claim_terms


def test_search_term_multiple_performance_claims_are_all_reported() -> None:
    """Multiple unverified claims in search terms are reported together."""
    report = review_listing(
        _request(
            backend_search_terms="waterproof heavy duty guaranteed outdoor stones",
        )
    )
    claim_findings = [
        f for f in report.findings if f.code == "SEARCH_TERM_CLAIM"
    ]
    assert len(claim_findings) == 1
    assert len(claim_findings[0].claim_terms) == 3


def test_search_term_empty_field_produces_no_findings() -> None:
    """An empty backend_search_terms field should be silent."""
    report = review_listing(_request(backend_search_terms=""))
    assert all(
        f.code not in {"SEARCH_TERM_DUPLICATION", "SEARCH_TERM_CLAIM"}
        for f in report.findings
    )


def test_highlights_density_warns_when_budget_is_wasted() -> None:
    """A 20-character IH in a 125-char budget should trigger a density warning."""
    report = review_listing(
        _request(item_highlights="Natural stones.")
    )
    density = [f for f in report.findings if f.code == "HIGHLIGHTS_DENSITY"]
    assert len(density) == 1
    assert density[0].severity == "WARN"


def test_highlights_density_passes_when_well_used() -> None:
    """An IH that uses a reasonable portion of the budget should pass."""
    report = review_listing(
        _request(
            item_highlights=(
                "10 smooth river stones for painting, 2-3 inches each, "
                "natural material with unique variations, suitable for "
                "acrylic paint after surface preparation"
            ),
        )
    )
    assert all(
        f.code != "HIGHLIGHTS_DENSITY" for f in report.findings
    )
