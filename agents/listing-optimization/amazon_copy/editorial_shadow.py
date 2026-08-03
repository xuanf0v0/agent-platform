"""Read-only editorial shadow observations for completed optimizations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from statistics import fmean
from threading import RLock
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from amazon_copy.automatic_models import CompletedOptimization

_SCHEMA_VERSION: Final[int] = 1
_LOW_SCORE: Final[float] = 7.0
_WRITE_LOCK = RLock()
_SAFE_CODE = re.compile(r"[^a-z0-9_.-]+")

_SWEEP_DIMENSIONS: Final[dict[str, tuple[str, ...]]] = {
    "clarity": ("grammar", "readability"),
    "voice_tone": ("localization", "readability"),
    "benefit_relevance": ("selling_points", "purchase_motivation"),
    "evidence_support": ("technical_accuracy", "compliance"),
    "specificity": ("technical_accuracy", "selling_points"),
    "emotional_resonance": ("emotional_appeal", "purchase_motivation"),
    "risk_control": ("compliance", "technical_accuracy"),
}


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_code(value: str) -> str:
    normalized = _SAFE_CODE.sub("_", value.casefold()).strip("_.-")
    return normalized[:96] or "unknown"


def _dimension_scores(result: CompletedOptimization) -> dict[str, float]:
    """Keep the more conservative score when diagnosis and postflight overlap."""
    scores = {
        row.dimension: round(float(row.score), 1)
        for row in result.postflight_review.scores
    }
    if result.diagnosis_report is not None:
        for row in result.diagnosis_report.scores:
            score = round(float(row.score), 1)
            scores[row.dimension] = min(scores.get(row.dimension, score), score)
    return scores


def _sweep_scores(dimensions: dict[str, float]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for sweep, sources in _SWEEP_DIMENSIONS.items():
        values = [dimensions[source] for source in sources if source in dimensions]
        scores[sweep] = round(fmean(values), 1) if values else 0.0
    return scores


def _deterministic_problem_codes(result: CompletedOptimization) -> set[str]:
    """Convert text-budget checks to codes without persisting their values."""
    listing = result.listing
    rules = result.rule_context.rules
    codes: set[str] = set()
    if len(listing.title) > rules.title_max:
        codes.add("metric.title.over_limit")
    if len(listing.item_highlights) > rules.item_highlights_max:
        codes.add("metric.item_highlights.over_limit")
    if len(listing.bullets) != rules.supported_bullet_count:
        codes.add("metric.bullets.count_mismatch")
    if len(listing.backend_search_terms.encode("utf-8")) > (
        rules.backend_search_terms_max_bytes
    ):
        codes.add("metric.backend_search_terms.over_limit")
    return codes


def build_shadow_observation(
    *,
    run_id: str,
    source_text: str,
    result: CompletedOptimization,
    created_at: str | None = None,
) -> dict[str, object]:
    """Build a redacted seven-sweep observation without changing the result."""
    dimensions = _dimension_scores(result)
    sweeps = _sweep_scores(dimensions)
    postflight = result.postflight_review
    finding_codes = {
        f"postflight.{_safe_code(finding.code)}" for finding in postflight.findings
    }
    low_sweep_codes = {
        f"shadow.{sweep}.low" for sweep, score in sweeps.items() if score < _LOW_SCORE
    }
    return {
        "schema_version": _SCHEMA_VERSION,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "source_sha256": _fingerprint(source_text),
        "output_sha256": _fingerprint(result.rendered_text),
        "dimension_scores": sweeps,
        "problem_codes": sorted(
            finding_codes | low_sweep_codes | _deterministic_problem_codes(result)
        ),
    }


def record_shadow_observation(
    path: Path,
    *,
    run_id: str,
    source_text: str,
    result: CompletedOptimization,
) -> None:
    """Append one redacted NDJSON observation under a per-process write lock."""
    observation = build_shadow_observation(
        run_id=run_id,
        source_text=source_text,
        result=result,
    )
    serialized = json.dumps(observation, ensure_ascii=False, separators=(",", ":"))
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            _ = stream.write(serialized)
            _ = stream.write("\n")


__all__ = ["build_shadow_observation", "record_shadow_observation"]
