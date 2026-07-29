"""Compatibility layer between schemas for the amazon_copy multi-agent system.

Provides conversions that bridge the ``ProductInput`` / ``SourceListingCopy``
world (simplified, user-facing) with the ``StudioRequest`` / ``OptimizationReport``
world (internal studio pipeline), and back out to ``OptimizedListingCopy``.

``report_to_final_package`` is intentionally *not* implemented here because
``FinalPackage`` requires a ``ProductInput`` reference and a full ``ListingDraft``
with ``BulletPoint`` objects (validation context, bilingual fields), which an
``OptimizationReport`` alone cannot supply.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from amazon_copy.schemas.simple_listing import OptimizedListingCopy, SourceListingCopy
from amazon_copy.schemas.studio_input import StudioRequest, parse_studio_request
from amazon_copy.schemas.studio_output import (
    DegradedOutcome,
    FailureOutcome,
    NoWinnerOutcome,
    SuccessOutcome,
    TerminalOutcome,
)

if TYPE_CHECKING:
    from amazon_copy.schemas.input_research import ProductInput


class CompatError(ValueError):
    """Raised when a compat conversion cannot produce a valid result.

    Attributes:
        reason: Human-readable explanation of why the conversion failed.
    """

    def __init__(self, reason: str) -> None:
        """Store *reason* and pass it to ``ValueError``."""
        self.reason = reason
        super().__init__(reason)


def product_input_to_studio_request(product: ProductInput) -> StudioRequest:
    """Build a ``StudioRequest`` from a ``ProductInput``.

    Constructs a listing text with the product name, instruction (if non-empty),
    and keywords (comma-separated), then delegates to ``parse_studio_request``
    for full header / layout detection.

    Args:
        product: The simplified product brief.

    Returns:
        A parsed ``StudioRequest`` ready for the studio pipeline.

    Raises:
        StudioInputParseError: If the assembled listing text cannot be parsed.
    """
    lines = [product.product]
    stripped = product.instruction.strip()
    if stripped:
        lines.append(stripped)
    if product.keywords:
        lines.append(", ".join(product.keywords))
    return parse_studio_request("\n".join(lines))


def source_listing_to_studio_request(source: SourceListingCopy) -> StudioRequest:
    """Convert a ``SourceListingCopy`` to a ``StudioRequest``.

    The source title and bullets are joined into a plain listing block and
    parsed via ``parse_studio_request``, which captures the original layout
    template (bullet markers, labels, spacing) from the text alone.

    Args:
        source: The source listing with title and bullet points.

    Returns:
        A ``StudioRequest`` preserving the original title, bullets, and format.
    """
    text = "\n".join([source.title, *source.bullets])
    return parse_studio_request(text)


def report_to_optimized_listing(outcome: TerminalOutcome) -> OptimizedListingCopy:
    """Map a terminal studio outcome to the simplified ``OptimizedListingCopy``.

    On a successful or degraded outcome the first title option becomes the
    primary title, the five bullet texts are mapped directly, and the
    ``item_highlights`` is taken from the report description (falling back
    to the first 120 characters of the analysis text).

    On a no-winner or failure outcome a ``CompatError("no_winner")`` is raised.

    Args:
        outcome: Any terminal outcome from the studio pipeline.

    Returns:
        A paste-ready ``OptimizedListingCopy``.

    Raises:
        CompatError: If the outcome is ``NoWinnerOutcome`` or ``FailureOutcome``.
    """
    match outcome:
        case SuccessOutcome(report=report) | DegradedOutcome(report=report):
            title = report.title_options[0].text
            bullets = [bullet.text for bullet in report.bullets]
            item_highlights = report.description or report.analysis[:120]
            return OptimizedListingCopy(
                title=title, bullets=bullets, item_highlights=item_highlights,
            )
        case NoWinnerOutcome():
            msg = "no_winner"
            raise CompatError(msg)
        case FailureOutcome():
            msg = "no_winner"
            raise CompatError(msg)
        # unreachable: TerminalOutcome is fully covered
