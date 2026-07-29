"""Paste-ready parsing, sanitization, and validation policy."""

from amazon_copy.compliance.paste_ready import (
    sanitize_paste_ready_listing,
    validate_paste_ready_listing,
)
from amazon_copy.optimizer_runtime import SimpleOptimizerError
from amazon_copy.schemas import OptimizedListingCopy
from amazon_copy.utils.json_extract import extract_json_object


def parse_response(raw: str, expected_count: int) -> OptimizedListingCopy:
    """Parse one model response and enforce the requested bullet count."""
    result = OptimizedListingCopy.model_validate(extract_json_object(raw))
    if len(result.bullets) != expected_count:
        message = f"Expected {expected_count} bullets, received {len(result.bullets)}"
        raise SimpleOptimizerError(message)
    return result


def enforce_paste_ready_policy(
    listing: OptimizedListingCopy,
    *,
    allow_weighted_base: bool,
) -> OptimizedListingCopy:
    """Strip banned claims, fix ambiguity, and clamp front-end fields."""
    title, item_highlights, bullets = sanitize_paste_ready_listing(
        listing.title,
        listing.item_highlights,
        listing.bullets,
        allow_weighted_base=allow_weighted_base,
    )
    safe_title = title.strip() or "Amazon Product Listing"
    safe_highlights = item_highlights.strip() or "Key product benefits for everyday use."
    fixed_bullets = [bullet.strip() or "Product detail." for bullet in bullets]
    safe_title, safe_highlights, fixed_bullets = sanitize_paste_ready_listing(
        safe_title,
        safe_highlights,
        fixed_bullets,
        allow_weighted_base=allow_weighted_base,
    )
    fixed_bullets = [bullet.strip() or "Product detail." for bullet in fixed_bullets]
    if (
        safe_title == listing.title
        and safe_highlights == listing.item_highlights
        and fixed_bullets == list(listing.bullets)
    ):
        return listing
    return OptimizedListingCopy(
        title=safe_title,
        item_highlights=safe_highlights,
        bullets=fixed_bullets,
        backend_search_terms=listing.backend_search_terms,
    )


def paste_ready_errors(
    listing: OptimizedListingCopy,
    *,
    allow_weighted_base: bool,
) -> list[str]:
    """Return deterministic paste-ready violations."""
    return list(
        validate_paste_ready_listing(
            listing.title,
            listing.item_highlights,
            listing.bullets,
            allow_weighted_base=allow_weighted_base,
        ).errors
    )


__all__ = ["enforce_paste_ready_policy", "parse_response", "paste_ready_errors"]
