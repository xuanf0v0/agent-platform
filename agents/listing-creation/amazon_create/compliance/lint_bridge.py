"""Bridge to packaged lint_listing for creation deliverables."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from amazon_create.schemas.deliverable import CreationDeliverable

_LINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "amazon-listing-policy-and-semantic-copy"
    / "scripts"
    / "lint_listing.py"
)


def _load_lint_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "amazon_create_lint_listing",
        _LINT_PATH,
    )
    if spec is None or spec.loader is None:
        message = f"cannot load lint script at {_LINT_PATH}"
        raise RuntimeError(message)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lint_deliverable(
    deliverable: CreationDeliverable,
    *,
    brand: str = "",
    media_category: bool = False,
    competitor_brands: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Run deterministic post-July-27-2026 listing lint."""
    module = _load_lint_module()
    payload = {
        "title": deliverable.title,
        "item_highlights": deliverable.item_highlights,
        "bullets": [b.text for b in deliverable.bullets],
        "search_terms": deliverable.search_terms,
        "brand": brand,
        "media_category": media_category,
        "competitor_brands": list(competitor_brands),
    }
    return module.lint(payload)
