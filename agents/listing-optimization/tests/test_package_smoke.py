from __future__ import annotations

from importlib.resources import files

import amazon_copy
from amazon_copy import (
    StudioService,
    StudioState,
    package_from_studio_state,
    run_pipeline,
    run_studio_pipeline,
)


def test_public_exports_importable() -> None:
    assert callable(run_pipeline)
    assert callable(run_studio_pipeline)
    assert StudioService is not None
    assert StudioState is not None
    assert callable(package_from_studio_state)
    assert amazon_copy.__version__


def test_mcp_fixture_package_data_present() -> None:
    root = files("amazon_copy.mcp.fixtures")
    for name in (
        "competitor.json",
        "keyword.json",
        "policy.json",
        "product.json",
        "shopper.json",
    ):
        assert (root / name).is_file(), name


def test_prompts_package_data_present() -> None:
    # at least one packaged prompt md under amazon_copy.prompts
    prompt_root = files("amazon_copy.prompts")
    found = list(prompt_root.iterdir())
    assert found, "expected packaged prompts"
