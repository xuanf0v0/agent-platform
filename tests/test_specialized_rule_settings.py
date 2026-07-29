import pytest
from amazon_copy.config import Settings
from pydantic import ValidationError


def test_listing_optimize_resource_settings_use_server_side_environment_aliases() -> None:
    # Given: one HTTPS Resources endpoint and a Bearer secret supplied server-side.
    bearer_sentinel = "listing-rule-secret-sentinel"

    # When: settings parse the listing-optimize environment aliases.
    settings = Settings.model_validate(
        {
            "LISTING_OPTIMIZE_MCP_URL": "https://rules.example.test/mcp",
            "LISTING_OPTIMIZE_MCP_TOKEN": bearer_sentinel,
            "LISTING_OPTIMIZE_MCP_TIMEOUT_SECONDS": 7,
            "LISTING_OPTIMIZE_MCP_MAX_RESOURCE_BYTES": 8192,
            "LISTING_OPTIMIZE_MCP_MAX_PAGES": 4,
        }
    )

    # Then: transport limits are typed and the credential is absent from repr.
    assert settings.listing_optimize_mcp_url == "https://rules.example.test/mcp"
    assert settings.listing_optimize_mcp_token.get_secret_value() == bearer_sentinel
    assert settings.listing_optimize_mcp_timeout_seconds == 7
    assert settings.listing_optimize_mcp_max_resource_bytes == 8192
    assert settings.listing_optimize_mcp_max_pages == 4
    assert bearer_sentinel not in repr(settings)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://rules.example.test/mcp",
        "https://user:password@rules.example.test/mcp",
        "https://rules.example.test/mcp?token=embedded-secret",
        "https://rules.example.test/mcp#credential",
    ],
)
def test_listing_optimize_endpoint_rejects_insecure_or_embedded_credentials(
    endpoint: str,
) -> None:
    # Given: a configured endpoint that is not a credential-free HTTPS origin.
    sentinel = "embedded-secret"

    # When: the settings boundary parses the endpoint.
    with pytest.raises(ValidationError) as captured:
        _ = Settings.model_validate({"LISTING_OPTIMIZE_MCP_URL": endpoint})

    # Then: validation rejects it without echoing credential material.
    assert sentinel not in str(captured.value)


def test_listing_optimize_resource_limits_are_bounded() -> None:
    # Given: the immutable specialized-rule transport defaults.
    settings = Settings.model_validate({})

    # When: defaults and out-of-range values are evaluated.
    invalid_values = (
        {"LISTING_OPTIMIZE_MCP_TIMEOUT_SECONDS": 0},
        {"LISTING_OPTIMIZE_MCP_TIMEOUT_SECONDS": 31},
        {"LISTING_OPTIMIZE_MCP_MAX_RESOURCE_BYTES": 0},
        {"LISTING_OPTIMIZE_MCP_MAX_RESOURCE_BYTES": 262145},
        {"LISTING_OPTIMIZE_MCP_MAX_PAGES": 0},
        {"LISTING_OPTIMIZE_MCP_MAX_PAGES": 33},
    )

    # Then: safe defaults load and every value outside its hard cap is rejected.
    assert settings.listing_optimize_mcp_timeout_seconds == 10
    assert settings.listing_optimize_mcp_max_resource_bytes == 64_000
    assert settings.listing_optimize_mcp_max_pages == 16
    for values in invalid_values:
        with pytest.raises(ValidationError):
            _ = Settings.model_validate(values)
