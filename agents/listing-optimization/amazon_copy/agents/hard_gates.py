"""Task 16 hard gates — deterministic pre-pipeline eligibility checks.

Pure functions (no I/O, no LLM) that enforce structural and content
constraints on candidate artifacts before they enter the scoring pipeline.
"""

from __future__ import annotations

from typing import Final

from amazon_copy.compliance.check import scan_title_hard_bans
from amazon_copy.schemas import CandidateArtifact, GateFinding, GateResult

_DEFAULT_BANNED_TERMS: Final[tuple[str, ...]] = (
    "free shipping",
    "best seller",
    "100% quality guaranteed",
)


def evaluate_candidate(
    candidate: CandidateArtifact,
    *,
    seller_name: str | None = None,
    banned_terms: list[str] | None = None,
) -> GateResult:
    """Evaluate a single candidate against Task 16 hard gates.

    Parameters
    ----------
    candidate:
        The candidate artifact to evaluate.
    seller_name:
        If provided, the seller/brand name must not appear in any title
        (casefold comparison, substring match).
    banned_terms:
        Additional promo terms to flag in addition to the built-in list
        (``free shipping``, ``best seller``, ``100% quality guaranteed``).
        Applied to titles and bullets.

    Returns:
    -------
    GateResult
        ``eligible`` is ``True`` only when **every** error-severity finding
        has ``passed=True`` (fail-closed semantics).

    Checks (all error severity, fail closed)
    ----------------------------------------
    1. ``titles`` length == 3, ``bullets`` length == 5
    2. No empty title or bullet
    3. No trailing period on bullets (final character)
    4. Banned promo phrases — compliance scanner on titles, static list
       on bullets, custom ``banned_terms`` on both
    5. ``seller_name`` (casefold) not present in any title
    6. No duplicate titles across the three options
    7. ``claim_ids`` may be empty — never fail
    """
    findings: list[GateFinding] = []

    # ── 1. Structure counts ──────────────────────────────────────────
    if len(candidate.titles) != 3:
        findings.append(
            GateFinding(
                code="STRUCTURE_TITLES_LEN",
                severity="error",
                message=f"expected 3 titles, got {len(candidate.titles)}",
                passed=False,
            ),
        )

    if len(candidate.bullets) != 5:
        findings.append(
            GateFinding(
                code="STRUCTURE_BULLETS_LEN",
                severity="error",
                message=f"expected 5 bullets, got {len(candidate.bullets)}",
                passed=False,
            ),
        )

    # ── 2. Empty content ─────────────────────────────────────────────
    for i, title in enumerate(candidate.titles):
        if not title.strip():
            findings.append(
                GateFinding(
                    code="CONTENT_EMPTY_TITLE",
                    severity="error",
                    message=f"title[{i}] is empty",
                    passed=False,
                ),
            )

    for i, bullet in enumerate(candidate.bullets):
        if not bullet.strip():
            findings.append(
                GateFinding(
                    code="CONTENT_EMPTY_BULLET",
                    severity="error",
                    message=f"bullet[{i}] is empty",
                    passed=False,
                ),
            )

    # ── 3. Trailing period on bullets ────────────────────────────────
    for i, bullet in enumerate(candidate.bullets):
        if bullet.endswith("."):
            findings.append(
                GateFinding(
                    code="CONTENT_TRAILING_PERIOD",
                    severity="error",
                    message=f"bullet[{i}] ends with trailing period",
                    passed=False,
                ),
            )

    # ── 4. Banned promo phrases ──────────────────────────────────────
    # Titles: compliance scanner (promo + subjective categories)
    for i, title in enumerate(candidate.titles):
        findings.extend(
            GateFinding(
                code="PROMO_TITLE_PHRASE",
                severity="error",
                message=f"title[{i}]: {hit.category} banned phrase {hit.phrase!r}",
                passed=False,
            )
            for hit in scan_title_hard_bans(title)
            if hit.category in ("promo", "subjective")
        )

    # Bullets: built-in static list + custom banned_terms
    effective_terms: list[str] = list(_DEFAULT_BANNED_TERMS)
    if banned_terms:
        seen: set[str] = set(effective_terms)
        for t in banned_terms:
            if t not in seen:
                effective_terms.append(t)
                seen.add(t)

    for i, bullet in enumerate(candidate.bullets):
        bullet_cf = bullet.casefold()
        findings.extend(
            GateFinding(
                code="PROMO_BANNED_TERM",
                severity="error",
                message=f"bullet[{i}]: contains banned term {term!r}",
                passed=False,
            )
            for term in effective_terms
            if term.casefold() in bullet_cf
        )

    # Titles: custom banned_terms only (built-in terms are covered by
    # the compliance scanner above, so we skip them to avoid noise).
    if banned_terms:
        for i, title in enumerate(candidate.titles):
            title_cf = title.casefold()
            findings.extend(
                GateFinding(
                    code="PROMO_BANNED_TERM",
                    severity="error",
                    message=f"title[{i}]: contains banned term {term!r}",
                    passed=False,
                )
                for term in banned_terms
                if term.casefold() in title_cf
            )

    # ── 5. Seller name in title ──────────────────────────────────────
    if seller_name:
        seller_cf = seller_name.casefold().strip()
        if seller_cf:
            for i, title in enumerate(candidate.titles):
                if seller_cf in title.casefold():
                    findings.append(
                        GateFinding(
                            code="SELLER_NAME_IN_TITLE",
                            severity="error",
                            message=f"title[{i}] contains seller name {seller_name!r}",
                            passed=False,
                        ),
                    )

    # ── 6. Duplicate titles ──────────────────────────────────────────
    title_map: dict[str, int] = {}
    for i, title in enumerate(candidate.titles):
        norm = title.casefold().strip()
        if norm in title_map:
            findings.append(
                GateFinding(
                    code="DUPLICATE_TITLES",
                    severity="error",
                    message=f"title[{i}] duplicates title[{title_map[norm]}] ({title!r})",
                    passed=False,
                ),
            )
        else:
            title_map[norm] = i

    # ── 7. claim_ids may be empty — no check needed ─────────────────

    eligible = all(f.passed for f in findings if f.severity == "error")

    return GateResult(
        candidate_id=candidate.candidate_id,
        findings=findings,
        eligible=eligible,
    )


def filter_eligible(
    candidates: list[CandidateArtifact],
    **kwargs: object,
) -> list[CandidateArtifact]:
    """Return only candidates that pass all hard gates.

    Convenience wrapper that calls ``evaluate_candidate`` on every entry
    and keeps those where ``eligible is True``.

    Additional keyword arguments (``seller_name``, ``banned_terms``) are
    forwarded to ``evaluate_candidate``.
    """
    result: list[CandidateArtifact] = []
    for cand in candidates:
        gate = evaluate_candidate(cand, **kwargs)  # type: ignore[arg-type]
        if gate.eligible:
            result.append(cand)
    return result
