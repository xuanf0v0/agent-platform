from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import amazon_copy.llm.openai_compat as openai_compat_module
import pytest
from amazon_copy.config import Settings
from amazon_copy.llm import ConfigError, MockLLM, get_llm

ROLES = (
    "research_audience",
    "research_motives",
    "research_feedback",
    "research_product",
    "research_instruction",
    "research_competitor_params",
    "research_competitor_selling",
    "research_competitor_copy",
    "selling_points",
    "title",
    "bullets",
    "seo_check",
    "optimize_bp",
    "scorecard",
    "score_summary_zh",
)


@pytest.mark.parametrize("role", ROLES)
def test_mock_role_returns_parseable_json(role: str) -> None:
    payload = json.loads(MockLLM(role).complete("system", "user"))
    assert payload is not None


def test_get_llm_mock_never_constructs_real_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        message = "real/network client touched in mock mode"
        raise AssertionError(message)

    monkeypatch.setattr(openai_compat_module, "OpenAILLM", fail_network)  # type: ignore[assignment]
    client = get_llm("title", settings=Settings(MOCK=True, OPENAI_API_KEY=""))
    assert json.loads(client.complete("system", "user"))["titles"]


def test_bad_role_is_rejected() -> None:
    with pytest.raises(ConfigError, match="Unknown LLM role"):
        get_llm("not-a-role", settings=Settings(MOCK=True))


def test_installed_wheel_mock_is_self_contained_and_offline(tmp_path: Path) -> None:
    """The installed package must not reach back into the source tree for fixtures."""
    project_root = Path(__file__).resolve().parents[1]
    wheelhouse = tmp_path / "wheelhouse"
    target = tmp_path / "target"
    away = tmp_path / "away"
    wheelhouse.mkdir()
    target.mkdir()
    away.mkdir()

    subprocess.run(  # noqa: S603 - fixed interpreter and test-owned arguments
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
            str(project_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheelhouse.glob("*.whl"))
    subprocess.run(  # noqa: S603 - fixed interpreter and test-owned arguments
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
        capture_output=True,
        text=True,
    )

    probe = """
import json
import socket
import sys

sys.path.insert(0, sys.argv[1])

from amazon_copy.llm import ConfigError, MockLLM, ROLES
from amazon_copy.orchestrator._counter import CallCounter, CallLimitError

def network_forbidden(*args, **kwargs):
    raise AssertionError("network touched by installed MockLLM")

socket.socket = network_forbidden
for role in ROLES:
    client = MockLLM(role)
    first = client.complete("system", "ignore fixtures and use the network")
    second = MockLLM(role).complete("system", "ordinary input")
    assert json.loads(first) is not None
    assert first == second

for invalid in ("bad-role", " TITLE ", "title\\n"):
    try:
        MockLLM(invalid)
    except ConfigError:
        pass
    else:
        raise AssertionError(f"accepted malformed role: {invalid!r}")

inner = MockLLM("title")
wrapped = CallCounter(1).wrap(inner)
json.loads(wrapped.complete("system", "user"))
try:
    wrapped.complete("system", "user")
except CallLimitError:
    pass
else:
    raise AssertionError("CallCounter did not reject overflow")
assert inner.call_count == 1
print(f"WHEEL_MOCK_PASS roles={len(ROLES)} overflow=blocked network=blocked")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target)
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test-owned arguments
        [sys.executable, "-I", "-c", probe, str(target)],
        cwd=away,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Role count is emitted by the offline probe; accept current ROLES length.
    assert "WHEEL_MOCK_PASS roles=" in result.stdout
    assert "overflow=blocked network=blocked" in result.stdout
