from __future__ import annotations

import json
from typing import TYPE_CHECKING

from amazon_copy.cli import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _args(output: str) -> list[str]:
    return [
        "run",
        "--mock",
        "--product",
        "USB C Hub",
        "--market",
        "US",
        "--instruction",
        "7-in-1 hub",
        "--rootwords",
        "usb，hub,adapter,hdmi,macbook,port,multiport,laptop,apple,usbc,card,mac,dongle,pd,charging,4k,sd,microsd,chrome,dell,ipad",
        "--keywords",
        (
            "usb hub,usb c hub,usb-c hub,multiport adapter,hdmi hub,pd charging,"
            "4k hdmi,macbook hub,laptop hub,sd card reader"
        ),
        "--output",
        output,
    ]


def test_run_mock_creates_four_exports_and_parses_chinese_comma(tmp_path: Path) -> None:
    result = runner.invoke(app, _args(str(tmp_path)))
    assert result.exit_code == 0, result.output
    assert {path.name for path in tmp_path.iterdir()} == {
        "listing.json",
        "listing.md",
        "listing_marked.md",
        "report.md",
    }
    payload = json.loads((tmp_path / "listing.json").read_text(encoding="utf-8"))
    assert payload["product_input"]["rootwords"][:2] == ["usb", "hub"]
    assert "Completed" in result.output


def test_run_mock_strict_title_mode_creates_valid_exports(tmp_path: Path) -> None:
    """Studio path produces 3 title candidates (was 5 in legacy path)."""
    args = _args(str(tmp_path))
    args.extend(["--title-mode", "strict_amazon"])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "listing.json").read_text(encoding="utf-8"))
    assert len(payload["listing"]["title"]) > 0
    assert len(payload["listing"]["title_candidates"]) == 3  # studio produces 3 titles


def test_run_mock_strict_rejects_known_seller_before_export(tmp_path: Path) -> None:
    args = _args(str(tmp_path))
    args.extend(["--title-mode", "strict_amazon", "--seller-name", "USB"])
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "seller" in result.output.lower() or "policy" in result.output.lower()
    assert not (tmp_path / "listing.json").exists()


def test_copy_generation_commands_expose_optional_seller_name() -> None:
    for command in ("run", "write"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "--seller-name" in result.output


def test_missing_product_is_a_typer_usage_error(tmp_path: Path) -> None:
    args = _args(str(tmp_path))
    product_index = args.index("--product")
    del args[product_index : product_index + 2]
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "product" in result.output.lower()


def test_unknown_market_requires_explicit_locale(tmp_path: Path) -> None:
    args = _args(str(tmp_path))
    args[args.index("US")] = "DE"
    result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert "--locale" in result.output


def test_all_commands_expose_mock_flag() -> None:
    for command in ("run", "write", "optimize", "seo", "analyze"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "--mock" in result.output
