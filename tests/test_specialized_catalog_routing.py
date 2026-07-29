from pathlib import Path
import pytest
from amazon_copy.automatic_context import resolve_specialized_rule_route
from amazon_copy.automatic_models import AutomaticOptimizationContext
from amazon_copy.schemas import SourceListingCopy
from amazon_copy.specialized_rules.catalog import ALLOWLISTED_PROFILE_FILENAMES, Marketplace
from amazon_copy.specialized_rules.routing import MarketplaceClarificationNeeded, ProductTypeClarificationNeeded, ResolvedMarketplace, RuleRoute, resolve_marketplace, route_rule_profiles
import tests.specialized_catalog_support as catalog_support
from tests.specialized_catalog_support import ALL_SOURCE_FILENAMES, COMBINED_RULE_SOURCE, PROCESS_ROUTE_CASES, PRODUCT_ROUTE_CASES, ProcessRouteCase, ProductRouteCase, combined_rule_profiles

def _profile_names(route: RuleRoute, kind: str) -> tuple[str, ...]:
    profiles = route.profiles
    return tuple((profile.filename for profile in profiles if profile.kind == kind))

def test_combined_source_registers_every_allowlisted_profile() -> None:
    profiles = combined_rule_profiles()
    fixture_names = frozenset(profiles)
    assert ALL_SOURCE_FILENAMES == ALLOWLISTED_PROFILE_FILENAMES
    assert len(ALL_SOURCE_FILENAMES) == 41
    assert fixture_names == ALL_SOURCE_FILENAMES
    assert all((markdown.strip() for markdown in profiles.values()))
    assert COMBINED_RULE_SOURCE.is_relative_to(Path(__file__).parent)

def test_missing_combined_source_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = Path(__file__).with_name('__missing_specialized_rules_fixture__.md')
    assert not missing.exists()
    monkeypatch.setattr(catalog_support, 'COMBINED_RULE_SOURCE', missing)
    catalog_support.combined_rule_profiles.cache_clear()
    try:
        with pytest.raises(catalog_support.SpecializedCatalogResourceError) as error:
            _ = catalog_support.combined_rule_profiles()
    finally:
        catalog_support.combined_rule_profiles.cache_clear()
    assert error.value.resource_path == missing

@pytest.mark.parametrize('case', PRODUCT_ROUTE_CASES, ids=tuple((case.filename for case in PRODUCT_ROUTE_CASES)))
def test_product_profile_routes_only_for_exact_marketplace_and_product_type(case: ProductRouteCase) -> None:
    marketplace = case.marketplace
    product_type = case.product_type
    filename = case.filename
    exact = route_rule_profiles(marketplace, product_type)
    typo = route_rule_profiles(marketplace, product_type + '_TYPO')
    cross_marketplace = {other: route_rule_profiles(other, product_type) for other in Marketplace if other is not marketplace}
    expected = {item.filename for item in PRODUCT_ROUTE_CASES if item.marketplace is marketplace and item.product_type == product_type}
    assert filename in _profile_names(exact, 'product')
    assert set(_profile_names(exact, 'product')) == expected
    assert _profile_names(typo, 'product') == ()
    declared_marketplaces = {item.marketplace for item in PRODUCT_ROUTE_CASES if item.filename == filename}
    assert all((filename not in _profile_names(route, 'product') for other, route in cross_marketplace.items() if other not in declared_marketplaces))

@pytest.mark.parametrize('case', PROCESS_ROUTE_CASES, ids=tuple((case.filename for case in PROCESS_ROUTE_CASES)))
def test_process_profile_routes_only_for_declared_marketplaces(case: ProcessRouteCase) -> None:
    filename = case.filename
    marketplaces = case.marketplaces
    routes = {marketplace: route_rule_profiles(marketplace, 'UNRELATED_PRODUCT') for marketplace in Marketplace}
    for marketplace, route in routes.items():
        assert (filename in _profile_names(route, 'process')) is (marketplace in marketplaces)
        assert _profile_names(route, 'product') == ()

def test_english_marketplace_ambiguity_is_preserved_until_confirmation() -> None:
    source = SourceListingCopy(title='A5 Hardback Lined Notebook', bullets=['Lined pages for notes'])
    context = AutomaticOptimizationContext(product_type='A5_HARDBACK_LINED_NOTEBOOK', skip_approval=True)
    resolution = resolve_specialized_rule_route(source, context)
    assert resolution == MarketplaceClarificationNeeded(candidates=(Marketplace.US, Marketplace.UK))

def test_clear_german_text_resolves_de_and_unknown_product_type_stays_explicit() -> None:
    german = 'Schreibblock für Schreibtisch und Büro mit Lieferung'
    marketplace = resolve_marketplace(german)
    product_route = route_rule_profiles(Marketplace.DE, 'UNREGISTERED_PRODUCT')
    unresolved = resolve_specialized_rule_route(SourceListingCopy(title='Modular Storage System', bullets=['Desk storage']), AutomaticOptimizationContext(marketplace='DE', skip_approval=True))
    assert marketplace == ResolvedMarketplace(marketplace=Marketplace.DE, basis='language')
    assert _profile_names(product_route, 'product') == ()
    assert isinstance(unresolved, ProductTypeClarificationNeeded)
    assert unresolved.marketplace == Marketplace.DE
