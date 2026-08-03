"""Read-only, redacted, failure-isolated editorial shadow observations."""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

from amazon_copy import api as api_module
from amazon_copy.config import Settings
from amazon_copy.editorial_shadow import (
    build_shadow_observation,
    record_shadow_observation,
)

from tests.specialized_ui_support import SOURCE, completed

if TYPE_CHECKING:
    import pytest


def test_shadow_observation_contains_only_allowed_redacted_fields() -> None:
    source = "SECRET-SOURCE Title and bullets"
    output = "SECRET-OUTPUT upload copy"
    result = completed().model_copy(update={"rendered_text": output})

    observation = build_shadow_observation(
        run_id="shadow-run",
        source_text=source,
        result=result,
        created_at="2026-08-03T00:00:00+00:00",
    )
    serialized = json.dumps(observation, ensure_ascii=False)

    assert observation["schema_version"] == 1
    assert len(str(observation["source_sha256"])) == 64
    assert len(str(observation["output_sha256"])) == 64
    assert set(observation["dimension_scores"]) == {
        "clarity",
        "voice_tone",
        "benefit_relevance",
        "evidence_support",
        "specificity",
        "emotional_resonance",
        "risk_control",
    }
    assert source not in serialized
    assert output not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "api.deepseek.com" not in serialized
    assert set(observation) == {
        "schema_version",
        "created_at",
        "run_id",
        "source_sha256",
        "output_sha256",
        "dimension_scores",
        "problem_codes",
    }


def test_shadow_record_is_ndjson_and_never_contains_raw_copy(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "observations" / "editorial-shadow.jsonl"
    result = completed()

    record_shadow_observation(
        path,
        run_id="one",
        source_text=SOURCE,
        result=result,
    )
    record_shadow_observation(
        path,
        run_id="two",
        source_text=SOURCE,
        result=result,
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["run_id"] for row in rows] == ["one", "two"]
    assert SOURCE not in path.read_text(encoding="utf-8")
    assert result.rendered_text not in path.read_text(encoding="utf-8")


def test_shadow_failure_does_not_change_completed_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    result = completed()
    before = result.model_dump(mode="json")
    run = api_module.RunState(
        "isolated-shadow",
        SOURCE,
        None,
        status="completed",
        result=result,
    )
    previous_settings = api_module._settings
    monkeypatch.setattr(
        api_module,
        "_settings",
        Settings(
            MOCK=True,
            CHECKPOINT_PATH=tmp_path / "checkpoints.sqlite3",
            EDITORIAL_SHADOW_ENABLED=True,
        ),
    )

    def fail_record(*_args: object, **_kwargs: object) -> None:
        message = "disk unavailable"
        raise OSError(message)

    monkeypatch.setattr(api_module, "record_shadow_observation", fail_record)
    try:
        api_module._record_editorial_shadow_best_effort(run)
    finally:
        monkeypatch.setattr(api_module, "_settings", previous_settings)

    assert run.result is result
    assert run.result.model_dump(mode="json") == before


def test_successful_shadow_does_not_change_public_result_serialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    result = completed()
    before = result.model_dump_json()
    run = api_module.RunState(
        "successful-shadow",
        SOURCE,
        None,
        status="completed",
        result=result,
    )
    previous_settings = api_module._settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_module,
        "_settings",
        Settings(MOCK=True, EDITORIAL_SHADOW_ENABLED=True),
    )
    try:
        api_module._record_editorial_shadow_best_effort(run)
    finally:
        monkeypatch.setattr(api_module, "_settings", previous_settings)

    assert run.result is result
    assert run.result.model_dump_json() == before
    assert (
        tmp_path / ".amazon_copy" / "observations" / "editorial-shadow.jsonl"
    ).is_file()


def test_disabled_shadow_skips_recording(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    run = api_module.RunState(
        "disabled-shadow",
        SOURCE,
        None,
        status="completed",
        result=completed(),
    )
    previous_settings = api_module._settings
    called = False

    def record(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(api_module, "record_shadow_observation", record)
    monkeypatch.setattr(
        api_module,
        "_settings",
        Settings(
            MOCK=True,
            CHECKPOINT_PATH=tmp_path / "checkpoints.sqlite3",
            EDITORIAL_SHADOW_ENABLED=False,
        ),
    )
    try:
        api_module._record_editorial_shadow_best_effort(run)
    finally:
        monkeypatch.setattr(api_module, "_settings", previous_settings)

    assert called is False


def test_api_shadow_path_is_fixed_outside_checkpoint_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    run = api_module.RunState(
        "fixed-shadow-path",
        SOURCE,
        None,
        status="completed",
        result=completed(),
    )
    captured: list[pathlib.Path] = []
    previous_settings = api_module._settings

    def record(path: pathlib.Path, **_kwargs: object) -> None:
        captured.append(path)

    monkeypatch.setattr(api_module, "record_shadow_observation", record)
    monkeypatch.setattr(
        api_module,
        "_settings",
        Settings(
            MOCK=True,
            CHECKPOINT_PATH=tmp_path / "custom.sqlite3",
            EDITORIAL_SHADOW_ENABLED=True,
        ),
    )
    try:
        api_module._record_editorial_shadow_best_effort(run)
    finally:
        monkeypatch.setattr(api_module, "_settings", previous_settings)

    assert captured == [pathlib.Path(".amazon_copy/observations/editorial-shadow.jsonl")]


def test_api_records_shadow_only_after_public_done_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = completed()
    run = api_module.RunState("event-order", SOURCE, None)
    observed_events: list[str] = []
    monkeypatch.setattr(
        api_module,
        "run_automatic_optimization",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(api_module, "_persist", lambda _run: None)
    monkeypatch.setattr(
        api_module,
        "_record_editorial_shadow_best_effort",
        lambda current: observed_events.extend(event["event"] for event in current.events),
    )

    api_module._execute(run, api_module.AutomaticOptimizationContext())

    assert observed_events[-2:] == ["result", "done"]
    assert run.result is result
    assert "editorial_shadow" not in run.payload()


def test_editorial_shadow_setting_defaults_on_and_accepts_environment_alias() -> None:
    assert Settings(_env_file=None).editorial_shadow_enabled is True
    disabled = Settings(_env_file=None, EDITORIAL_SHADOW_ENABLED=False)
    assert disabled.editorial_shadow_enabled is False
