from __future__ import annotations
import ast
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock
import amazon_copy.simple_optimizer as optimizer
import pytest
from amazon_copy.automatic_models import CompletedOptimization, NeedsClarification
from amazon_copy.config import Settings
from amazon_copy.mcp.live_research import McpToolSnapshot, normalize_tool_payload
from amazon_copy.review.models import EvidenceSource, FactClaim
if TYPE_CHECKING:
    from typing import Literal
    from amazon_copy.llm.base import LLMClient
ROCKS_SOURCE = 'Title: Natural River Rocks for Painting\n- Smooth natural stones provide prepared painting surfaces\n- Natural shape color and texture vary from stone to stone\n- Finished projects can become garden markers or desk decorations'
VEST_SOURCE = 'Title: Toddler Swim Vest for Pool Practice\n- CHILD SAFE: Child safe flotation support for supervised pool practice\n- CLASSIFICATION: Swim vest with secure adjustable straps\n- FIT: Designed for toddlers during supervised water activities'
WEDDING_SOURCE = 'Title: Gold Wedding Welcome Sign Stand 68x31x20 Inches\n- STABILITY: Ensures stability on various surfaces\n- CONTENTS: Includes 8 leather and water bags\n- DISPLAY: Holds a welcome sign for ceremony entrances'
# Title must not match specialized heuristics (e.g. "desk organizer" → DESK_ORGANIZER).
UNKNOWN_PRODUCT_SOURCE = 'Title: Modular Widget Gadget\n- Keeps small office items together\n- Fits on a desk or shelf\n- Components can be rearranged for daily use'

class _ScenarioLLM:

    def __init__(self, events: list[str], *, unsafe_postflight: bool=False, clarification_response: str | None=None) -> None:
        self._events = events
        self._unsafe_postflight = unsafe_postflight
        self._clarification_response = clarification_response
        self._call_count = 0
        self.payloads: list[dict[str, object]] = []

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        self._events.append('llm')
        self._call_count += 1
        payload = json.loads(user)
        if 'seller_reply' in payload:
            return self._clarification_response or '{"answers":[]}'
        self.payloads.append(payload)
        source = payload['source_listing']
        count = int(payload['target_bullet_count'])
        title = str(source['title'])
        if self._unsafe_postflight:
            bullets = ['SAFE: Child safe and guaranteed performance'] * count
        else:
            bullets = [f'DETAIL {index}: Product information from the source' for index in range(1, count + 1)]
        return json.dumps({'title': title, 'item_highlights': 'Source-based product details for marketplace shoppers.', 'bullets': bullets, 'backend_search_terms': 'invented competitor unsafe terms'})

class _ResearchFetcher:

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls = 0

    def __call__(self, settings: Settings, *, query: str) -> list[McpToolSnapshot]:
        del settings
        self.events.append('research')
        self.calls += 1
        normalized = normalize_tool_payload(provider='sellersprite', tool='keyword_miner', output_schema_json='{"type":"object","properties":{"keyword":{"type":"string"},"search_volume":{"type":"number"},"material":{"type":"string"}}}', payload_json=json.dumps({'keyword': query, 'search_volume': 900, 'material': 'unsupported PVC'}))
        return [McpToolSnapshot(provider='sellersprite', status='ok', tool_count=1, research_items=normalized.items, research_gaps=normalized.gaps)]

class _TimeoutLLM:

    @property
    def call_count(self) -> int:
        return 0

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, user, kwargs
        raise TimeoutError

class _CompatibilityLLM:

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        self._call_count += 1
        payload = json.loads(user)
        count = int(payload['target_bullet_count'])
        return json.dumps({'title': 'Natural River Rocks for Painting', 'item_highlights': 'Natural stones for creative painting projects.', 'bullets': ['Use Cases: Compatible with acrylic signs, foam boards, and wooden signs for a practical event display', *('Source-based product detail' for _ in range(count - 1))], 'backend_search_terms': ''})

class _ClassificationLLM:

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del system, kwargs
        payload = json.loads(user)
        count = int(payload['target_bullet_count'])
        return json.dumps({'title': 'Swim Vest for Pool Practice', 'item_highlights': 'Source-based product details', 'bullets': ['Source-based product detail'] * count, 'backend_search_terms': ''})

