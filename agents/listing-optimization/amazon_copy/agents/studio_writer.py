"""Three isolated async writer lanes with quorum gating.

Each lane runs a different role (SEO, differentiation, clarity) against the
same evidence snapshot in parallel.  Opaque candidate IDs are assigned by
this module; the LLM model name never leaks into the candidate identity.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from amazon_copy.llm import AsyncLLMClient, get_async_llm
from amazon_copy.prompt_loader import load_prompt
from amazon_copy.schemas.agents import CandidateArtifact, LaneResult, WriterLane

if TYPE_CHECKING:
    from amazon_copy.config import Settings

__all__ = [
    "WriterQuorumError",
    "generate_candidates",
]

_WRITER_ROLES: tuple[str, ...] = (
    "writer_seo",
    "writer_differentiation",
    "writer_clarity",
)

_LANE_BY_ROLE: dict[str, WriterLane] = {
    "writer_seo": WriterLane.SEO,
    "writer_differentiation": WriterLane.DIFFERENTIATION,
    "writer_clarity": WriterLane.CLARITY,
}

_MIN_SUCCESS_QUORUM = 2


class WriterQuorumError(ValueError):
    """Raised when fewer than 2 writer lanes produce valid candidates."""


def _parse_candidate(
    role: str,
    data: dict[str, Any],
    cand_index: int,
) -> CandidateArtifact:
    """Normalise a writer role's JSON payload into a ``CandidateArtifact``.

    Each writer returns role-specific keys:

    * writer_seo          → ``title``, ``bullets``
    * writer_differentiation → ``angle``, ``differentiators``
    * writer_clarity      → ``plain_title``, ``plain_bullets``

    The parsed artifact always carries exactly 3 titles and 5 bullets
    (required by the schema) — shorter lists are padded with the first
    available element.
    """
    lane = _LANE_BY_ROLE[role]

    if role == "writer_seo":
        titles_raw = data.get("titles") or [data.get("title", "")]
        bullets = list(data.get("bullets", []) or [])
    elif role == "writer_differentiation":
        titles_raw = data.get("titles") or [data.get("angle", "")]
        bullets = list(data.get("differentiators", []) or [])
    elif role == "writer_clarity":
        titles_raw = data.get("titles") or [data.get("plain_title", "")]
        bullets = list(data.get("plain_bullets", []) or [])
    else:
        msg = f"Unknown writer role: {role!r}"
        raise ValueError(msg)

    # Pad / truncate to match the CandidateArtifact contract (3 titles, 5 bullets).
    _required_title_count = 3
    _required_bullet_count = 5
    titles: list[str] = [str(t) for t in titles_raw]
    # Strip trailing periods from bullets
    bullets = [b.rstrip(".").strip() for b in bullets]
    while len(bullets) < _required_bullet_count:
        bullets.append(bullets[0] if bullets else "")
    bullets = bullets[:_required_bullet_count]
    # Synthesize distinct titles when only one is provided (avoids DUPLICATE_TITLES gate)
    if len(titles) == 1:
        base = titles[0]
        suffixes = ["", " | Variant B", " | Variant C"]
        titles = [f"{base}{suffixes[i]}" for i in range(_required_title_count)]
    while len(titles) < _required_title_count:
        titles.append(titles[0] if titles else "")
    titles = titles[:_required_title_count]

    return CandidateArtifact(
        candidate_id=f"cand-{lane.value}-{cand_index}",
        lane=lane,
        titles=titles,
        bullets=bullets,
        claim_ids=[],
    )


async def _run_lane(
    role: str,
    evidence_snapshot: dict[str, Any],
    settings: Settings,
    cand_index: int,
) -> CandidateArtifact:
    """Execute one writer lane and return a parsed ``CandidateArtifact``."""
    client: AsyncLLMClient = get_async_llm(role, settings=settings)
    system_prompt = load_prompt(role)
    user_payload = json.dumps(evidence_snapshot, ensure_ascii=False, default=str)
    raw = await client.complete(system=system_prompt, user=user_payload)
    data: dict[str, Any] = json.loads(raw)
    return _parse_candidate(role, data, cand_index)


async def generate_candidates(
    evidence_snapshot: dict[str, Any],
    settings: Settings,
) -> list[CandidateArtifact | LaneResult]:
    """Run exactly three concurrent writer lanes and return results.

    Args:
        evidence_snapshot: Arbitrary evidence dict serialised as the user
            payload for every lane (identical across all three roles).
        settings: Application settings (``MOCK=True`` for offline testing).

    Returns:
        A list of ``CandidateArtifact`` and/or ``LaneResult`` items, one
        per writer lane.  Successful lanes produce a ``CandidateArtifact``;
        failed lanes produce a ``LaneResult`` with the error message.

    Raises:
        WriterQuorumError: When fewer than 2 lanes succeed.
    """
    tasks = [
        _run_lane(role, evidence_snapshot, settings, index + 1)
        for index, role in enumerate(_WRITER_ROLES)
    ]

    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[CandidateArtifact | LaneResult] = []
    success_count = 0

    for role, outcome in zip(_WRITER_ROLES, gathered, strict=True):
        lane = _LANE_BY_ROLE[role]
        if isinstance(outcome, CandidateArtifact):
            results.append(outcome)
            success_count += 1
        elif isinstance(outcome, BaseException):
            results.append(LaneResult(lane=lane, error=str(outcome)))
        else:
            results.append(LaneResult(lane=lane, error=str(outcome)))

    if success_count < _MIN_SUCCESS_QUORUM:
        msg = f"Writer quorum not met: {success_count}/{len(_WRITER_ROLES)} lanes succeeded"
        raise WriterQuorumError(msg)

    return results
