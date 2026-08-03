from pathlib import Path

from amazon_product_research.config import Settings


def test_shared_agent_configuration_is_inherited_with_expected_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    creation = tmp_path / "creation.env"
    optimization = tmp_path / "optimization.env"
    creation.write_text(
        "OPENAI_API_KEY=creation-model-key\nSORFTIME_MCP_KEY=creation-sorftime\n",
        encoding="utf-8",
    )
    optimization.write_text(
        "OPENAI_API_KEY=optimization-model-key\n"
        "WRITER_MODEL=shared-writer\n"
        "SIF_MCP_KEY=shared-sif\n"
        "MAX_LLM_CALLS=12\n"
        "MAX_MCP_CALLS=20\n",
        encoding="utf-8",
    )
    for key in ("OPENAI_API_KEY", "SORFTIME_MCP_KEY", "SIF_MCP_KEY", "WRITER_MODEL"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=(creation, optimization))
    assert settings.openai_api_key.get_secret_value() == "optimization-model-key"
    assert settings.analysis_model == "shared-writer"
    assert settings.sorftime_mcp_key.get_secret_value() == "creation-sorftime"
    assert settings.sif_mcp_key.get_secret_value() == "shared-sif"
    assert settings.max_llm_calls == 4
    assert settings.max_mcp_calls == 60