def _dependencies(fetcher: _ResearchFetcher, llm: LLMClient) -> object:
    dependency_type = getattr(optimizer, 'AutomaticOptimizationDependencies', None)
    assert dependency_type is not None
    return dependency_type(settings=Settings(mock=True), llm=llm, research_fetcher=fetcher)

def test_automatic_pipeline_researches_before_review_and_completes_clean_output() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    run = getattr(optimizer, 'run_automatic_optimization', None)
    assert callable(run)
    result = run(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(fetcher, llm))
    assert result.status == 'completed'
    assert events == ['research', 'llm']
    assert result.source_review.keyword_basis == 'third_party_data'
    assert not [finding for finding in result.postflight_review.findings if finding.severity == 'BLOCK']
    assert len(result.listing.backend_search_terms.encode('utf-8')) <= 250
    assert 'invented' not in result.listing.backend_search_terms
    assert result.rule_context.marketplace == 'US'
    assert result.rule_context.product_type == 'ART_CRAFT_MATERIAL'
    assert result.rule_context.gaps[0].code == 'authoritative_rules_missing'

def test_malformed_research_snapshot_degrades_to_safe_empty_evidence() -> None:
    events: list[str] = []
    llm = _ScenarioLLM(events)
    malformed_fetcher = Mock(return_value=[{'provider': 'sellersprite'}])
    dependencies = optimizer.AutomaticOptimizationDependencies(settings=Settings(mock=True), llm=llm, research_fetcher=malformed_fetcher)
    run = getattr(optimizer, 'run_automatic_optimization', None)
    assert callable(run)
    result = run(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=dependencies)
    assert result.status == 'completed'
    assert result.source_review.keyword_basis == 'text_relevance_only'
    assert result.research_cache.snapshots[0].status == 'error'
    assert result.research_cache.bundle.gaps[0].code == 'payload_malformed'

def test_automatic_pipeline_reports_provider_timeout_separately() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    result = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(fetcher, _TimeoutLLM()))
    assert result.status == 'failed'
    assert result.code == 'optimization_failed'
    assert '60秒' in result.message
    assert '格式无效' not in result.message

def test_automatic_pipeline_removes_generated_compatibility_instead_of_blocking() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    result = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(fetcher, _CompatibilityLLM()))
    assert isinstance(result, CompletedOptimization)
    assert 'compatible with acrylic' not in ' '.join(result.listing.bullets).casefold()

def test_toddler_vest_clarification_resume_reuses_successful_research() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    run = getattr(optimizer, 'run_automatic_optimization', None)
    context_type = getattr(optimizer, 'AutomaticOptimizationContext', None)
    answer_type = getattr(optimizer, 'ClarificationAnswer', None)
    assert callable(run)
    assert context_type is not None
    assert answer_type is not None
    dependencies = _dependencies(fetcher, llm)
    paused = run(VEST_SOURCE, context=context_type(marketplace='US'), dependencies=dependencies)
    answers = tuple((answer_type(question_code=question.code, action='confirm', value='confirmed from packaging label') for question in paused.questions))
    # After facts are confirmed, skip_approval keeps the legacy one-shot complete path
    # (default mode is diagnose → awaiting_approval without generating copy).
    resumed = run(
        VEST_SOURCE,
        context=context_type(
            marketplace='US',
            clarification_answers=answers,
            cached_research=paused.research_cache,
            cached_specialized_rules=paused.specialized_rule_cache,
            skip_approval=True,
        ),
        dependencies=dependencies,
    )
    resumed_again = run(
        VEST_SOURCE,
        context=context_type(
            marketplace='US',
            clarification_answers=answers,
            cached_research=resumed.research_cache,
            cached_specialized_rules=resumed.specialized_rule_cache,
            skip_approval=True,
        ),
        dependencies=dependencies,
    )
    assert paused.status == 'needs_clarification'
    assert {question.code for question in paused.questions} >= {'confirm_product_classification', 'confirm_safety_evidence'}
    assert llm.call_count == 2
    assert resumed.status == 'completed'
    assert resumed.cache_reused is True
    assert resumed_again.status == 'completed'
    assert resumed_again.cache_reused is True
    assert fetcher.calls == 1

