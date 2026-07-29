# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2", "ruff>=0.12,<1"]
# ///
# ─── How to run ───
# python tests/ruff_baseline.py
# python tests/ruff_baseline.py --refresh

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, TypeAdapter

PROJECT_ROOT: Final = Path(__file__).parents[1]
BASELINE_PATH: Final = Path(__file__).with_name("ruff_baseline.json")
RUFF_TARGETS: Final = ("amazon_copy", "tests")


class RuffPosition(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    row: int
    column: int


class RuffDiagnostic(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    filename: str
    code: str | None
    message: str
    location: RuffPosition
    end_location: RuffPosition


@dataclass(frozen=True, slots=True)
class DiagnosticKey:
    filename: str
    code: str | None
    message: str
    row: int
    column: int
    end_row: int
    end_column: int


@dataclass(frozen=True, slots=True)
class BaselineDelta:
    new: tuple[DiagnosticKey, ...]
    stale: tuple[DiagnosticKey, ...]


class RuffExecutionError(RuntimeError):
    returncode: int
    stderr: str

    def __init__(self, *, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"Ruff exited with status {returncode}: {stderr}")


class RuffPathError(RuntimeError):
    filename: Path
    root: Path

    def __init__(self, *, filename: Path, root: Path) -> None:
        self.filename = filename
        self.root = root
        super().__init__(f"Ruff reported a path outside {root}: {filename}")


RAW_DIAGNOSTICS: Final = TypeAdapter(tuple[RuffDiagnostic, ...])
BASELINE_DIAGNOSTICS: Final = TypeAdapter(tuple[DiagnosticKey, ...])


def diagnostic_key(diagnostic: RuffDiagnostic) -> DiagnosticKey:
    filename = Path(diagnostic.filename).resolve()
    try:
        relative_filename = filename.relative_to(PROJECT_ROOT).as_posix()
    except ValueError as error:
        raise RuffPathError(filename=filename, root=PROJECT_ROOT) from error
    return DiagnosticKey(
        filename=relative_filename,
        code=diagnostic.code,
        message=diagnostic.message,
        row=diagnostic.location.row,
        column=diagnostic.location.column,
        end_row=diagnostic.end_location.row,
        end_column=diagnostic.end_location.column,
    )


def sort_key(diagnostic: DiagnosticKey) -> tuple[str, int, int, str, str, int, int]:
    return (
        diagnostic.filename,
        diagnostic.row,
        diagnostic.column,
        diagnostic.code or "",
        diagnostic.message,
        diagnostic.end_row,
        diagnostic.end_column,
    )


def parse_ruff_output(payload: str) -> tuple[DiagnosticKey, ...]:
    parsed = RAW_DIAGNOSTICS.validate_json(payload)
    return tuple(sorted((diagnostic_key(item) for item in parsed), key=sort_key))


def load_baseline() -> tuple[DiagnosticKey, ...]:
    parsed = BASELINE_DIAGNOSTICS.validate_json(BASELINE_PATH.read_text(encoding="utf-8"))
    return tuple(sorted(parsed, key=sort_key))


def compare_diagnostics(
    current: tuple[DiagnosticKey, ...], baseline: tuple[DiagnosticKey, ...]
) -> BaselineDelta:
    current_counts = Counter(current)
    baseline_counts = Counter(baseline)
    new = tuple(sorted((current_counts - baseline_counts).elements(), key=sort_key))
    stale = tuple(sorted((baseline_counts - current_counts).elements(), key=sort_key))
    return BaselineDelta(new=new, stale=stale)


def collect_diagnostics() -> tuple[DiagnosticKey, ...]:
    result = subprocess.run(  # noqa: S603 - current interpreter and fixed arguments
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "json",
            *RUFF_TARGETS,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuffExecutionError(returncode=result.returncode, stderr=result.stderr)
    return parse_ruff_output(result.stdout)


def render(diagnostic: DiagnosticKey) -> str:
    code = diagnostic.code or "syntax-error"
    return (
        f"{diagnostic.filename}:{diagnostic.row}:{diagnostic.column}: "
        f"{code} {diagnostic.message}"
    )


def main() -> int:
    arguments = sys.argv[1:]
    current = collect_diagnostics()
    if arguments == ["--refresh"]:
        payload = BASELINE_DIAGNOSTICS.dump_json(current, indent=2)
        _ = BASELINE_PATH.write_bytes(payload + b"\n")
        _ = sys.stdout.write(f"Wrote {len(current)} diagnostics to {BASELINE_PATH}\n")
        return 0
    if arguments:
        _ = sys.stderr.write("Usage: python tests/ruff_baseline.py [--refresh]\n")
        return 2

    baseline = load_baseline()
    delta = compare_diagnostics(current, baseline)
    for diagnostic in delta.new:
        _ = sys.stderr.write(f"NEW: {render(diagnostic)}\n")
    for diagnostic in delta.stale:
        _ = sys.stderr.write(f"STALE: {render(diagnostic)}\n")
    if delta.new or delta.stale:
        _ = sys.stderr.write(
            f"Ruff baseline mismatch: {len(delta.new)} new, {len(delta.stale)} stale.\n"
        )
        return 1

    _ = sys.stdout.write(f"Ruff baseline passed: {len(current)} known, 0 new, 0 stale.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
