"""Lint bridge tests."""

from __future__ import annotations

from amazon_create.compliance.lint_bridge import lint_deliverable
from amazon_create.schemas.deliverable import BulletDeliverable, CreationDeliverable


def test_lint_title_too_long() -> None:
    d = CreationDeliverable(
        title="X" * 80,
        item_highlights="Short highlight line for materials and uses",
        bullets=[BulletDeliverable(text=f"Bullet {i} body") for i in range(1, 6)],
        search_terms="garden mesh fence",
    )
    result = lint_deliverable(d)
    assert result["status"] == "BLOCK"
