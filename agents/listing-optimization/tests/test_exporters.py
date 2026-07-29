from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from amazon_copy.config import Settings
from amazon_copy.exporters import export_package, export_studio_report
from amazon_copy.orchestrator.asyncio_pipeline import run_pipeline
from amazon_copy.schemas import EmbedRow, FinalPackage, ProductInput, SEOCheck
from amazon_copy.schemas.studio_output import (
    AuditMetadata,
    BulletOption,
    OptimizationReport,
    SuccessOutcome,
    TitleOption,
)

if TYPE_CHECKING:
    from pathlib import Path


def _package() -> FinalPackage:
    product = ProductInput(
        product="USB C Hub",
        market="US",
        instruction="7-in-1 hub",
        rootwords=[
            "usb",
            "hub",
            "adapter",
            "hdmi",
            "macbook",
            "port",
            "multiport",
            "laptop",
            "apple",
            "usbc",
            "card",
            "mac",
            "dongle",
            "pd",
            "charging",
            "4k",
            "sd",
            "microsd",
            "chrome",
            "dell",
            "ipad",
        ],
        keywords=[
            "usb hub",
            "usb c hub",
            "usb-c hub",
            "multiport adapter",
            "hdmi hub",
            "pd charging",
            "4k hdmi",
            "macbook hub",
            "laptop hub",
            "sd card reader",
        ],
    )
    return asyncio.run(run_pipeline(product, settings=Settings(mock=True)))


def test_export_package_escapes_markdown_pipe_under_python311(tmp_path: Path) -> None:
    package = _package()
    seo = SEOCheck(intent_rows=[EmbedRow(item="left|right", present=True)])

    _ = export_package(package.model_copy(update={"seo": seo}), tmp_path)

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "| left\\|right | V |" in report


def test_export_package_writes_json_and_markdown_files(tmp_path: Path) -> None:
    """Studio-sourced package exports 4 files with listing content."""
    package = _package()
    paths = export_package(package, tmp_path)

    assert set(paths) == {"json", "listing", "listing_marked", "report"}
    payload = json.loads((tmp_path / "listing.json").read_text(encoding="utf-8"))
    assert payload["product_input"]["product"] == "USB C Hub"
    assert len(payload["listing"]["bullets"]) == 5
    plain = (tmp_path / "listing.md").read_text(encoding="utf-8")
    marked = (tmp_path / "listing_marked.md").read_text(encoding="utf-8")
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**" not in plain
    assert "Amazon Copywriting Report" in report


def test_export_package_overwrites_stale_files_and_leaves_no_temp_files(tmp_path: Path) -> None:
    (tmp_path / "listing.json").write_text("stale", encoding="utf-8")
    export_package(_package(), tmp_path)
    assert json.loads((tmp_path / "listing.json").read_text(encoding="utf-8"))
    assert not list(tmp_path.glob("*.tmp"))


def test_export_package_writes_four_files_on_disk(tmp_path: Path) -> None:
    """export_package creates all four expected output files."""
    export_package(_package(), tmp_path)
    assert (tmp_path / "listing.json").is_file()
    assert (tmp_path / "listing.md").is_file()
    assert (tmp_path / "listing_marked.md").is_file()
    assert (tmp_path / "report.md").is_file()


def test_export_studio_redacts_secret_sentinel(tmp_path: Path) -> None:
    """studio export omits SECRET_SENTINEL from all four output files."""
    # Use model_construct to bypass schema validation so SECRET_SENTINEL
    # survives into the model and is caught by the export sanitizer.
    report = OptimizationReport.model_construct(
        title_options=(
            TitleOption(text="Alpha title"),
            TitleOption(text="Beta title"),
            TitleOption(text="Gamma title"),
        ),
        bullets=(
            BulletOption(text="Benefit 1"),
            BulletOption(text="Benefit 2"),
            BulletOption(text="Benefit 3"),
            BulletOption(text="Benefit 4"),
            BulletOption(text="Benefit 5"),
        ),
        description="Clean description",
        search_terms="clean terms",
        analysis="Leaked SECRET_SENTINEL here",
        evidence_gaps=(),
        keyword_allocation=(),
        compliance_notes=(),
        return_risk_notes=(),
        citations=(),
        audit=AuditMetadata(run_id="run-1", request_hash="a" * 64),
    )
    outcome = SuccessOutcome(report=report)
    export_studio_report(outcome, tmp_path)

    for name in ("listing.json", "listing.md", "listing_marked.md", "report.md"):
        content = (tmp_path / name).read_text(encoding="utf-8")
        assert "SECRET_SENTINEL" not in content, f"{name} contains SECRET_SENTINEL"
