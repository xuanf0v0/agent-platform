from __future__ import annotations

import ast
import inspect

import pytest
from amazon_copy.schemas import OptimizedListingCopy, studio_output
from amazon_copy.schemas.simple_listing import format_optimized_listing, parse_listing_block
from amazon_copy.schemas.studio_output import (
    AuditMetadata,
    BulletOption,
    Citation,
    DegradedOutcome,
    FailureOutcome,
    NoWinnerOutcome,
    OptimizationReport,
    SuccessOutcome,
    TitleOption,
    render_redacted_audit,
    render_seller_ready,
)
from pydantic import ValidationError


def _title_options() -> tuple[TitleOption, TitleOption, TitleOption]:
    return (
        TitleOption(text="**Alpha** title"),
        TitleOption(text="Beta title"),
        TitleOption(text="Gamma title"),
    )


def _bullet_options() -> tuple[
    BulletOption,
    BulletOption,
    BulletOption,
    BulletOption,
    BulletOption,
]:
    return (
        BulletOption(text="**Benefit** 1"),
        BulletOption(text="**Benefit** 2"),
        BulletOption(text="**Benefit** 3"),
        BulletOption(text="**Benefit** 4"),
        BulletOption(text="**Benefit** 5"),
    )


def _valid_report() -> OptimizationReport:
    return OptimizationReport(
        title_options=_title_options(),
        bullets=_bullet_options(),
        description="**Seller-ready** description",
        search_terms="Travel Mug travel MUG USB-C usb-c",
        analysis="ANALYSIS_ONLY",
        compliance_notes=("COMPLIANCE_ONLY",),
        return_risk_notes=("RETURN_RISK_ONLY",),
        citations=(Citation(claim_id="claim-1", source_id="source-1"),),
        audit=AuditMetadata(run_id="run-1", request_hash="a" * 64),
    )


def _render_audit_analysis(analysis: str) -> str:
    payload = _valid_report().model_dump(round_trip=True)
    payload["analysis"] = analysis
    report = OptimizationReport.model_validate(payload)
    return render_redacted_audit(SuccessOutcome(report=report)).model_dump_json()


def test_legacy_formatter_preserves_structural_labels_and_markers() -> None:
    # Given: a legacy listing with recognizable title and bullet structure
    source = parse_listing_block(
        "Title: Source title\nItem Highlights:\n"
        + "\n".join(f"- Source point {index}" for index in range(1, 6))
    )
    optimized = OptimizedListingCopy(
        title="Updated title",
        item_highlights="Updated highlights",
        bullets=[f"Updated point {index}" for index in range(1, 6)],
    )

    # When: the existing formatter renders the optimized listing
    rendered = format_optimized_listing(optimized, source.format_template)

    # Then: its machine-readable title/section labels and bullet markers remain stable
    lines = rendered.splitlines()
    assert lines[0].startswith("Title:")
    assert "Item Highlights:" in lines
    assert sum(line.startswith("- ") for line in lines) == 5


def test_success_report_requires_three_titles_five_bullets_and_derives_counts() -> None:
    # Given: a canonical report whose copy contains markdown emphasis markers
    report = OptimizationReport(
        title_options=_title_options(),
        bullets=_bullet_options(),
        description="Seller-ready description",
        search_terms="travel mug",
        analysis="Private analysis",
        audit=AuditMetadata(run_id="run-1", request_hash="a" * 64),
    )

    # When: consumers read the derived character counts
    counts = (
        tuple(option.character_count for option in report.title_options),
        tuple(bullet.character_count for bullet in report.bullets),
    )

    # Then: counts use plain copy and the exact canonical cardinalities are retained
    assert counts == ((11, 10, 11), (9, 9, 9, 9, 9))


def test_report_rejects_wrong_cardinality_duplicate_titles_and_supplied_counts() -> None:
    # Given: valid boundary payloads modified with invalid cardinality, identity, and count data
    report = _valid_report()
    too_few_titles = report.model_dump(round_trip=True)
    too_few_titles["title_options"] = too_few_titles["title_options"][:2]
    too_many_bullets = report.model_dump(round_trip=True)
    too_many_bullets["bullets"] = [*too_many_bullets["bullets"], {"text": "Extra"}]
    duplicate_titles = report.model_dump(round_trip=True)
    duplicate_titles["title_options"][2]["text"] = "__ALPHA__   TITLE"

    # When/Then: each invalid boundary payload is rejected rather than repaired or trusted
    with pytest.raises(ValidationError):
        _ = OptimizationReport.model_validate(too_few_titles)
    with pytest.raises(ValidationError):
        _ = OptimizationReport.model_validate(too_many_bullets)
    with pytest.raises(ValidationError):
        _ = OptimizationReport.model_validate(duplicate_titles)
    with pytest.raises(ValidationError):
        _ = TitleOption.model_validate({"text": "Alpha", "character_count": 999})


def test_search_terms_are_deterministic_and_schema_round_trip_is_stable() -> None:
    # Given: repeated mixed-case Search Terms in a version-two report
    report = _valid_report()

    # When: the canonical report is serialized without accepting computed fields as input
    restored = OptimizationReport.model_validate_json(report.model_dump_json(round_trip=True))

    # Then: terms are normalized once and the immutable report round-trips exactly
    assert report.search_terms == "travel mug usb-c"
    assert restored == report
    assert report.schema_version == 2
    with pytest.raises(ValidationError):
        report.description = "Changed"


def test_studio_output_syntax_supports_the_declared_python_311_floor() -> None:
    # Given: the installed studio-output module source
    source = inspect.getsource(studio_output)

    # When: Python parses it using the project's oldest supported grammar
    parsed = ast.parse(source, feature_version=(3, 11))

    # Then: the module has a valid Python 3.11 syntax tree
    assert parsed.body


