"""Explicit, secret-safe DeepSeek integration test (skipped by default)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import TYPE_CHECKING

import pytest
from amazon_copy.agents.seo import check_listing_seo
from amazon_copy.compliance.check import validate_bullets, validate_title
from amazon_copy.config import Settings
from amazon_copy.orchestrator.asyncio_pipeline import run_pipeline
from amazon_copy.schemas import PipelineMode, ProductInput, TitleMode
from openai import OpenAI

if TYPE_CHECKING:
    from collections.abc import Callable


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_DEEPSEEK_LIVE") != "1",
        reason="set RUN_DEEPSEEK_LIVE=1 for explicit billed network QA",
    ),
]


class _AuditLLM:
    def __init__(self, client: OpenAI, model: str) -> None:
        self.client = client
        self.model = model
        self._call_count = 0
        self.metadata: list[dict[str, object]] = []

    @property
    def call_count(self) -> int:
        return self._call_count

    def complete(self, system: str, user: str, **kwargs: object) -> str:
        del kwargs
        self._call_count += 1
        started = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1800,
            timeout=50.0,
        )
        usage = response.usage
        self.metadata.append(
            {
                "id_suffix": (response.id or "")[-8:],
                "model": response.model,
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
            }
        )
        return response.choices[0].message.content or ""


def _settings_and_client() -> tuple[Settings, OpenAI]:
    settings = Settings()
    if not settings.effective_api_key:
        pytest.fail("missing API credential in local .env", pytrace=False)
    return settings, OpenAI(
        api_key=settings.effective_api_key,
        base_url=settings.openai_api_base,
    )


def test_deepseek_structured_json_live(
    record_property: Callable[[str, object], None],
) -> None:
    settings, client = _settings_and_client()
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.writer_model,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Return exactly: {"status":"ok"}'},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=32,
            timeout=20.0,
        )
        assert json.loads(response.choices[0].message.content or "") == {"status": "ok"}
    except Exception as exc:  # noqa: BLE001  # pragma: no cover - sanitize provider failure
        pytest.fail(
            f"sanitized provider failure: {type(exc).__name__} "
            f"status={getattr(exc, 'status_code', None)}",
            pytrace=False,
        )
    usage = response.usage
    record_property("response_id_suffix", (response.id or "")[-8:])
    record_property("response_model", response.model)
    record_property("prompt_tokens", usage.prompt_tokens if usage else -1)
    record_property("completion_tokens", usage.completion_tokens if usage else -1)
    record_property("elapsed_ms", round((time.perf_counter() - started) * 1000))


def test_deepseek_amazon_optimize_pipeline_live(
    record_property: Callable[[str, object], None],
) -> None:
    settings, client = _settings_and_client()
    product = ProductInput(
        product="USB-C to USB-A Adapter 2-Pack",
        market="US",
        instruction="Improve clarity without inventing specifications",
        rootwords=["usb c", "adapter"],
        keywords=["usb c adapter", "usb a adapter"],
        locale="en",
    )
    title = (
        "USB-C to USB-A Adapter 2-Pack for Compatible Phones Tablets Laptops Keyboards "
        "Mice Flash Drives and Everyday USB Accessories"
    )
    source = [
        "Connect everyday USB-A accessories to a compatible USB-C device",
        "Compact adapter shape fits easily in a laptop bag or desk drawer",
        "Two-pack provides one adapter for a desk and one for travel",
        "Simple plug-in design supports convenient accessory connections",
        "Use with compatible USB-C phones tablets and laptops",
    ]
    audit = _AuditLLM(client, settings.writer_model)
    try:
        package = asyncio.run(
            run_pipeline(
                product,
                PipelineMode.OPTIMIZE,
                title=title,
                bullets=source,
                instructions="Rewrite for clear shopper benefits without unsupported claims",
                settings=settings,
                llm_factory=lambda _role: audit,
                max_llm_calls=2,
            )
        )
    except Exception as exc:  # noqa: BLE001  # pragma: no cover - sanitize provider failure
        pytest.fail(
            f"sanitized pipeline failure: {type(exc).__name__}",
            pytrace=False,
        )
    assert package.listing is not None
    assert package.stage.value == "completed"
    assert len(package.listing.bullets) == 5
    assert not validate_title(package.listing.title, TitleMode.SOP_SEO).errors
    assert not validate_bullets(package.listing.bullets, mode="optimize").errors
    seo = check_listing_seo(
        package.listing,
        ["compatibility", "portable two-pack"],
        product.rootwords,
        product.keywords,
    )
    assert len(seo.keyword_rows) == 2
    assert len(seo.rootword_rows) == 2
    record_property("llm_calls", audit.call_count)
    record_property("bullet_count", len(package.listing.bullets))
    record_property(
        "bullet_plain_lengths",
        ",".join(str(bullet.plain_len) for bullet in package.listing.bullets),
    )
    record_property("compliance_errors", 0)
    record_property("seo_keyword_rows", len(seo.keyword_rows))
    record_property("seo_rootword_rows", len(seo.rootword_rows))
    record_property("provider_metadata", json.dumps(audit.metadata, separators=(",", ":")))
