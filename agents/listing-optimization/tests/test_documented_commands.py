"""Tests that the commands and APIs documented in README actually exist and work.

These tests verify structural contract points — they assert that CLI commands
exit with code 0 and that key imports resolve.  They do NOT assert specific
prose text from README.md or DESIGN.md.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from amazon_copy.cli import app
from amazon_copy.orchestrator.studio_graph import run_studio_pipeline
from amazon_copy.studio import StudioService
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


# ── CLI help exits 0 ─────────────────────────────────────────────────────


class TestCLIHelp:
    """Top-level --help and subcommand --help all exit 0."""

    @staticmethod
    def test_module_entry_help_exits_zero() -> None:
        """``python -m amazon_copy.cli --help`` exits 0."""
        result = subprocess.run(
            [sys.executable, "-m", "amazon_copy.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

    @staticmethod
    def test_console_script_help_exits_zero() -> None:
        """``amz-copy --help`` via Typer runner exits 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    @staticmethod
    @pytest.mark.parametrize(
        "command",
        ["run", "write", "optimize", "seo", "analyze"],
    )
    def test_each_subcommand_help_exits_zero(command: str) -> None:
        """Every documented subcommand ``--help`` exits 0."""
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0, (
            f"'{command} --help' exited {result.exit_code}: {result.output[:200]}"
        )


# ── Studio service imports resolve ───────────────────────────────────────


class TestStudioImports:
    """Key studio APIs documented in README are importable."""

    @staticmethod
    def test_studio_service_importable() -> None:
        """``StudioService`` is importable from ``amazon_copy.studio``."""
        from amazon_copy.studio import StudioService as Service

        assert Service is StudioService

    @staticmethod
    def test_run_studio_pipeline_importable() -> None:
        """``run_studio_pipeline`` is importable from ``orchestrator.studio_graph``."""
        from amazon_copy.orchestrator.studio_graph import run_studio_pipeline as rsp

        assert rsp is run_studio_pipeline

    @staticmethod
    def test_studio_service_constructs_with_defaults() -> None:
        """``StudioService()`` constructs with no arguments (env settings)."""
        service = StudioService()
        assert service is not None
        assert service._settings is None  # defaults to None → Settings() from env
        assert service._provider is None
        assert service._budget is None
