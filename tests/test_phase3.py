"""
Comprehensive Phase 3 Integration Test Suite for MY PERSONAL AI.

Verifies:
  1. GET /api/v1/tools (schema, count, permission levels)
  2. GET /health (brain orchestrator online, 5 tools active)
  3. POST /api/v1/think (synchronous autonomous calculation)
  4. POST /api/v1/think (synchronous system inspection)
  5. POST /api/v1/think (real-time streaming progress events)
  6. POST /api/v1/think (input validation and error handling)
  7. Regression check for Phase 1 & 2 endpoints
"""

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_tools_endpoint():
    """Verify GET /api/v1/tools lists all 5 sandboxed tools."""
    res = client.get("/api/v1/tools")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 5

    tool_names = [t["name"] for t in data["tools"]]
    assert "calculator" in tool_names
    assert "file_reader" in tool_names
    assert "code_analyzer" in tool_names
    assert "system_info" in tool_names
    assert "datetime" in tool_names
    print("✅ test_tools_endpoint PASSED (Found all 5 tools)")


def test_health_with_brain():
    """Verify GET /health includes brain & orchestrator metrics."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "brain" in data
    assert data["brain"]["orchestrator_online"] is True
    assert data["brain"]["registered_tools"] == 5
    assert data["version"] == "0.3.0"
    print("✅ test_health_with_brain PASSED")


def test_think_calculation():
    """Verify autonomous calculation task execution."""
    res = client.post(
        "/api/v1/think",
        json={"message": "Calculate sqrt(144) * 5 + 40", "stream": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert data["confidence"] >= 0.5
    print(f"✅ test_think_calculation PASSED (Confidence: {data['confidence']})")


def test_think_system_info():
    """Verify autonomous system inspection task execution."""
    res = client.post(
        "/api/v1/think",
        json={"message": "Show me the hardware specifications and GPU details", "stream": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "RTX 3050" in data["answer"] or "GPU" in data["answer"] or "NVIDIA" in data["answer"]
    print("✅ test_think_system_info PASSED")


def test_think_streaming():
    """Verify streaming progress events during autonomous execution."""
    res = client.post(
        "/api/v1/think",
        json={"message": "What is today's date?", "stream": True},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = []
    for line in res.iter_lines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload != "[DONE]":
                events.append(json.loads(payload))

    assert len(events) >= 2
    phases = [e.get("phase") for e in events]
    assert "reasoning" in phases
    assert "complete" in phases
    print(f"✅ test_think_streaming PASSED ({len(events)} progress events received)")


def test_think_validation_errors():
    """Verify error handling on invalid / empty inputs."""
    # Empty message
    res = client.post("/api/v1/think", json={"message": "", "stream": False})
    assert res.status_code == 400

    # Missing message
    res = client.post("/api/v1/think", json={"stream": False})
    assert res.status_code == 422
    print("✅ test_think_validation_errors PASSED")


def test_phase1_phase2_regressions():
    """Verify legacy endpoints still work seamlessly."""
    # Root UI
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert "MY PERSONAL AI" in r_root.text

    # System Info
    r_sys = client.get("/api/v1/system/info")
    assert r_sys.status_code == 200
    assert "gpu" in r_sys.json()

    # Models list
    r_mod = client.get("/api/v1/models")
    assert r_mod.status_code == 200
    assert r_mod.json()["count"] >= 1
    print("✅ test_phase1_phase2_regressions PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING PHASE 3 COMPREHENSIVE INTEGRATION SUITE")
    print("=" * 60)
    test_tools_endpoint()
    test_health_with_brain()
    test_think_calculation()
    test_think_system_info()
    test_think_streaming()
    test_think_validation_errors()
    test_phase1_phase2_regressions()
    print("=" * 60)
    print("🎉 ALL 7 PHASE 3 INTEGRATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 60)
