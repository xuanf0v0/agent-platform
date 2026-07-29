from __future__ import annotations
import hashlib
import pytest
from amazon_copy import simple_optimizer as optimizer
from amazon_copy.automatic_models import CompletedOptimization, NeedsClarification
from amazon_copy.config import Settings
from amazon_copy.specialized_rules.catalog import Marketplace
from tests.specialized_catalog_support import CombinedCatalogRuleFetcher, combined_rule_profiles
from tests.specialized_gate_support import ROCKS_SOURCE, ListingLLM, ResearchFetcher, resume_context
WEDDING_SOURCE = 'Title: Wedding Welcome Sign Stand with Screws\n- Holds signs up to 0.39 inch / 1 cm thick\n- Designed for supervised outdoor displays\n- Adjustable metal frame for event signs\n'
SWIM_SOURCE = 'Title: Toddler Swim Vest 22-66 lb Ages 2-6 Years USCG Approved\n- Includes a crotch strap and detachable arm bands\n- Adult supervision is required during water activities\n- Check the selected child package before use\n'
UK_BAKERY_SOURCE = 'Title: 18 Pack Kraft Cookie Boxes with Window\n- Ready-to-use bakery gift boxes for brownies and biscuits\n- Clear window for display during transport\n- Suitable for pastries, party favours and bake sales\n'
DE_WRITING_PAD_SOURCE = 'Title: Schreibblock A4 liniert für Schreibtisch und Büro\n- Papierblock für Notizen in Schule und Büro\n- Perforiert mit Abreißkante für einfache Nutzung\n- Neutrales Cover für tägliche Notizen\n'

def _dependencies(rules: CombinedCatalogRuleFetcher, llm: ListingLLM) -> optimizer.AutomaticOptimizationDependencies:
    return optimizer.AutomaticOptimizationDependencies(settings=Settings(), llm=llm, research_fetcher=ResearchFetcher(), specialized_rule_fetcher=rules)

def _assert_guidance_provenance(result: CompletedOptimization, filename: str) -> None:
    guidance = next((item for item in result.specialized_rule_guidance if item.profile_filename == filename))
    expected_hash = hashlib.sha256(combined_rule_profiles()[filename].encode('utf-8')).hexdigest()
    assert guidance.content_sha256 == expected_hash
    assert guidance.authority == 'internal_guidance'
    assert guidance.can_authorize_facts is False

def test_wedding_profile_blocks_deterministic_fact_risks_then_resumes_with_provenance() -> None:
    rules = CombinedCatalogRuleFetcher()
    paused = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(rules, ListingLLM()))
    assert isinstance(paused, NeedsClarification)
    fact_keys = {question.fact_key for question in paused.questions}
    assert {'included_screws', 'sign_thickness', 'outdoor_use_conditions'} <= fact_keys
    answers = tuple((optimizer.ClarificationAnswer(question_code=question.code, action='confirm', value='confirmed for this SKU by seller evidence') for question in paused.questions))
    completed = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=resume_context(paused, answers), dependencies=_dependencies(rules, ListingLLM()))
    assert isinstance(completed, CompletedOptimization)
    assert completed.rule_context.marketplace == Marketplace.US
    assert completed.rule_context.product_type == 'SIGN_DISPLAY_STAND'
    assert completed.postflight_review.release_disposition == 'release'
    _assert_guidance_provenance(completed, 'us-adjustable-wedding-sign-stands.md')

def test_swim_profile_requires_safety_ranges_structure_and_certification() -> None:
    rules = CombinedCatalogRuleFetcher()
    paused = optimizer.run_automatic_optimization(SWIM_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', product_type='SWIM_VEST', skip_approval=True), dependencies=_dependencies(rules, ListingLLM()))
    assert isinstance(paused, NeedsClarification)
    fact_keys = {question.fact_key for question in paused.questions}
    assert {'weight_range', 'age_range', 'included_structure', 'certification'} <= fact_keys
    answers = tuple((optimizer.ClarificationAnswer(question_code=question.code, action='confirm', value='confirmed against selected-child packaging and compliance records') for question in paused.questions))
    completed = optimizer.run_automatic_optimization(SWIM_SOURCE, context=resume_context(paused, answers), dependencies=_dependencies(rules, ListingLLM()))
    assert isinstance(completed, CompletedOptimization)
    assert completed.rule_context.product_type == 'SWIM_VEST'
    assert completed.postflight_review.release_disposition == 'release'
    _assert_guidance_provenance(completed, 'us-childrens-swim-aid-listing-audit.md')

def test_process_only_rocks_route_removes_an_unauthorized_new_pack_fact() -> None:
    rules = CombinedCatalogRuleFetcher()
    result = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', product_type='ART_CRAFT_MATERIAL', skip_approval=True), dependencies=_dependencies(rules, ListingLLM(added_title_fact='12-Pack')))
    assert isinstance(result, CompletedOptimization)
    assert '12-Pack' not in result.listing.title
    assert result.specialized_rule_cache is not None
    assert result.specialized_rule_cache.snapshots
    assert all((snapshot.profile_filename not in {'us-adjustable-wedding-sign-stands.md', 'us-childrens-swim-aid-listing-audit.md'} for snapshot in result.specialized_rule_cache.snapshots))
    assert result.postflight_review.release_disposition == 'release'

@pytest.mark.parametrize(('source', 'product_type', 'marketplace', 'filename'), [(UK_BAKERY_SOURCE, 'BAKERY_PACKAGING', Marketplace.UK, 'uk-bakery-packaging-copy.md'), (DE_WRITING_PAD_SOURCE, 'WRITING_PAD', Marketplace.DE, 'de-writing-pad-title-optimization.md')], ids=['uk-bakery', 'de-writing-pad'])
def test_localized_golden_profiles_keep_marketplace_and_guidance_provenance(source: str, product_type: str, marketplace: Marketplace, filename: str) -> None:
    rules = CombinedCatalogRuleFetcher()
    result = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace=marketplace.value if marketplace is Marketplace.UK else None, product_type=product_type, skip_approval=True), dependencies=_dependencies(rules, ListingLLM()))
    assert isinstance(result, CompletedOptimization)
    assert result.rule_context.marketplace == marketplace
    assert result.rule_context.product_type == product_type
    assert result.specialized_rule_cache is not None
    assert filename in result.specialized_rule_cache.requested_profiles
    _assert_guidance_provenance(result, filename)