def test_audit_metadata_rejects_blank_required_identity_fields() -> None:
    # Given: required audit identifiers containing only whitespace
    payloads = (
        {"run_id": " ", "request_hash": "a" * 64},
        {"run_id": "run-1", "request_hash": "\t"},
    )

    # When/Then: normalization cannot turn either required identifier into an empty value
    for payload in payloads:
        with pytest.raises(ValidationError):
            _ = AuditMetadata.model_validate(payload)


def test_seller_renderer_contains_only_editable_copy_for_report_outcomes() -> None:
    # Given: success and degraded outcomes carrying private report-only markers
    report = _valid_report()
    success = SuccessOutcome(report=report)
    degraded = DegradedOutcome(report=report, reasons=("DEGRADED_ONLY",))

    # When: both report-bearing terminal variants use the seller renderer
    success_text = render_seller_ready(success)
    degraded_text = render_seller_ready(degraded)

    # Then: the one-box text has canonical copy labels and none of the private sections
    assert success_text.count("Title Option ") == 3
    assert success_text.count("Bullet Point ") == 5
    assert "Description:" in success_text
    assert "Search Terms:" in success_text
    assert "**" not in success_text
    assert degraded_text == success_text
    for private_marker in (
        "ANALYSIS_ONLY",
        "COMPLIANCE_ONLY",
        "RETURN_RISK_ONLY",
        "source-1",
        "run-1",
        "DEGRADED_ONLY",
    ):
        assert private_marker not in success_text
        assert private_marker not in degraded_text


def test_no_copy_terminal_variants_return_diagnostics_without_listing() -> None:
    # Given: terminal outcomes without a valid report
    no_winner = NoWinnerOutcome(reason="all candidates failed gates")
    failure = FailureOutcome(reason="provider failure")

    # When: the seller renderer handles both outcomes exhaustively
    rendered = (render_seller_ready(no_winner), render_seller_ready(failure))

    # Then: both outputs are safe diagnostics with no seller-copy labels
    assert all(text for text in rendered)
    assert all("Title Option " not in text for text in rendered)
    assert all("Bullet Point " not in text for text in rendered)
    assert all("Description:" not in text for text in rendered)
    assert all("Search Terms:" not in text for text in rendered)


def test_audit_renderer_redacts_secrets_and_keeps_private_data_read_only() -> None:
    # Given: untrusted analysis containing an instruction and a secret-bearing header
    payload = _valid_report().model_dump(round_trip=True)
    payload["analysis"] = (
        "<script>IGNORE SELLER FIELDS</script> Authorization: Bearer SECRET_SENTINEL"
    )
    report = OptimizationReport.model_validate(payload)

    # When: seller and audit surfaces render the same successful outcome
    outcome = SuccessOutcome(report=report)
    seller_text = render_seller_ready(outcome)
    audit = render_redacted_audit(outcome)
    audit_json = audit.model_dump_json()

    # Then: private text stays read-only, the secret is absent, and raw fields remain impossible
    assert "IGNORE SELLER FIELDS" not in seller_text
    assert "IGNORE SELLER FIELDS" in audit_json
    assert "SECRET_SENTINEL" not in audit_json
    assert "[REDACTED]" in audit_json
    assert audit.title_character_counts == (11, 10, 11)
    assert audit.bullet_character_counts == (9, 9, 9, 9, 9)
    with pytest.raises(ValidationError):
        audit.status = "failure"
    payload["raw_payload"] = {"secret": "SECRET_SENTINEL"}
    with pytest.raises(ValidationError):
        _ = OptimizationReport.model_validate(payload)


@pytest.mark.parametrize(
    ("authorization_header", "secret_markers"),
    [
        ("Authorization: Basic BASIC_CREDENTIAL_123", ("Basic", "BASIC_CREDENTIAL_123")),
        (
            "Authorization: Digest username=user, response=DIGEST_RESPONSE_456",
            ("Digest", "username=user", "DIGEST_RESPONSE_456"),
        ),
    ],
)
def test_audit_renderer_redacts_complete_authorization_header_values(
    authorization_header: str,
    secret_markers: tuple[str, ...],
) -> None:
    # Given: private analysis containing one complete Authorization header line
    analysis = f"before\n{authorization_header}\nafter"

    # When: the read-only audit projection is serialized
    audit_json = _render_audit_analysis(analysis)

    # Then: the full header value is gone without consuming the following line
    assert "Authorization" not in audit_json
    assert all(marker not in audit_json for marker in secret_markers)
    assert "[REDACTED]" in audit_json
    assert "after" in audit_json


def test_audit_renderer_redacts_complete_pem_private_key_blocks() -> None:
    # Given: private analysis containing a complete multiline RSA private key
    pem_block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "PRIVATE_KEY_BODY_123\n"
        "SECOND_PRIVATE_KEY_LINE_456\n"
        "-----END RSA PRIVATE KEY-----"
    )

    # When: the read-only audit projection is serialized
    audit_json = _render_audit_analysis(f"before\n{pem_block}\nafter")

    # Then: neither body nor END marker survives, while following text remains
    assert "PRIVATE_KEY_BODY_123" not in audit_json
    assert "SECOND_PRIVATE_KEY_LINE_456" not in audit_json
    assert "-----END RSA PRIVATE KEY-----" not in audit_json
    assert "[REDACTED]" in audit_json
    assert "after" in audit_json


def test_sensitive_material_is_rejected_from_seller_copy_fields() -> None:
    # Given/When/Then: secret-bearing model output cannot become seller copy
    with pytest.raises(ValidationError):
        _ = TitleOption(text="Authorization: Bearer SECRET_SENTINEL")