def test_stale_source_cache_is_refused_and_refetched() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    run = getattr(optimizer, 'run_automatic_optimization', None)
    context_type = getattr(optimizer, 'AutomaticOptimizationContext', None)
    assert callable(run)
    assert context_type is not None
    first = run(ROCKS_SOURCE, context=context_type(marketplace='US'), dependencies=_dependencies(fetcher, llm))
    changed = ROCKS_SOURCE.replace('Natural River Rocks', '12 Natural River Rocks')
    second = run(changed, context=context_type(marketplace='US', cached_research=first.research_cache, cached_specialized_rules=first.specialized_rule_cache), dependencies=_dependencies(fetcher, llm))
    assert second.cache_reused is False
    assert fetcher.calls == 2

def test_postflight_safety_and_performance_blocks_are_repaired_and_released() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events, unsafe_postflight=True)
    run = getattr(optimizer, 'run_automatic_optimization', None)
    assert callable(run)
    result = run(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(fetcher, llm))
    assert isinstance(result, CompletedOptimization)
    visible = ' '.join((result.listing.title, *result.listing.bullets)).casefold()
    assert 'child safe' not in visible
    assert 'guaranteed' not in visible
    assert result.postflight_review.release_disposition == 'release'

def test_generated_cross_product_classification_is_removed_without_question() -> None:
    events: list[str] = []
    dependencies = _dependencies(_ResearchFetcher(events), _ClassificationLLM())
    result = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=dependencies)
    assert isinstance(result, CompletedOptimization)
    visible = ' '.join((result.listing.title, *result.listing.bullets)).casefold()
    assert 'swim vest' not in visible
    assert result.postflight_review.release_disposition == 'release'

def test_conservative_mode_auto_removes_every_unverified_question() -> None:
    events: list[str] = []
    dependencies = _dependencies(_ResearchFetcher(events), _ScenarioLLM(events))
    result = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', auto_resolve_unverified=True, skip_approval=True), dependencies=dependencies)
    assert isinstance(result, CompletedOptimization)
    assert result.postflight_review.release_disposition == 'release'


def test_conservative_resume_keeps_prior_answers_and_suppresses_removed_terms() -> None:
    from amazon_copy.automatic_conservative import conservative_resume_context

    events: list[str] = []
    dependencies = _dependencies(_ResearchFetcher(events), _ScenarioLLM(events))
    paused = optimizer.run_automatic_optimization(
        WEDDING_SOURCE,
        context=optimizer.AutomaticOptimizationContext(
            marketplace='US',
            skip_approval=True,
        ),
        dependencies=dependencies,
    )
    assert isinstance(paused, NeedsClarification)
    previous_answer = optimizer.ClarificationAnswer(
        question_code='previous_question',
        action='remove',
    )
    previous = optimizer.AutomaticOptimizationContext(
        marketplace='US',
        clarification_answers=(previous_answer,),
        suppressed_claim_terms=('previous unsupported claim',),
    )

    resumed = conservative_resume_context(paused, previous)

    answer_codes = {answer.question_code for answer in resumed.clarification_answers}
    assert 'previous_question' in answer_codes
    assert {question.code for question in paused.questions} <= answer_codes
    expected_removed = {
        term
        for question in paused.questions
        if question.fact_key not in {'marketplace', 'product_type'}
        for term in question.claim_terms
    }
    assert {'previous unsupported claim', *expected_removed} <= set(
        resumed.suppressed_claim_terms
    )


