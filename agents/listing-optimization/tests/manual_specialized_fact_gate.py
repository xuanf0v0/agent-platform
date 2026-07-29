import json
import sys
from typing import TypeAlias
from amazon_copy import simple_optimizer as optimizer
from amazon_copy.automatic_models import CompletedOptimization, FailedOptimization, NeedsClarification
from tests.specialized_gate_support import ROCKS_SOURCE, WEDDING_CLAIMS_SOURCE, ListingLLM, ResearchFetcher, RuleFetcher, dependencies, resume_context
SWIM_SOURCE = 'Title: Toddler Swim Aid 22-66 lb Ages 2-6 Years USCG Approved\n- Includes a crotch strap and detachable arm bands\n- Adjustable support for supervised pool practice\n- Check the selected child package before use'
ScenarioValue: TypeAlias = str | int | bool | list[str]
ScenarioResult: TypeAlias = dict[str, ScenarioValue]

class ManualScenarioError(RuntimeError):
    pass

def _wedding_scenario() -> ScenarioResult:
    research = ResearchFetcher()
    rules = RuleFetcher('## Product-fact gate\n- Verify every concrete claim.')
    llm = ListingLLM()
    scenario_dependencies = dependencies(research, rules, llm)
    paused = optimizer.run_automatic_optimization(WEDDING_CLAIMS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=scenario_dependencies)
    if not isinstance(paused, NeedsClarification):
        raise ManualScenarioError
    answers = tuple((optimizer.ClarificationAnswer(question_code=question.code, action='confirm', value='confirmed from packaging BOM and approved specification') for question in paused.questions))
    completed = optimizer.run_automatic_optimization(WEDDING_CLAIMS_SOURCE, context=resume_context(paused, answers), dependencies=scenario_dependencies)
    if not isinstance(completed, CompletedOptimization):
        raise ManualScenarioError
    return {'unconfirmed_status': paused.status, 'unconfirmed_fact_keys': sorted((str(question.fact_key) for question in paused.questions if question.fact_key)), 'confirmed_status': completed.status, 'research_calls': research.calls, 'rule_calls': rules.calls, 'research_cache_reused': completed.cache_reused, 'profile_cache_reused': completed.specialized_cache_reused}

def _swim_scenario() -> ScenarioResult:
    research = ResearchFetcher()
    rules = RuleFetcher('## Safety verification\n- Verify selected child evidence.')
    llm = ListingLLM()
    result = optimizer.run_automatic_optimization(SWIM_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', product_type='SWIM_VEST', skip_approval=True), dependencies=dependencies(research, rules, llm))
    if not isinstance(result, NeedsClarification):
        raise ManualScenarioError
    return {'status': result.status, 'fact_keys': sorted((str(question.fact_key) for question in result.questions)), 'listing_exposed': hasattr(result, 'listing')}

def _rocks_scenarios() -> ScenarioResult:
    clean_research = ResearchFetcher()
    clean_rules = RuleFetcher('## Claim guardrails\n- Verify concrete facts.')
    clean_llm = ListingLLM()
    context = optimizer.AutomaticOptimizationContext(marketplace='US', product_type='ART_CRAFT_MATERIAL', skip_approval=True)
    clean = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=context, dependencies=dependencies(clean_research, clean_rules, clean_llm))
    if not isinstance(clean, CompletedOptimization):
        raise ManualScenarioError
    malicious = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=context, dependencies=dependencies(ResearchFetcher(), RuleFetcher('## Claim guardrails\n- Verify concrete facts.'), ListingLLM(added_title_fact='12 Pack')))
    if not isinstance(malicious, FailedOptimization):
        raise ManualScenarioError
    if malicious.postflight_review is None:
        raise ManualScenarioError
    return {'clean_status': clean.status, 'malicious_status': malicious.status, 'malicious_code': malicious.code, 'malicious_listing_exposed': hasattr(malicious, 'listing'), 'malicious_finding_codes': sorted((str(finding.code) for finding in malicious.postflight_review.findings))}

def main() -> None:
    results: dict[str, ScenarioResult] = {'wedding': _wedding_scenario(), 'swim': _swim_scenario(), 'rocks': _rocks_scenarios()}
    _ = sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
if __name__ == '__main__':
    main()
