from amazon_copy.automatic_context import infer_product_type, resolve_specialized_rule_route
from amazon_copy.automatic_models import AutomaticOptimizationContext
from amazon_copy.schemas import SourceListingCopy
from amazon_copy.specialized_rules.catalog import ALLOWLISTED_PROFILE_FILENAMES, RULE_PROFILES, Marketplace
from amazon_copy.specialized_rules.routing import MarketplaceClarificationNeeded, ResolvedMarketplace, RuleRoute, resolve_marketplace, route_rule_profiles
EXPECTED_PROFILE_FILENAMES = frozenset({'us-adjustable-wedding-sign-stands.md', 'us-childrens-swim-aid-listing-audit.md', 'us-decorative-wired-ribbon-short-fields.md', 'us-metal-magazine-file-holder-copy.md', 'us-multifunction-desk-organizer-copy.md', 'us-natural-scallop-shell-copy.md', 'us-outdoor-bird-bath-short-fields.md', 'us-small-mesh-zipper-pouches.md', 'us-tiered-letter-tray-organizers.md', 'us-wall-file-organizer-short-fields.md', 'us-wall-file-organizer-public-diagnostic.md', 'wood-wall-panel-keyword-gap-seo.md', 'acoustic-wood-slat-wall-panels-diagnostic-pattern.md', 'us-wood-slat-wall-panel-traffic-benchmark.md', 'us-acoustic-wood-panel-public-comparison.md', 'us-large-acoustic-polyester-panel-public-benchmark.md', 'public-amazon-hardware-cloth-benchmark.md', 'us-short-field-office-organizer-examples.md', 'uk-bakery-packaging-copy.md', 'uk-cellophane-hamper-copy.md', 'uk-a5-hardback-lined-notebook-cold-start.md', 'uk-acrylic-rotating-pen-holder-cold-start.md', 'uk-craft-kit-seasonality-and-mobile-amazon-fallback.md', 'uk-dust-mop-refill-pads-cold-start.md', 'uk-plastic-wallets-document-wallets.md', 'de-acrylic-rotating-pen-holder-cold-start.md', 'de-writing-pad-title-optimization.md', 'de-cellophane-gift-packaging-diagnostic-pattern.md', 'small-self-adhesive-cellophane-bags-de-uk.md', 'parent-child-variation-copy.md', 'structured-fact-authorization-and-cascade-dedupe.md', 'us-short-title-highlight-search-terms.md', 'short-title-highlight-search-term-allocation.md', 'us-short-title-item-highlights-backend-terms.md', 'cosmo-rufus-copy-rules.md', 'copy-and-image-sop-scoring-rubric.md', 'xiyou-multi-asin-keyword-and-review-workflow.md', 'amazon-rolling-plan-workbook-from-screenshot.md', 'amazon-public-pdp-and-autocomplete-fallback.md', 'us-localized-public-amazon-price-and-offer-checks.md', 'us-mature-competitor-price-promo-ad-audit.md'})

def test_catalog_registers_exactly_the_supplied_forty_unique_profiles() -> None:
    filenames = tuple((profile.filename for profile in RULE_PROFILES))
    registered = frozenset(filenames)
    assert registered == EXPECTED_PROFILE_FILENAMES
    assert ALLOWLISTED_PROFILE_FILENAMES == EXPECTED_PROFILE_FILENAMES
    assert len(filenames) == len(registered) == 41

def test_us_wedding_route_selects_only_exact_product_profile_and_general_gates() -> None:
    product_type = 'SIGN_DISPLAY_STAND'
    route = route_rule_profiles(Marketplace.US, product_type)
    product_profiles = tuple((profile.filename for profile in route.profiles if profile.kind == 'product'))
    process_profiles = tuple((profile for profile in route.profiles if profile.kind == 'process'))
    assert product_profiles == ('us-adjustable-wedding-sign-stands.md',)
    assert len(process_profiles) == 12
    assert 'structured-fact-authorization-and-cascade-dedupe.md' in {
        profile.filename for profile in process_profiles
    }
    assert len(route.fingerprint) == 64

def test_unmatched_product_type_never_inherits_a_similar_product_profile() -> None:
    product_type = 'ROTATING_PEN_HOLDERS'
    route = route_rule_profiles(Marketplace.US, product_type)
    assert route.product_type == product_type
    assert route.profiles
    assert all((profile.kind == 'process' for profile in route.profiles))

def test_shared_cellophane_profile_routes_to_uk_and_de_but_not_us() -> None:
    product_type = 'SELF_ADHESIVE_CELLOPHANE_BAG'
    routed = {marketplace: route_rule_profiles(marketplace, product_type) for marketplace in Marketplace}
    shared = 'small-self-adhesive-cellophane-bags-de-uk.md'
    assert shared in {profile.filename for profile in routed[Marketplace.UK].profiles}
    assert shared in {profile.filename for profile in routed[Marketplace.DE].profiles}
    assert shared not in {profile.filename for profile in routed[Marketplace.US].profiles}

def test_clear_german_resolves_de_while_english_requests_marketplace() -> None:
    german = 'Produktbeschreibung: Größe, Farbe und Lieferung für den Stifthalter'
    english = 'Gold adjustable wedding welcome sign stand'
    german_resolution = resolve_marketplace(german)
    english_resolution = resolve_marketplace(english)
    assert german_resolution == ResolvedMarketplace(marketplace=Marketplace.DE, basis='language')
    assert english_resolution == MarketplaceClarificationNeeded(candidates=(Marketplace.US, Marketplace.UK))

def test_explicit_marketplace_wins_and_generic_wedding_does_not_infer_a_stand() -> None:
    source = 'Wedding table decorations and centrepieces'
    marketplace = resolve_marketplace(source, explicit_marketplace='uk')
    product_type = infer_product_type(source)
    assert marketplace == ResolvedMarketplace(marketplace=Marketplace.UK, basis='explicit')
    assert product_type is None

def test_automatic_route_preserves_english_marketplace_ambiguity() -> None:
    source = SourceListingCopy(title='Gold Adjustable Wedding Welcome Sign Stand', bullets=['Adjustable display frame'])
    context = AutomaticOptimizationContext(product_type='SIGN_DISPLAY_STAND', skip_approval=True)
    resolution = resolve_specialized_rule_route(source, context)
    assert resolution == MarketplaceClarificationNeeded(candidates=(Marketplace.US, Marketplace.UK))

def test_automatic_route_selects_de_for_german_with_exact_product_type() -> None:
    source = SourceListingCopy(title='Drehbarer Acryl-Stifthalter für Schreibtisch und Büro', bullets=['Fächer für Stifte und Zubehör'])
    context = AutomaticOptimizationContext(marketplace='', product_type='ROTATING_PEN_HOLDER', skip_approval=True)
    resolution = resolve_specialized_rule_route(source, context)
    assert isinstance(resolution, RuleRoute)
    assert resolution.marketplace == Marketplace.DE
    assert 'de-acrylic-rotating-pen-holder-cold-start.md' in {profile.filename for profile in resolution.profiles}

def test_automatic_route_keeps_unknown_product_type_unresolved() -> None:
    # Title must not match desk/desktop-storage heuristics → DESK_ORGANIZER.
    source = SourceListingCopy(title='Modular Widget Gadget System', bullets=['Stores small daily items'])
    context = AutomaticOptimizationContext(marketplace='US', skip_approval=True)
    resolution = resolve_specialized_rule_route(source, context)
    assert type(resolution).__name__ == 'ProductTypeClarificationNeeded'
    assert getattr(resolution, 'marketplace', None) == Marketplace.US