def test_conservative_mode_converges_for_multi_issue_sign_display_stand() -> None:
    source = """Wedding Welcome Sign Stand 68 x 31 x 20 Inch Adjustable Wedding Sign Holder with 8 Leather and Water Bags Heavy Duty Easel for Poster, Baby Bridal Shower, Bridal Shower, Seating Chart, Gold
[Product Features Gold Metal Frame]: This display stand is constructed with a metal base and features a shimmering gold-coated finish, providing an elegant visual presentation for various occasions. Its light-reflecting surface and sturdy structure ensure long-term use both indoors and outdoors.
[Adjustable Height Design]: Users can freely switch between two height options—5.7ft meters and 4ft meters—based on spatial requirements. The simple assembly design supports repeated use and is suitable for year-round display needs for different events.
[Wind-Resistant Stabilization System]: Equipped with a weighted base measuring 31 x 20 inches and two fillable water bags, this display stand offers reliable stability in both indoor and outdoor environments.
[Includes Leather Straps in Four Colors]: The sign stand comes with dual-tone leather straps in four color options and anti-rust screws, capable of securely holding signs up to 1 cm thick. It maintains display stability even in breezy conditions.
[Suitable for Various Display Scenarios]: Ideal for weddings, graduation ceremonies, commercial promotions, and seasonal decorations. It is compatible with acrylic plates, foam boards, and wooden signs, providing a practical and aesthetically pleasing display solution."""
    events: list[str] = []
    dependencies = _dependencies(_ResearchFetcher(events), _ScenarioLLM(events))

    result = optimizer.run_automatic_optimization(
        source,
        context=optimizer.AutomaticOptimizationContext(
            marketplace='US',
            auto_resolve_unverified=True,
            skip_approval=True,
        ),
        dependencies=dependencies,
    )

    assert isinstance(result, CompletedOptimization)
    assert result.postflight_review.release_disposition == 'release'

def test_wedding_stand_only_requests_unresolved_accessory_facts() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    run = getattr(optimizer, 'run_automatic_optimization', None)
    assert callable(run)
    result = run(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(fetcher, llm))
    assert result.status == 'needs_clarification'
    question_codes = {question.code for question in result.questions}
    assert 'confirm_accessory_counts' in question_codes
    assert 'confirm_performance_evidence' not in question_codes
    assert llm.call_count == 0

def test_wedding_accessory_confirmation_replaces_ambiguous_source_phrase() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    dependencies = _dependencies(fetcher, llm)
    paused = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    confirmed = '8 leather straps and 2 fillable water bags'
    resumed = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_answers=(optimizer.ClarificationAnswer(question_code='confirm_accessory_counts', action='confirm', value=confirmed),), cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert not isinstance(resumed, NeedsClarification)
    payload = llm.payloads[0]
    assert '8 leather and water bags' not in str(payload['source_listing']).casefold()
    assert confirmed in str(payload['verified_facts']).casefold()

