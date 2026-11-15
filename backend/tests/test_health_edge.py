import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_health_rejects_non_get(method: str) -> None:
    assert client.request(method, "/api/health").status_code == 405


def test_unknown_route_404() -> None:
    assert client.get("/api/nope").status_code == 404


def test_health_is_json_exact_and_ignores_query() -> None:
    r = client.get("/api/health?x=1")
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"status": "ok"}


def test_trailing_slash_redirects_to_health() -> None:
    r = client.get("/api/health/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].endswith("/api/health")
