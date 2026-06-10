from __future__ import annotations

from fastapi.testclient import TestClient

from memory_gateway.api.main import app
from memory_gateway.db import init_db


def test_healthz():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_requires_api_key():
    client = TestClient(app)
    response = client.post("/v1/memories/search", json={"query": "hello"})
    assert response.status_code == 401


def test_desktop_origin_cors_preflight():
    client = TestClient(app)
    response = client.options(
        "/v1/captures/analyze",
        headers={
            "Origin": "http://127.0.0.1:1420",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()