def test_wedding_chat_reply_is_interpreted_before_generation() -> None:
    events: list[str] = []
    confirmed = '8 leather straps and 2 fillable water bags'
    response = json.dumps({'answers': [{'question_code': 'confirm_accessory_counts', 'action': 'confirm', 'value': confirmed}]})
    llm = _ScenarioLLM(events, clarification_response=response)
    dependencies = _dependencies(_ResearchFetcher(events), llm)
    paused = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    resumed = optimizer.run_automatic_optimization(WEDDING_SOURCE, context=optimizer.AutomaticOptimizationContext(rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_reply='确认包含8条皮革带和2个可注水水袋', clarification_questions=paused.questions, cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert isinstance(resumed, CompletedOptimization)
    assert confirmed in str(llm.payloads[0]['verified_facts']).casefold()

def test_unknown_product_type_requests_confirmation_and_answer_resumes() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    dependencies = _dependencies(fetcher, llm)
    paused = optimizer.run_automatic_optimization(UNKNOWN_PRODUCT_SOURCE, dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    assert [question.code for question in paused.questions] == ['confirm_marketplace', 'confirm_product_type']
    assert paused.rule_context.marketplace == 'UNRESOLVED'
    assert llm.call_count == 0
    resumed = optimizer.run_automatic_optimization(UNKNOWN_PRODUCT_SOURCE, context=optimizer.AutomaticOptimizationContext(rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_answers=(optimizer.ClarificationAnswer(question_code='confirm_marketplace', action='confirm', value='US'), optimizer.ClarificationAnswer(question_code='confirm_product_type', action='confirm', value='OFFICE_ORGANIZER')), cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert isinstance(resumed, CompletedOptimization)
    assert resumed.rule_context.product_type == 'OFFICE_ORGANIZER'
    assert resumed.rule_context.authoritative is False
    assert fetcher.calls == 1

def test_pasted_verified_facts_do_not_bypass_typed_fact_authority() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)

    class _CaptureLLM(_ScenarioLLM):

        def __init__(self) -> None:
            super().__init__(events)
            self.payloads: list[dict[str, object]] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            self.payloads.append(json.loads(user))
            return super().complete(system, user, **kwargs)
    llm = _CaptureLLM()
    source = ROCKS_SOURCE + '\nVerified facts: material=plastic; weighted base; waterproof'
    context = optimizer.AutomaticOptimizationContext(marketplace='US', user_claims=(FactClaim(key='material', value='natural river stone', source=EvidenceSource.AMAZON_PRODUCT_TYPE_RULE, sku_scope='all'),), skip_approval=True)
    result = optimizer.run_automatic_optimization(source, context=context, dependencies=_dependencies(fetcher, llm))
    assert isinstance(result, CompletedOptimization)
    material_facts = [(fact.key, fact.value, int(fact.source)) for fact in result.source_review.resolved_facts if fact.key == 'material']
    assert material_facts == [('material', 'natural river stone', 1)]
    payload_text = json.dumps(llm.payloads[0], ensure_ascii=False).casefold()
    assert 'material=plastic' not in payload_text
    assert 'weighted base' not in payload_text
    assert 'waterproof' not in payload_text

def test_equal_priority_conflict_confirmation_selects_one_user_fact() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    source = ROCKS_SOURCE.replace('Smooth natural stones provide prepared painting surfaces', 'Red and blue finishes provide prepared painting surfaces')
    claims = (FactClaim(key='color', value='red', source=EvidenceSource.PACKAGING_BOM_USER, sku_scope='all'), FactClaim(key='color', value='blue', source=EvidenceSource.PACKAGING_BOM_USER, sku_scope='all'))
    dependencies = _dependencies(fetcher, llm)
    paused = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', user_claims=claims, skip_approval=True), dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    resumed = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_answers=(optimizer.ClarificationAnswer(question_code='resolve_fact_conflict', action='confirm', value='red'),), cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert isinstance(resumed, CompletedOptimization)
    colors = [fact for fact in resumed.source_review.resolved_facts if fact.key == 'color']
    assert [(fact.value, int(fact.source)) for fact in colors] == [('red', 4)]

def test_equal_priority_conflict_removal_drops_claims_and_source_terms() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)

    class _CaptureLLM(_ScenarioLLM):

        def __init__(self) -> None:
            super().__init__(events)
            self.payloads: list[dict[str, object]] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            self.payloads.append(json.loads(user))
            return super().complete(system, user, **kwargs)
    llm = _CaptureLLM()
    source = ROCKS_SOURCE.replace('Smooth natural stones provide prepared painting surfaces', 'Red and blue finishes provide prepared painting surfaces')
    claims = tuple((FactClaim(key='color', value=value, source=EvidenceSource.PACKAGING_BOM_USER, sku_scope='all') for value in ('red', 'blue')))
    dependencies = _dependencies(fetcher, llm)
    paused = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', user_claims=claims, skip_approval=True), dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    resumed = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_answers=(optimizer.ClarificationAnswer(question_code='resolve_fact_conflict', action='remove'),), cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert isinstance(resumed, CompletedOptimization)
    assert all((fact.key != 'color' for fact in resumed.source_review.resolved_facts))
    source_payload = json.dumps(llm.payloads[0]['source_listing'], ensure_ascii=False).casefold()
    assert re.search('\\bred\\b', source_payload) is None
    assert re.search('\\bblue\\b', source_payload) is None

def test_painting_rock_uses_five_bullet_upload_shape() -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)

    class _EchoLLM:

        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        def complete(self, system: str, user: str, **kwargs: object) -> str:
            del system, kwargs
            payload = json.loads(user)
            self.payloads.append(payload)
            source = payload['source_listing']
            bullets = [
                *source['bullets'],
                'Painting Uses: Use the prepared surfaces for painting projects',
                'Display Ideas: Turn finished stones into garden markers or desk decorations',
            ]
            return json.dumps({'title': source['title'], 'item_highlights': 'Natural craft stones for painting projects', 'bullets': bullets[:payload['target_bullet_count']], 'backend_search_terms': ''})
    llm = _EchoLLM()
    result = optimizer.run_automatic_optimization(ROCKS_SOURCE, context=optimizer.AutomaticOptimizationContext(marketplace='US', skip_approval=True), dependencies=_dependencies(fetcher, llm))
    assert isinstance(result, CompletedOptimization)
    assert llm.payloads[0]['target_bullet_count'] == 5
    assert len(result.listing.bullets) == 5
    assert result.rendered_text.count('Bullet Point ') == 5
    assert result.rendered_text.startswith('Title\n')
    joined = ' '.join(result.listing.bullets).casefold()
    assert 'natural shape color and texture vary' in joined
    assert 'garden markers or desk decorations' in joined

@pytest.mark.parametrize(('action', 'answer_value'), [('confirm', 'checked against the priority-1 rule'), ('remove', '')])
def test_priority_conflict_resume_suppresses_exact_lower_claim(action: Literal['confirm', 'remove'], answer_value: str) -> None:
    events: list[str] = []
    fetcher = _ResearchFetcher(events)
    llm = _ScenarioLLM(events)
    source = ROCKS_SOURCE.replace('Smooth natural stones provide prepared painting surfaces', 'Blue stones provide prepared painting surfaces')
    claims = (FactClaim(key='color', value='red', source=EvidenceSource.AMAZON_PRODUCT_TYPE_RULE, sku_scope='all'), FactClaim(key='color', value='blue', source=EvidenceSource.PACKAGING_BOM_USER, sku_scope='all'))
    dependencies = _dependencies(fetcher, llm)
    paused = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', user_claims=claims, skip_approval=True), dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    question = next((item for item in paused.questions if item.finding_code == 'FACT_PRIORITY_CONFLICT'))
    assert (question.fact_key, question.claim_terms) == ('color', ('blue',))
    resumed = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_answers=(optimizer.ClarificationAnswer(question_code=question.code, action=action, value=answer_value),), cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert isinstance(resumed, CompletedOptimization)
    colors = [fact for fact in resumed.source_review.resolved_facts if fact.key == 'color']
    assert [(fact.value, int(fact.source)) for fact in colors] == [('red', 1)]
    source_payload = json.dumps(llm.payloads[0]['source_listing'], ensure_ascii=False).casefold()
    assert re.search('\\bblue\\b', source_payload) is None

@pytest.mark.parametrize(('action', 'answer_value'), [('confirm', 'checked against the package count'), ('remove', '')])
def test_quantity_mismatch_resume_suppresses_exact_source_count(action: Literal['confirm', 'remove'], answer_value: str) -> None:
    events: list[str] = []
    llm = _ScenarioLLM(events)
    source = ROCKS_SOURCE.replace('Natural River Rocks', '12 Natural River Rocks')
    claims = (FactClaim(key='quantity', value='10', source=EvidenceSource.PACKAGING_BOM_USER, sku_scope='all'),)
    dependencies = optimizer.AutomaticOptimizationDependencies(settings=Settings(mock=True), llm=llm, research_fetcher=Mock(return_value=[]))
    paused = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', user_claims=claims, skip_approval=True), dependencies=dependencies)
    assert isinstance(paused, NeedsClarification)
    question = next((item for item in paused.questions if item.finding_code == 'FACT_QUANTITY_MISMATCH'))
    assert (question.fact_key, question.claim_terms) == ('quantity', ('12',))
    resumed = optimizer.run_automatic_optimization(source, context=optimizer.AutomaticOptimizationContext(marketplace='US', rule_context=paused.rule_context, user_claims=paused.evidence_bundle.user_claims, allowed_keywords=paused.evidence_bundle.allowed_keywords, clarification_answers=(optimizer.ClarificationAnswer(question_code=question.code, action=action, value=answer_value),), cached_research=paused.research_cache, cached_specialized_rules=paused.specialized_rule_cache, skip_approval=True), dependencies=dependencies)
    assert isinstance(resumed, CompletedOptimization)
    quantities = [fact for fact in resumed.source_review.resolved_facts if fact.key == 'quantity']
    assert [(fact.value, int(fact.source)) for fact in quantities] == [('10', 4)]
    source_payload = json.dumps(llm.payloads[0]['source_listing'], ensure_ascii=False).casefold()
    assert re.search('\\b12\\b', source_payload) is None

def test_owned_type_alias_modules_parse_with_python_311_grammar() -> None:
    root = Path(__file__).parents[1]
    paths = (root / 'amazon_copy' / 'automatic_models.py', root / 'amazon_copy' / 'automatic_pipeline.py', root / 'amazon_copy' / 'review' / 'scoring.py', root / 'amazon_copy' / 'utils' / 'json_extract.py')
    for path in paths:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 11))
