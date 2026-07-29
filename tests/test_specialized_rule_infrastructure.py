import importlib.util

import amazon_copy.specialized_rules.catalog as rule_catalog
import amazon_copy.specialized_rules.client as rule_client
import amazon_copy.specialized_rules.models as rule_models
import amazon_copy.specialized_rules.routing as rule_routing
from amazon_copy import automatic_context, automatic_models
from amazon_copy.automatic_context import source_fingerprint


def test_source_fingerprint_characterizes_existing_source_bound_cache_key() -> None:
    # Given: the unchanged listing source consumed by automatic cache lookup.
    source = "Title: Gold Wedding Welcome Sign Stand"

    # When: the existing cache-key function frames and hashes that source.
    fingerprint = source_fingerprint(source)

    # Then: the established binary observable remains stable.
    assert fingerprint == "c6396665f066108a705c20bd75f18b8077ee5f4be4a066cc3ed7cf92821e281f"


def test_specialized_rule_contract_is_exposed_to_the_automatic_pipeline() -> None:
    # Given: the existing automatic pipeline modules.
    route_resolver = getattr(automatic_context, "resolve_specialized_rule_route", None)
    cache_model = getattr(automatic_models, "SpecializedRuleCache", None)

    # When: specialized-rule infrastructure is requested by the pipeline.
    exposed = callable(route_resolver) and cache_model is not None

    # Then: routing and typed cache contracts are available at stable seams.
    assert exposed


def test_specialized_rule_modules_have_bounded_public_responsibilities() -> None:
    # Given: the specialized-rule package exposed to the automatic workflow.
    module_names = (
        "amazon_copy.specialized_rules.catalog",
        "amazon_copy.specialized_rules.client",
        "amazon_copy.specialized_rules.routing",
    )

    # When: each bounded infrastructure responsibility is resolved.
    specs = tuple(importlib.util.find_spec(name) for name in module_names)

    # Then: catalog, client, and routing modules are independently importable.
    assert all(spec is not None for spec in specs)


def test_specialized_rule_modules_expose_typed_runtime_contracts() -> None:
    # Given: independently importable specialized-rule modules.
    required_symbols = (
        (rule_catalog, "ALLOWLISTED_PROFILE_FILENAMES"),
        (rule_catalog, "RULE_PROFILES"),
        (rule_client, "ReadOnlyRuleResourcesClient"),
        (rule_client, "RuleReadPolicy"),
        (rule_client, "SpecializedRuleRequest"),
        (rule_client, "fetch_specialized_rules"),
        (rule_client, "fetch_specialized_rules_sync"),
        (rule_models, "SpecializedRuleGap"),
        (rule_models, "SpecializedRuleSnapshot"),
        (rule_models, "SpecializedRuleLoad"),
        (rule_routing, "resolve_marketplace"),
        (rule_routing, "route_rule_profiles"),
    )

    # When: the runtime seams are inspected without executing remote work.
    symbols = tuple(getattr(module, name, None) for module, name in required_symbols)

    # Then: every typed catalog, routing, cache, and client seam is present.
    assert all(symbol is not None for symbol in symbols)


def test_automatic_context_can_resume_with_source_bound_specialized_rule_cache() -> None:
    # Given: the automatic optimization context boundary.
    context_type = automatic_models.AutomaticOptimizationContext

    # When: its default marketplace and cache fields are inspected.
    context = context_type()

    # Then: marketplace may require clarification and a typed cache can be carried on resume.
    assert context.marketplace is None
    assert "cached_specialized_rules" in context_type.model_fields
    assert context.cached_specialized_rules is None
    assert (
        "specialized_rule_fetcher"
        in automatic_models.AutomaticOptimizationDependencies.__dataclass_fields__
    )
