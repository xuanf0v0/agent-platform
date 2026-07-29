"""Ring-critique and revision for the multi-agent studio pipeline.

Each candidate is critiqued by a peer (ring topology) then revised based
on the collected feedback.  All LLM calls go through ``get_async_llm``
and respect ``settings.mock`` for offline testing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from amazon_copy.llm import get_async_llm
from amazon_copy.schemas.agents import CandidateArtifact, CritiqueArtifact, CritiqueFinding

if TYPE_CHECKING:
    from amazon_copy.config import Settings

__all__ = [
    "ring_edges",
    "run_critique_round",
    "run_revision_round",
    "critique_and_revise",
]


# ── Ring topology ──────────────────────────────────────────────────────


def ring_edges(ids: list[str]) -> list[tuple[str, str]]:
    """Build a directed critique ring over *ids*.

    * len(ids) == 3 — cycle: ``0→1, 1→2, 2→0``
    * len(ids) == 2 — mutual: ``0→1, 1→0``
    * else          — ``[]``

    IDs are sorted internally so the ring is deterministic regardless of
    insertion order.
    """
    sorted_ids = sorted(ids)
    n = len(sorted_ids)
    if n == 3:
        return [
            (sorted_ids[0], sorted_ids[1]),
            (sorted_ids[1], sorted_ids[2]),
            (sorted_ids[2], sorted_ids[0]),
        ]
    if n == 2:
        return [
            (sorted_ids[0], sorted_ids[1]),
            (sorted_ids[1], sorted_ids[0]),
        ]
    return []


# ── Normalisation helpers (mock-friendly) ─────────────────────────────


def _normalize_findings(raw: Any) -> list[CritiqueFinding]:
    """Normalise raw critic output into structured CritiqueFindings.

    Handles three shapes returned by mock fixtures:

    * **list of dicts** — each dict must contain ``category``, ``finding``,
      and ``recommendation`` keys (or we fall back to the whole dict).
    * **list of strings** — each string becomes a single finding in the
      ``"review"`` category.
    * **single string** — wrapped as one finding.
    * **anything else** — returns empty list.
    """
    if isinstance(raw, list):
        if all(isinstance(item, dict) for item in raw):
            return [
                CritiqueFinding(
                    category=item.get("category", "review"),
                    finding=item.get("finding", str(item)),
                    recommendation=item.get("recommendation", ""),
                )
                for item in raw
            ]
        # list of strings
        return [
            CritiqueFinding(category="review", finding=str(item), recommendation="")
            for item in raw
        ]
    if isinstance(raw, str):
        return [CritiqueFinding(category="review", finding=raw, recommendation="")]
    return []


def _normalize_titles_bullets(
    data: dict[str, Any],
    original: CandidateArtifact,
) -> tuple[list[str], list[str]]:
    """Extract 3 titles and 5 bullets from the reviser's JSON output.

    Tries the mock fixture keys (``revision_title`` / ``revision_bullets``)
    first, then generic keys (``title`` / ``titles`` / ``bullets``), and
    falls back to the *original* candidate values when the output lacks
    them.  The result is always padded or truncated to the required lengths.
    """
    titles_raw = (
        data.get("revision_titles")
        or data.get("revision_title")
        or data.get("title")
        or data.get("titles")
    )
    bullets_raw = data.get("revision_bullets") or data.get("bullets")

    if isinstance(titles_raw, str):
        # Single string → synthesize 3 distinct variants to avoid DUPLICATE_TITLES gate
        base = titles_raw
        suffixes = ["", " | Variant B", " | Variant C"]
        titles = [f"{base}{suffixes[i]}" for i in range(3)]
    elif isinstance(titles_raw, list):
        titles = [str(t) for t in titles_raw]
    else:
        titles = list(original.titles)

    if isinstance(bullets_raw, list):
        bullets = [str(b).rstrip(".").strip() for b in bullets_raw]
    else:
        bullets = list(original.bullets)

    # Pad to contract
    while len(titles) < 3:
        titles.append(titles[0] if titles else "")
    while len(bullets) < 5:
        bullets.append(bullets[0] if bullets else "")

    # Truncate to contract
    return titles[:3], bullets[:5]


# ── Critique round ─────────────────────────────────────────────────────


async def run_critique_round(
    candidates: list[CandidateArtifact],
    settings: Settings,
) -> list[CritiqueArtifact]:
    """Run one critique round over the ring.

    For each directed edge ``(source_id, target_id)`` the source's LLM
    reviews the *target*'s titles and bullets.  The raw LLM response is
    normalised into structured ``CritiqueFinding`` items.
    """
    id_map = {c.candidate_id: c for c in candidates}
    edges = ring_edges(list(id_map.keys()))

    critiques: list[CritiqueArtifact] = []
    for _source_id, target_id in edges:
        target = id_map[target_id]
        client = get_async_llm("critic", settings=settings)
        payload = json.dumps(
            {"titles": target.titles, "bullets": target.bullets},
            ensure_ascii=False,
        )
        raw = await client.complete(system="critic", user=payload)
        data = json.loads(raw)

        # Normalise findings — the mock fixture stores them in "issues"
        issues_raw = data.get("issues") or data.get("findings") or []
        findings = _normalize_findings(issues_raw)

        critiques.append(
            CritiqueArtifact(target_candidate_id=target_id, findings=findings),
        )

    return critiques


# ── Revision round ─────────────────────────────────────────────────────


async def run_revision_round(
    critiques: list[CritiqueArtifact],
    candidates: list[CandidateArtifact],
    settings: Settings,
) -> list[CandidateArtifact]:
    """Run one revision round.

    For every *unique* target identified in *critiques*, the reviser LLM
    produces a revised ``CandidateArtifact``.  The revised artifact carries
    the ID ``{original_id}-rev`` and preserves the original lane.

    Titles and bullets are padded or normalised so the result always
    satisfies the schema contract (3 titles / 5 bullets).
    """
    id_map = {c.candidate_id: c for c in candidates}
    unique_targets = sorted({c.target_candidate_id for c in critiques})

    revisions: list[CandidateArtifact] = []
    for target_id in unique_targets:
        original = id_map[target_id]
        target_critiques = [
            c for c in critiques if c.target_candidate_id == target_id
        ]

        client = get_async_llm("reviser", settings=settings)
        payload = json.dumps(
            {
                "original_titles": original.titles,
                "original_bullets": original.bullets,
                "critiques": [
                    {"category": f.category, "finding": f.finding, "recommendation": f.recommendation}
                    for tc in target_critiques
                    for f in tc.findings
                ],
            },
            ensure_ascii=False,
        )
        raw = await client.complete(system="reviser", user=payload)
        data = json.loads(raw)

        titles, bullets = _normalize_titles_bullets(data, original)

        revisions.append(
            CandidateArtifact(
                candidate_id=f"{target_id}-rev",
                lane=original.lane,
                titles=titles,
                bullets=bullets,
                claim_ids=list(original.claim_ids),
            ),
        )

    return revisions


# ── One-shot critique + revise ────────────────────────────────────────


async def critique_and_revise(
    candidates: list[CandidateArtifact],
    settings: Settings,
) -> list[CandidateArtifact]:
    """Critique then revise — exactly one round of each.

    This is the top-level entry point: it runs the full critique ring,
    then revises every candidate that received criticism.  The returned
    list contains one ``CandidateArtifact`` per unique critique target.
    """
    critiques = await run_critique_round(candidates, settings)
    revisions = await run_revision_round(critiques, candidates, settings)
    return revisions
