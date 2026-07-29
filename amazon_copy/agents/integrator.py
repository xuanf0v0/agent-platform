"""Task 18 integrator — post-validation and first-eligible selection.

Picks the highest-ranked candidate that passes both hard-gate checks and
optional claim-ID gating.  Simple-first-wins semantics: no LLM polish pass
for reliability.
"""

from __future__ import annotations

from amazon_copy.agents.hard_gates import evaluate_candidate
from amazon_copy.schemas.agents import (
    CandidateArtifact,
    GateFinding,
    GateResult,
    IntegrationTrace,
    RankingResult,
)


def post_validate(
    candidate: CandidateArtifact,
    allowed_claim_ids: set[str] | None = None,
) -> GateResult:
    """Run hard-gate evaluation **plus** claim-ID whitelist check.

    Parameters
    ----------
    candidate:
        The candidate artifact to validate.
    allowed_claim_ids:
        If provided, every ``candidate.claim_id`` must be present in this
        set; unknown IDs produce an error-severity finding that makes the
        candidate ineligible.

    Returns:
    --------
    GateResult
        ``eligible`` is ``True`` only when **every** error-severity finding
        has ``passed=True`` (fail-closed semantics).
    """
    result = evaluate_candidate(candidate)

    if allowed_claim_ids is not None:
        unknown = [c for c in candidate.claim_ids if c not in allowed_claim_ids]
        if unknown:
            new_findings = [
                *result.findings,
                GateFinding(
                    code="CLAIM_ID_UNKNOWN",
                    severity="error",
                    message=f"claim_ids {unknown} not in allowed set",
                    passed=False,
                ),
            ]
            return GateResult(
                candidate_id=result.candidate_id,
                findings=new_findings,
                eligible=False,
            )

    return result


async def integrate(
    ranked: RankingResult,
    candidates: list[CandidateArtifact],
    _settings: object | None = None,
    allowed_claim_ids: set[str] | None = None,
) -> tuple[CandidateArtifact | None, IntegrationTrace]:
    """Select the first eligible candidate in ranked order.

    Iterates ``ranked.ordered_candidate_ids`` and returns the first
    candidate whose ``post_validate`` gate passes.  If no candidate is
    eligible the function returns ``(None, IntegrationTrace(fallback=True))``.

    Parameters
    ----------
    ranked:
        Ranking result from the judging phase.
    candidates:
        Full pool of candidate artifacts (indexed by ``candidate_id``).
    settings:
        Reserved for future pipeline settings (currently unused).
    allowed_claim_ids:
        Optional claim-ID whitelist forwarded to ``post_validate``.

    Returns:
    --------
    tuple[CandidateArtifact | None, IntegrationTrace]
        ``(winner, trace)`` where *winner* is ``None`` when no candidate
        passes validation.
    """
    by_id: dict[str, CandidateArtifact] = {c.candidate_id: c for c in candidates}

    for cid in ranked.ordered_candidate_ids:
        cand = by_id.get(cid)
        if cand is None:
            continue
        gate = post_validate(cand, allowed_claim_ids=allowed_claim_ids)
        if gate.eligible:
            return cand, IntegrationTrace(
                winner_id=cid,
                used_claim_ids=list(cand.claim_ids),
                fallback_used=False,
            )

    return None, IntegrationTrace(
        winner_id="",
        used_claim_ids=[],
        fallback_used=False,
    )
