from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_harness.api import create_app
from agent_harness.catalog import AgentCatalog


ROOT = Path(__file__).resolve().parents[1]


def test_platform_manifests_register_business_agents() -> None:
    catalog = AgentCatalog.load(ROOT / "harness-agents")
    agents = {agent.id: agent for agent in catalog.all()}

    assert set(agents) == {"listing-creation", "listing-optimization", "product-research"}
    assert agents["listing-creation"].service is not None
    assert agents["listing-creation"].service.port == 8501
    assert agents["listing-optimization"].service is not None
    assert agents["listing-optimization"].service.port == 8502
    assert agents["listing-creation"].cwd == ROOT / "agents" / "listing-creation"
    assert agents["product-research"].service is not None
    assert agents["product-research"].service.port == 8503


def test_harness_management_api_lists_platform_agents(tmp_path: Path) -> None:
    app = create_app(ROOT / "harness-agents", state_path=tmp_path / "state.db")
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        payload = client.get("/api/agents").json()
        assert {item["id"] for item in payload} == {
            "listing-creation",
            "listing-optimization",
            "product-research",
        }
        assert client.get("/api/agents/listing-creation/config").status_code == 200
        assert client.get("/api/agents/listing-creation/service/health").status_code == 503

