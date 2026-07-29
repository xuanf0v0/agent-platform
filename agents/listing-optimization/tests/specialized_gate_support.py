from __future__ import annotations
import hashlib
import json
from typing import TYPE_CHECKING, Protocol, final
from amazon_copy import simple_optimizer as optimizer
from amazon_copy.config import Settings
from amazon_copy.specialized_rules.models import SpecializedRuleCache, SpecializedRuleLoad, SpecializedRuleSnapshot
from amazon_copy.utils.json_extract import JsonValue, extract_json_object
if TYPE_CHECKING:
    from amazon_copy.automatic_models import CompletedOptimization, NeedsClarification
    from amazon_copy.mcp.live_research_models import McpToolSnapshot
    from amazon_copy.specialized_rules.resource_loader import SpecializedRuleRequest

class CompletionOption(Protocol):
    pass
WEDDING_CLAIMS_SOURCE = 'Title: Wedding Welcome Sign Stand with Screws\n- Holds signs up to 0.39 inch / 1 cm thick\n- Designed for supervised outdoor displays\n- Adjustable metal frame for event signs'
WEDDING_SAFE_SOURCE = 'Title: Wedding Welcome Sign Stand\n- Adjustable frame for event signs\n- Base supports the assembled display\n- Package details should be checked before setup'
# Avoid specialized heuristics (e.g. "desk/desktop storage" → DESK_ORGANIZER).
UNKNOWN_SOURCE = 'Title: Modular Widget Gadget\n- Stores small daily items\n- Fits on a shelf unit\n- Components can be rearranged'
ROCKS_SOURCE = 'Title: Natural River Rocks for Painting\n- Smooth natural stones for painting projects\n- Natural shape and texture vary\n- Finished projects can become decorations'

@final
class ResearchFetcher:

    def __init__(self) -> None:
        self.calls: int = 0

    def __call__(self, settings: Settings, *, query: str) -> list[McpToolSnapshot]:
        del settings, query
        self.calls += 1
        return []

@final
class RuleFetcher:

    def __init__(self, markdown: str) -> None:
        self.markdown: str = markdown
        self.calls: int = 0

    def __call__(self, settings: Settings, *, request: SpecializedRuleRequest, cached: SpecializedRuleCache | None=None) -> SpecializedRuleLoad:
        del settings
        requested = tuple((profile.filename for profile in request.route.profiles))
        if cached is not None and cached.source_fingerprint == request.source_fingerprint and (cached.route_fingerprint == request.route.fingerprint) and (cached.requested_profiles == requested):
            return SpecializedRuleLoad(cache=cached, reused=True)
        self.calls += 1
        snapshots = tuple((self._snapshot(filename) for filename in requested))
        return SpecializedRuleLoad(cache=SpecializedRuleCache(source_fingerprint=request.source_fingerprint, route_fingerprint=request.route.fingerprint, requested_profiles=requested, snapshots=snapshots, all_requested_loaded=True), reused=False)

    def _snapshot(self, filename: str) -> SpecializedRuleSnapshot:
        content = self.markdown.replace('{filename}', filename)
        return SpecializedRuleSnapshot(profile_filename=filename, content_markdown=content, content_sha256=hashlib.sha256(content.encode()).hexdigest())

@final
class ListingLLM:

    def __init__(self, *, added_title_fact: str='', obey_guidance: bool=False) -> None:
        self.added_title_fact: str = added_title_fact
        self.obey_guidance: bool = obey_guidance
        self.obeyed_guidance: bool = False
        self.payloads: list[dict[str, JsonValue]] = []
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: CompletionOption) -> str:
        del system, kwargs
        self._call_count += 1
        payload = extract_json_object(user)
        self.payloads.append(payload)
        source = payload.get('source_listing')
        if not isinstance(source, dict):
            raise TypeError
        source_title = source.get('title')
        source_bullets = source.get('bullets')
        if not isinstance(source_title, str) or not isinstance(source_bullets, list):
            raise TypeError
        bullets = [bullet for bullet in source_bullets if isinstance(bullet, str)]
        if len(bullets) != len(source_bullets):
            raise TypeError
        added_title_fact = self.added_title_fact
        guidance_value = payload.get('specialized_rule_guidance')
        if self.obey_guidance and isinstance(guidance_value, list):
            for row in guidance_value:
                if not isinstance(row, dict):
                    continue
                excerpt = row.get('excerpt_markdown')
                if isinstance(excerpt, str) and '12-PACK' in excerpt.upper() and ('OUTPUT' in excerpt.upper()):
                    added_title_fact = '12-Pack'
                    self.obeyed_guidance = True
                    break
        title = ' '.join((part for part in (added_title_fact, source_title) if part))
        return json.dumps({'title': title, 'item_highlights': 'Source-based product details for marketplace shoppers', 'bullets': bullets, 'backend_search_terms': ''})

def dependencies(research: ResearchFetcher, rules: RuleFetcher, llm: ListingLLM) -> optimizer.AutomaticOptimizationDependencies:
    return optimizer.AutomaticOptimizationDependencies(settings=Settings(), llm=llm, research_fetcher=research, specialized_rule_fetcher=rules)

def resume_context(result: CompletedOptimization | NeedsClarification, answers: tuple[optimizer.ClarificationAnswer, ...]) -> optimizer.AutomaticOptimizationContext:
    return optimizer.AutomaticOptimizationContext(rule_context=result.rule_context, user_claims=result.evidence_bundle.user_claims, allowed_keywords=result.evidence_bundle.allowed_keywords, clarification_answers=answers, cached_research=result.research_cache, cached_specialized_rules=result.specialized_rule_cache, skip_approval=True)
__all__ = ['ROCKS_SOURCE', 'UNKNOWN_SOURCE', 'WEDDING_CLAIMS_SOURCE', 'WEDDING_SAFE_SOURCE', 'ListingLLM', 'ResearchFetcher', 'RuleFetcher', 'dependencies', 'resume_context']
