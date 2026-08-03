from pathlib import Path

import amazon_product_research.api as api_module
from amazon_product_research.store import RunStore
from fastapi.testclient import TestClient


def test_health_and_empty_history(tmp_path: Path) -> None:
    previous = api_module.store
    api_module.store = RunStore(tmp_path / "runs.sqlite3")
    api_module.memory = {}
    try:
        with TestClient(api_module.app) as client:
            assert client.get("/health").json()["agent"] == "product-research"
            assert client.get("/runs").json() == []
    finally:
        api_module.store = previous


def test_compare_requires_two_candidates() -> None:
    with TestClient(api_module.app) as client:
        response = client.post(
            "/runs",
            json={
                "mode": "compare",
                "prompt": "compare products",
                "candidate_refs": ["B000000001"],
            },
        )
    assert response.status_code == 422
