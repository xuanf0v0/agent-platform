from __future__ import annotations

import pytest
from amazon_copy.schemas.canonical_deliverables import FullUsDeliverable
from pydantic import ValidationError

from tests.canonical_full_us_support import full_us_deliverable


def test_full_us_contract_round_trips_every_template_section() -> None:
    # Given: a full-US package containing every section required by the template.
    deliverable = full_us_deliverable()

    # When: the package crosses the serialized Pydantic boundary.
    parsed = FullUsDeliverable.model_validate_json(deliverable.model_dump_json())

    # Then: paired short fields and all five detailed/upload bullets remain aligned.
    assert tuple(item.label.value for item in parsed.short_field_variants) == ("A", "B", "C")
    assert len(parsed.fact_table) == 1
    assert len(parsed.keyword_allocation) == 1
    assert len(parsed.detailed_bullets) == 5
    assert parsed.upload_only_bullets == tuple(
        item.content.english for item in parsed.detailed_bullets
    )


def test_full_us_rejects_mismatched_detailed_and_upload_bullets() -> None:
    # Given: a valid package whose fifth upload-only bullet is replaced by stale copy.
    deliverable = full_us_deliverable()
    invalid = deliverable.model_copy(
        update={"upload_only_bullets": (*deliverable.upload_only_bullets[:-1], "Stale copy")}
    )

    # When / Then: revalidation rejects the stale upload block with the typed code.
    with pytest.raises(ValidationError, match="full_us_bullet_alignment"):
        _ = FullUsDeliverable.model_validate_json(invalid.model_dump_json())


def test_full_us_rejects_stale_short_field_character_count() -> None:
    # Given: a serialized title pair whose declared count no longer matches its copy.
    deliverable = full_us_deliverable()
    first, *remaining = deliverable.short_field_variants
    stale = first.model_copy(update={"title_character_count": first.title_character_count + 1})
    invalid = deliverable.model_copy(update={"short_field_variants": (stale, *remaining)})

    # When / Then: row-level validation reports the explicit count mismatch code.
    with pytest.raises(ValidationError, match="short_field_count_mismatch"):
        _ = FullUsDeliverable.model_validate_json(invalid.model_dump_json())


def test_full_us_rejects_stale_backend_search_term_byte_count() -> None:
    # Given: a serialized package whose declared backend byte count is stale.
    deliverable = full_us_deliverable()
    invalid = deliverable.model_copy(
        update={"backend_search_term_bytes": deliverable.backend_search_term_bytes - 1}
    )

    # When / Then: package validation reports the explicit UTF-8 byte mismatch code.
    with pytest.raises(ValidationError, match="backend_search_term_byte_mismatch"):
        _ = FullUsDeliverable.model_validate_json(invalid.model_dump_json())
