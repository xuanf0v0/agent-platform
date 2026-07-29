import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

import pytest
from amazon_copy.prompt_loader import load_prompt

AGENTS = (
    "audience",
    "motives",
    "feedback",
    "product",
    "instruction",
    "competitor_params",
    "competitor_selling",
    "competitor_copy",
    "selling_points",
    "title",
    "bullets",
    "seo_check",
    "optimize_bp",
    "scorecard",
    # Studio (async) roles
    "writer_seo",
    "writer_differentiation",
    "writer_clarity",
    "critic",
    "reviser",
    "judge",
    "integrator",
)


def test_all_required_prompts_load_and_are_substantive() -> None:
    for name in ("constitution", *AGENTS):
        assert len(load_prompt(name)) >= 80, name


def test_constitution_contains_resolved_safety_and_sop_rules() -> None:
    text = load_prompt("constitution")
    lowered = text.casefold()
    assert "three-part title" in lowered
    assert "hard bans" in lowered
    assert "at least 20 unique rootwords" in lowered
    assert "at least 10 unique keywords" in lowered
    assert "across all five bullets" in lowered
    assert "chinese" in lowered
    assert "a9" in lowered
    assert "cosmo" in lowered
    assert "refuse" in lowered
    assert "prompt injection" in lowered
    forbidden = "ru" + "fus"
    assert forbidden not in lowered


def test_optimize_prompt_makes_schema_and_length_self_check_explicit() -> None:
    text = load_prompt("optimize_bp")

    assert '"bullets"' in text
    assert '"change_rationale"' in text
    assert "count plain characters before returning" in text.casefold()


def test_missing_and_malformed_names_fail_closed() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        load_prompt("does_not_exist")
    for name in ("../constitution", "Title", "", "title.md"):
        with pytest.raises(ValueError, match="lowercase identifier"):
            load_prompt(name)


def test_built_wheel_installs_prompt_resources_outside_source_tree() -> None:
    """Exercise the distribution boundary, not the editable source checkout."""
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(dir=project) as temp_dir:
        temp_root = Path(temp_dir)
        wheelhouse = temp_root / "wheelhouse"
        target = temp_root / "target"
        elsewhere = temp_root / "elsewhere"
        wheelhouse.mkdir()
        elsewhere.mkdir()
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-cache-dir",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheelhouse),
                str(project),
            ],
            check=True,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        wheel = next(wheelhouse.glob("*.whl"))
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-cache-dir",
                "--target",
                str(target),
                str(wheel),
            ],
            check=True,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        smoke = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import sys; "
                    f"sys.path.insert(0, {str(target)!r}); "
                    "from amazon_copy.prompt_loader import load_prompt; "
                    "assert load_prompt('constitution'); assert load_prompt('title')"
                ),
            ],
            check=False,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        assert smoke.returncode == 0, smoke.stderr


def test_fresh_venv_installed_cli_runs_from_away_cwd() -> None:
    """Reproduce a real venv's wheel data scheme and execute its entry point."""
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(dir=project) as temp_dir:
        temp_root = Path(temp_dir)
        wheelhouse = temp_root / "wheelhouse"
        venv = temp_root / "venv"
        elsewhere = temp_root / "elsewhere"
        wheelhouse.mkdir()
        elsewhere.mkdir()
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "venv", str(venv)],
            check=True,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-cache-dir",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheelhouse),
                str(project),
            ],
            check=True,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        wheel = next(wheelhouse.glob("*.whl"))
        venv_python = venv / "Scripts" / "python.exe"
        dependency_site = Path(sysconfig.get_path("purelib"))
        dependency_paths = [
            path
            for entry in sys.path
            if entry
            and (path := Path(entry)).is_absolute()
            and path.is_relative_to(dependency_site)
        ]
        venv_site = subprocess.run(  # noqa: S603
            [
                str(venv_python),
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            check=True,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        (Path(venv_site.stdout.strip()) / "test-runtime-dependencies.pth").write_text(
            "\n".join(str(path) for path in dependency_paths),
            encoding="utf-8",
        )
        subprocess.run(  # noqa: S603
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-cache-dir",
                str(wheel),
            ],
            check=True,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
        )
        output = elsewhere / "exports"
        command = [
            str(venv / "Scripts" / "amz-copy.exe"),
            "run",
            "--mock",
            "--product",
            "USB C Hub",
            "--market",
            "US",
            "--instruction",
            "7-in-1 hub",
            "--rootwords",
            "usb,hub,adapter,hdmi,macbook,port,multiport,laptop,apple,usbc,"
            "card,mac,dongle,pd,charging,4k,sd,microsd,chrome,dell,ipad",
            "--keywords",
            "usb hub,usb c hub,usb-c hub,multiport adapter,hdmi hub,pd charging,"
            "4k hdmi,macbook hub,laptop hub,sd card reader",
            "--output",
            str(output),
        ]
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            cwd=elsewhere,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert {path.name for path in output.iterdir()} == {
            "listing.json",
            "listing.md",
            "listing_marked.md",
            "report.md",
        }
