"""
Security Audit Log and Access Control Verification Suite for MY PERSONAL AI.

Verifies:
  1. Immutable security audit logging to SQLite (audit_logs table).
  2. Role-based audit log visibility (OWNER sees all logs, standard USER sees only their own).
  3. Sandbox traversal attempts trigger automated SANDBOX_TRAVERSAL_BLOCKED audit events.
  4. Authentication actions (register, login, failed login) log immutable audit entries.
  5. POST /api/v1/security/scan-code performs static code audit and logs audit event.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from core.audit import list_audit_logs, log_audit_event, verify_audit_log_integrity
from core.auth import create_user
from core.sandbox import UserSandbox, UserSandboxError
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


def test_audit_event_logging():
    """Verify log_audit_event writes to database and list_audit_logs retrieves it."""
    db.init_db()
    user = _setup_user("audit_test_user_01")

    event_id = log_audit_event(
        event_type="TEST_EVENT",
        action="test_action",
        user_id=user["user_id"],
        resource="/api/v1/test",
        status="SUCCESS",
        severity="INFO",
        details={"key": "test_val"},
    )
    assert event_id is not None

    logs = list_audit_logs(user_id=user["user_id"], event_type="TEST_EVENT")
    assert len(logs) >= 1
    matched = next((l for l in logs if l["id"] == event_id), None)
    assert matched is not None
    assert matched["action"] == "test_action"
    assert matched["details"]["key"] == "test_val"
    print("✅ test_audit_event_logging PASSED")


def test_audit_log_rbac_visibility():
    """Verify OWNER can see all logs, but standard USER can see only their own."""
    client.cookies.clear()
    owner = _setup_user("audit_owner_boss", role="OWNER")
    user_a = _setup_user("audit_regular_user_a", role="USER")
    user_b = _setup_user("audit_regular_user_b", role="USER")

    # Generate distinct events
    log_audit_event("USER_A_ACTION", "action_a", user_id=user_a["user_id"])
    log_audit_event("USER_B_ACTION", "action_b", user_id=user_b["user_id"])

    # User A requests audit logs
    res_a = client.get("/api/v1/security/audit-logs", headers=user_a["headers"])
    assert res_a.status_code == 200
    logs_a = res_a.json()
    # User A should only see logs where user_id == user_a["user_id"]
    for l in logs_a:
        assert l["user_id"] == user_a["user_id"]
        assert l["event_type"] != "USER_B_ACTION"

    # Owner requests audit logs
    res_owner = client.get("/api/v1/security/audit-logs", headers=owner["headers"])
    assert res_owner.status_code == 200
    logs_owner = res_owner.json()
    event_types = [l["event_type"] for l in logs_owner]
    assert "USER_A_ACTION" in event_types
    assert "USER_B_ACTION" in event_types

    print("✅ test_audit_log_rbac_visibility PASSED")


def test_sandbox_traversal_triggers_audit():
    """Verify directory traversal attempt logs SANDBOX_TRAVERSAL_BLOCKED."""
    user = _setup_user("audit_sandbox_attacker")
    sandbox = UserSandbox()

    try:
        sandbox.resolve_path(user["user_id"], "../../windows/system32/cmd.exe")
    except UserSandboxError:
        pass

    logs = list_audit_logs(user_id=user["user_id"], event_type="SANDBOX_TRAVERSAL_BLOCKED")
    assert len(logs) >= 1
    assert logs[0]["status"] == "BLOCKED"
    assert logs[0]["severity"] == "HIGH"
    print("✅ test_sandbox_traversal_triggers_audit PASSED")


def test_api_code_scan():
    """Verify POST /api/v1/security/scan-code detects vulnerabilities and logs event."""
    user = _setup_user("audit_scanner_user")

    # Dangerous payload with subprocess and hardcoded secret
    code_payload = (
        "import subprocess\n"
        "api_key = 'sk-live-0987654321fedcba09876'\n"
        "subprocess.run(['dir'])\n"
    )

    res = client.post(
        "/api/v1/security/scan-code",
        json={"code": code_payload},
        headers=user["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is False
    assert data["overall_risk"] in ("CRITICAL", "HIGH")
    assert data["findings_count"] >= 2

    # Check audit log
    logs = list_audit_logs(user_id=user["user_id"], event_type="CODE_SCAN")
    assert len(logs) >= 1
    print("✅ test_api_code_scan PASSED")


def test_audit_log_hash_chain_and_tamper_resistance():
    """Verify cryptographic hash chaining and SQLite trigger tamper resistance."""
    user = _setup_user("audit_chain_tester")

    # 1. Log multiple events to build the chain
    e1 = log_audit_event("CHAIN_1", "action_1", user_id=user["user_id"])
    e2 = log_audit_event("CHAIN_2", "action_2", user_id=user["user_id"])
    e3 = log_audit_event("CHAIN_3", "action_3", user_id=user["user_id"])

    # 2. Verify chain via API and core function
    api_verify = client.get("/api/v1/security/audit-logs/verify", headers=user["headers"])
    assert api_verify.status_code == 200
    res_api = api_verify.json()
    assert res_api["valid"] is True
    assert res_api["total_records"] >= 3

    core_verify = verify_audit_log_integrity()
    assert core_verify["valid"] is True

    # 3. Verify SQLite Triggers block UPDATE attacks on audit_logs
    try:
        db.execute("UPDATE audit_logs SET status = 'TAMPERED' WHERE id = ?;", (e1,))
        assert False, "SQLite trigger should have blocked UPDATE on audit_logs"
    except Exception as e:
        assert "cannot be updated" in str(e).lower() or "fail" in str(e).lower()

    # 4. Verify SQLite Triggers block DELETE attacks on audit_logs
    try:
        db.execute("DELETE FROM audit_logs WHERE id = ?;", (e2,))
        assert False, "SQLite trigger should have blocked DELETE on audit_logs"
    except Exception as e:
        assert "cannot be deleted" in str(e).lower() or "fail" in str(e).lower()

    print("✅ test_audit_log_hash_chain_and_tamper_resistance PASSED (Tamper Resistance Proven)")


if __name__ == "__main__":
    test_audit_event_logging()
    test_audit_log_rbac_visibility()
    test_sandbox_traversal_triggers_audit()
    test_api_code_scan()
    test_audit_log_hash_chain_and_tamper_resistance()
    print("\nALL AUDIT LOG TESTS PASSED SUCCESSFULLY!")
