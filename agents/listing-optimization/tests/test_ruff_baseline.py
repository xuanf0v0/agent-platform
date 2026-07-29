from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

from tests.ruff_baseline import DiagnosticKey, compare_diagnostics

PROJECT_ROOT: Final = Path(__file__).parents[1]
LEGACY_FILENAME: Final = "tests/test_judging.py"
UNTYPED_FUNCTION: Final = "def adversarial_new_function(value):\n    return 1\n"


def test_ruff_config_rejects_new_annotation_errors_in_a_legacy_file() -> None:
    # Given: source with two annotation errors and a filename containing known legacy errors.
    # When: Ruff checks the source using the repository configuration.
    result = subprocess.run(  # noqa: S603 - resolved Ruff executable and fixed arguments
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--stdin-filename",
            LEGACY_FILENAME,
            "-",
        ],
        cwd=PROJECT_ROOT,
        input=UNTYPED_FUNCTION,
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: both new errors remain visible instead of inheriting a file-wide exemption.
    assert result.returncode == 1, result.stdout
    assert "ANN001" in result.stdout
    assert "ANN201" in result.stdout


def test_exact_baseline_rejects_the_same_rule_at_a_new_legacy_file_location() -> None:
    # Given: one known diagnostic and a second occurrence with the same file, code, and message.
    known = DiagnosticKey(
        filename=LEGACY_FILENAME,
        code="ANN001",
        message="Missing type annotation for function argument `value`",
        row=10,
        column=30,
        end_row=10,
        end_column=35,
    )
    added = DiagnosticKey(
        filename=LEGACY_FILENAME,
        code=known.code,
        message=known.message,
        row=20,
        column=30,
        end_row=20,
        end_column=35,
    )

    # When: the exact baseline compares the known and current diagnostics.
    delta = compare_diagnostics((known, added), (known,))

    # Then: location identity keeps the added occurrence outside the baseline.
    assert delta.new == (added,)
    assert delta.stale == ()
