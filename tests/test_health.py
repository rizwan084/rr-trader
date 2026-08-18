from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get(
        "/api/health"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["status"] == "healthy"


def test_root_endpoint() -> None:
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["app"] == "RR Trader"
    assert data["status"] == "online"


def test_markets_endpoint() -> None:
    response = client.get(
        "/api/markets"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True

    market_ids = {
        item["id"]
        for item in data["markets"]
    }

    assert "spot" in market_ids
    assert "futures" in market_ids
