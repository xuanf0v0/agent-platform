"""Anonymous dual-judge ranking for the studio pipeline.

Task 17 (dual-judge anonymized ranking):
- Two judges see different alias permutations of the same candidate pool.
- Each judge produces a Ballot with dimension-level scores and a ranked
  alias list.
- Aggregation is equal-weight mean across judges; ties are broken by
  lexicographic candidate_id (ascending after higher-mean tie-break).
- No writer-lane / identity info reaches the judge prompt beyond the
  anonymised listing.
"""

from __future__ import annotations

import json
import random
from typing import Any

from amazon_copy.llm.mock import AsyncMockLLM
from amazon_copy.schemas.agents import Ballot, CandidateArtifact, RankingResult, SCORE_DIMS

# ── Fixture dimension key → SCORE_DIMS key ─────────────────────────
_FIXTURE_DIM_MAP: dict[str, str] = {
    "seo": "seo",
    "clarity": "readability",
    "persuasion": "selling_points",
    "compliance": "compliance",
}
"""Maps the mock judge fixture's dimension names to canonical SCORE_DIMS."""


class NoEligibleError(Exception):
    """Raised when no eligible candidates are provided for judging."""


# ── Helpers ─────────────────────────────────────────────────────────


def make_permutations(
    run_id: str,
    candidate_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Return two deterministically-different shuffles of *candidate_ids*.

    Each shuffle is seeded with ``hash(run_id + ":j1")`` and
    ``hash(run_id + ":j2")`` respectively so the same *run_id* always
    yields the same pair of orders (deterministic reproducibility).
    """
    rng1 = random.Random(hash(run_id + ":j1"))
    rng2 = random.Random(hash(run_id + ":j2"))
    ids1 = list(candidate_ids)
    ids2 = list(candidate_ids)
    rng1.shuffle(ids1)
    rng2.shuffle(ids2)
    return ids1, ids2


def alias_map(order: list[str]) -> dict[str, str]:
    """Build a bidirectional alias → real-id mapping.

    Each element at index *i* (0-based) in *order* receives alias ``A{i+1}``.
    The returned dict contains both ``A{i} → real_id`` **and**
    ``real_id → A{i}`` entries, enabling look-up in either direction.

    Example
    -------
    >>> alias_map(["id_x", "id_y", "id_z"])
    {"A1": "id_x", "A2": "id_y", "A3": "id_z",
     "id_x": "A1", "id_y": "A2", "id_z": "A3"}
    """
    result: dict[str, str] = {}
    for i, real_id in enumerate(order, start=1):
        alias = f"A{i}"
        result[alias] = real_id
        result[real_id] = alias
    return result


# ── Mock-ballot builder ─────────────────────────────────────────────


def _build_mock_ballot(judge_alias: str, order: list[str], raw: dict) -> Ballot:
    """Convert a mock ``AsyncMockLLM("judge")`` response into a validated Ballot.

    The fixed fixture's *rankings* are mapped to aliases by position
    (1st ranking entry → A1, 2nd → A2, …).  The fixture's *dimensions*
    are expanded to cover every canonical ``SCORE_DIMS``; missing dims
    default to ``5.0``.
    """
    entries: list[dict[str, Any]] = raw.get("rankings", [])
    fixture_dims: dict[str, float] = raw.get("dimensions", {})

    # Build full SCORE_DIMS dict from fixture dimensions.
    scores: dict[str, float] = dict.fromkeys(SCORE_DIMS, 5.0)  # type: ignore[arg-type]
    for fix_key, dim_key in _FIXTURE_DIM_MAP.items():
        if fix_key in fixture_dims:
            scores[dim_key] = float(fixture_dims[fix_key])

    # ranked_aliases: position-based mapping.
    n = min(len(order), len(entries))
    ranked_aliases = [f"A{i + 1}" for i in range(n)]

    return Ballot(
        judge_alias=judge_alias,
        scores=scores,
        ranked_aliases=ranked_aliases,
    )


# ── Public API ──────────────────────────────────────────────────────


async def run_judges(
    candidates: list[CandidateArtifact],
    run_id: str,
    settings: object = None,
) -> RankingResult:
    """Run two anonymous judges over *candidates* and return an aggregated ranking.

    Parameters
    ----------
    candidates:
        Eligible candidates to rank.  At least one is required (raises
        :class:`NoEligibleError` when empty).
    run_id:
        Opaque workflow identifier used to seed the deterministic
        alias permutations (ensures reproducibility for the same run).
    settings:
        (Ignored in the mock implementation; included for API
        compatibility with the real judge pipeline.)

    Returns
    -------
    RankingResult
        Aggregated ranking with per-candidate mean scores, ordered by
        score descending (lexicographic candidate_id for ties),
        and a tie-break note.

    Raises
    ------
    NoEligibleError
        If *candidates* is empty.
    """
    if not candidates:
        raise NoEligibleError("No eligible candidates provided for judging.")

    candidate_ids = [c.candidate_id for c in candidates]
    perm1, perm2 = make_permutations(run_id, candidate_ids)

    # Accumulate per-candidate scores from each judge.
    judge_scores: dict[str, list[float]] = {cid: [] for cid in candidate_ids}

    for judge_idx, order in enumerate((perm1, perm2), start=1):
        # Build anonymous prompt listing only aliases.
        aliases = [f"A{i + 1}" for i in range(len(order))]
        alias_lines = "\n".join(f"- {a}" for a in aliases)
        system = "You are an impartial judge evaluating Amazon listing candidates."
        user = (
            "Please evaluate and rank the following anonymized candidates"
            f" (all are listings for the same product):\n{alias_lines}"
        )

        # Call the mock judge (ignores prompt — returns fixed fixture).
        llm = AsyncMockLLM("judge")
        raw_json = await llm.complete(system, user)
        data = json.loads(raw_json)

        # Map fixture ranking entries to real candidate IDs by position.
        entries: list[dict[str, Any]] = data.get("rankings", [])
        for i, entry in enumerate(entries):
            if i < len(order):
                real_id = order[i]
                judge_scores[real_id].append(float(entry["score"]))

        # Build the Ballot for validation / recording purposes.
        _build_mock_ballot(f"j{judge_idx}", order, data)

    # ── Aggregate (equal-weight mean across judges) ─────────────
    final_scores: dict[str, float] = {}
    for cid, scores in judge_scores.items():
        final_scores[cid] = (sum(scores) / len(scores)) if scores else 0.0

    # Sort: higher mean first → lexicographic candidate_id for ties.
    ordered = sorted(
        final_scores.keys(),
        key=lambda cid: (-final_scores[cid], cid),
    )

    # Build tie-break note (only if a true tie exists — identical mean).
    tie_notes_parts: list[str] = []
    seen: dict[float, list[str]] = {}
    for cid in ordered:
        seen.setdefault(final_scores[cid], []).append(cid)
    for score, tied in seen.items():
        if len(tied) > 1:
            tie_notes_parts.append(
                f"score={score}: {tied} → ordered {sorted(tied)}"
            )
    tie_break_notes = "; ".join(tie_notes_parts)

    return RankingResult(
        ordered_candidate_ids=ordered,
        scores=final_scores,
        tie_break_notes=tie_break_notes,
    )
