import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server import app
from data.db import db
from core.auth import create_user
from core.sessions import create_session

client = TestClient(app)

# Authenticate test client for protected endpoints
db.init_db()
_test_user = db.fetch_one("SELECT id FROM users WHERE username = ?", ("phase2_test_user",))
if not _test_user:
    _test_user = create_user(username="phase2_test_user", password="StrongPassword123!", role="USER")
_raw_token, _ = create_session(user_id=_test_user["id"])
client.headers.update({"Authorization": f"Bearer {_raw_token}"})


def test_ui_served():
    """Verify that the local web chat UI is served at root."""
    response = client.get("/")
    assert response.status_code == 200
    assert "MY PERSONAL AI" in response.text
    assert "100% Offline" in response.text
    print("✅ test_ui_served PASSED")


def test_health_endpoint():
    """Verify health check with active local Ollama integration."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["router"]["local_engine_online"] is True
    assert data["router"]["cloud_enabled"] is False  # Cloud must remain disabled
    assert "RTX 3050" in data["hardware"]["gpu"]
    print("✅ test_health_endpoint PASSED")


def test_models_list():
    """Verify that local models endpoint detects qwen2.5-coder:3b."""
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert data["router_mode"] == "local_only"
    model_names = [m["name"] for m in data["models"]]
    assert any("qwen2.5-coder:3b" in name for name in model_names)
    print(f"✅ test_models_list PASSED (Found: {model_names})")


def test_chat_non_streaming():
    """Verify actual local inference with non-streaming chat."""
    payload = {
        "messages": [
            {"role": "user", "content": "Write exactly one line of Python code: print('PHASE_2_TEST_OK')"}
        ],
        "model": "qwen2.5-coder:3b",
        "stream": False,
        "temperature": 0.1
    }
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "assistant"
    assert "PHASE_2_TEST_OK" in data["content"] or "print" in data["content"]
    assert data["provider"] == "ollama_local"
    assert data["eval_count"] > 0
    assert data["latency_sec"] > 0
    print(f"✅ test_chat_non_streaming PASSED (Speed: {data['tokens_per_sec']} tok/s, Latency: {data['latency_sec']}s)")


def test_chat_streaming():
    """Verify streaming token delivery via Server-Sent Events."""
    payload = {
        "messages": [
            {"role": "user", "content": "Count from 1 to 3. Format: 1, 2, 3."}
        ],
        "model": "qwen2.5-coder:3b",
        "stream": True,
        "temperature": 0.1
    }
    with client.stream("POST", "/api/v1/chat", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        
        chunks = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])

        assert len(chunks) > 0
        assert chunks[-1] == "[DONE]"
        print(f"✅ test_chat_streaming PASSED ({len(chunks)} stream chunks received, properly terminated with [DONE])")


def test_error_handling_empty_messages():
    """Verify 400 Bad Request on empty messages."""
    response = client.post("/api/v1/chat", json={"messages": []})
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
    print("✅ test_error_handling_empty_messages PASSED")


def test_error_handling_unknown_model():
    """Verify 404 Not Found when requesting uninstalled model."""
    response = client.post("/api/v1/chat", json={
        "messages": [{"role": "user", "content": "hello"}],
        "model": "non_existent_fake_model:99b",
        "stream": False
    })
    assert response.status_code == 404
    assert "not installed" in response.json()["detail"].lower()
    print("✅ test_error_handling_unknown_model PASSED")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("RUNNING PHASE 2 COMPREHENSIVE VERIFICATION SUITE")
    print("="*60)
    test_ui_served()
    test_health_endpoint()
    test_models_list()
    test_chat_non_streaming()
    test_chat_streaming()
    test_error_handling_empty_messages()
    test_error_handling_unknown_model()
    print("="*60)
    print("🎉 ALL 7 PHASE 2 TESTS PASSED WITH 100% SUCCESS!")
    print("="*60)
