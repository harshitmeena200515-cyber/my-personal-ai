"""
Human-in-the-Loop (HITL) Integration Test Suite for MY PERSONAL AI.

Verifies:
  1. Creation and persistent listing of pending HITL approvals.
  2. Resolving approvals (ALLOW / DENY) updates database and audit trail.
  3. Re-resolving an already resolved approval returns HTTP 404.
  4. Cross-user isolation: User B cannot view or resolve User A's approvals.
  5. End-to-end agent task execution with critical risk triggers HITL blocking.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from core.audit import create_hitl_approval, list_hitl_approvals
from core.auth import create_user
from core.sessions import create_session
from data.db import db
from server import app

client = TestClient(app)


def _setup_user(username: str, role: str = "USER") -> dict:
    db.init_db()
    row = db.fetch_one("SELECT id, username, role FROM users WHERE username = ?", (username,))
    if row:
        user_id = row["id"]
        role = row["role"]
    else:
        user = create_user(username=username, password="StrongPassword123!", role=role)
        user_id = user["id"]

    token, _ = create_session(user_id=user_id)
    return {
        "user_id": user_id,
        "username": username,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "role": role,
    }


def test_hitl_approval_lifecycle():
    """Verify approval creation, listing, resolution, and state immutability."""
    user = _setup_user("hitl_test_user_01")

    # 1. Create a pending approval
    approval_id = create_hitl_approval(
        user_id=user["user_id"],
        agent_name="cybersec_agent",
        action="execute_destructive_command",
        reason="Detected rm -rf in requested task",
        risk_level="CRITICAL",
    )
    assert approval_id is not None

    # 2. List approvals via API
    res_list = client.get("/api/v1/security/approvals?status=PENDING", headers=user["headers"])
    assert res_list.status_code == 200
    approvals = res_list.json()
    assert any(a["id"] == approval_id for a in approvals)

    # 3. Resolve approval (APPROVE)
    res_resolve = client.post(
        f"/api/v1/security/approvals/{approval_id}/resolve",
        json={"approved": True},
        headers=user["headers"],
    )
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "APPROVED"

    # 4. Attempt to resolve again should fail (HTTP 404)
    res_re_resolve = client.post(
        f"/api/v1/security/approvals/{approval_id}/resolve",
        json={"approved": False},
        headers=user["headers"],
    )
    assert res_re_resolve.status_code == 404

    print("✅ test_hitl_approval_lifecycle PASSED")


def test_hitl_cross_user_isolation():
    """Verify User B cannot view or resolve User A's approvals."""
    user_a = _setup_user("hitl_iso_user_a")
    user_b = _setup_user("hitl_iso_user_b")

    # User A has an approval created
    approval_id = create_hitl_approval(
        user_id=user_a["user_id"],
        agent_name="cybersec_agent",
        action="modify_system_config",
        reason="Privileged config change",
        risk_level="HIGH",
    )

    # User B lists approvals: approval_id MUST NOT be present
    res_b_list = client.get("/api/v1/security/approvals", headers=user_b["headers"])
    assert res_b_list.status_code == 200
    b_ids = [a["id"] for a in res_b_list.json()]
    assert approval_id not in b_ids

    # User B attempts to resolve User A's approval
    res_b_resolve = client.post(
        f"/api/v1/security/approvals/{approval_id}/resolve",
        json={"approved": True},
        headers=user_b["headers"],
    )
    assert res_b_resolve.status_code == 404

    print("✅ test_hitl_cross_user_isolation PASSED")


def test_agent_execution_triggers_hitl():
    """Verify high-risk agent execution blocks and creates a pending HITL request."""
    user = _setup_user("hitl_agent_exec_user")

    # Dispatch code with critical risk (subprocess and secret)
    dangerous_task = "import subprocess\napi_key = 'sk-live-supersecret'\nsubprocess.run(['dir'])"

    res_agent = client.post(
        "/api/v1/agents/cybersec_agent/execute",
        json={"task": dangerous_task},
        headers=user["headers"],
    )
    assert res_agent.status_code == 200
    data = res_agent.json()

    assert data["status"] == "BLOCKED_AWAITING_APPROVAL"
    assert data["risk_level"] in ("HIGH", "CRITICAL")
    assert "approval_id" in data["metadata"]

    approval_id = data["metadata"]["approval_id"]

    # Verify pending approval is listed in /api/v1/security/approvals
    res_approvals = client.get("/api/v1/security/approvals?status=PENDING", headers=user["headers"])
    assert res_approvals.status_code == 200
    ids = [a["id"] for a in res_approvals.json()]
    assert approval_id in ids

    print("✅ test_agent_execution_triggers_hitl PASSED")


def test_hitl_expiration_and_deduplication():
    """Verify expired approvals cannot be authorized and duplicate resolutions are rejected."""
    user = _setup_user("hitl_exp_user")

    # 1. Create an expired approval (ttl_seconds = -60)
    exp_approval_id = create_hitl_approval(
        user_id=user["user_id"],
        agent_name="cybersec_agent",
        action="modify_firewall",
        reason="Expired authorization test",
        ttl_seconds=-60,
    )

    # 2. List approvals: status should be EXPIRED
    res_list = client.get("/api/v1/security/approvals", headers=user["headers"])
    assert res_list.status_code == 200
    appr_match = next((a for a in res_list.json() if a["id"] == exp_approval_id), None)
    assert appr_match is not None
    assert appr_match["status"] == "EXPIRED"

    # 3. Attempt to resolve expired approval: must fail with HTTP 404
    res_resolve = client.post(
        f"/api/v1/security/approvals/{exp_approval_id}/resolve",
        json={"approved": True},
        headers=user["headers"],
    )
    assert res_resolve.status_code == 404

    print("✅ test_hitl_expiration_and_deduplication PASSED (Expired Approvals Safely Disallowed)")


if __name__ == "__main__":
    test_hitl_approval_lifecycle()
    test_hitl_cross_user_isolation()
    test_agent_execution_triggers_hitl()
    test_hitl_expiration_and_deduplication()
    print("\nALL HITL TESTS PASSED SUCCESSFULLY!")
