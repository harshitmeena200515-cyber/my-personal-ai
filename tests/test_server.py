import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "MY PERSONAL AI" in response.text


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_system_info():
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = response.json()
    assert "gpu" in data
    assert "ram" in data


def test_models_status():
    response = client.get("/api/v1/models/status")
    assert response.status_code == 200
    data = response.json()
    assert "router_mode" in data
    assert "default_local" in data


if __name__ == "__main__":
    test_root()
    test_health()
    test_system_info()
    test_models_status()
    print("ALL TESTS PASSED SUCCESSFULLY!")
