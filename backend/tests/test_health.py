from fastapi.testclient import TestClient

from app.db import make_engine
from app.main import create_app


def test_health_ok() -> None:
    response = TestClient(create_app(engine=make_engine("sqlite://"))).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] in {"fake", "gemini"}
