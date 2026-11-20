"""
MY PERSONAL AI — PHASE 4 FINAL ACCEPTANCE & PRODUCTION READINESS AUDIT SUITE
Tests real workflows, multi-user isolation, tamper-resistant audit logs,
HITL lifecycle, agent dispatch, and hardware metrics.
"""

import asyncio
import os
import sys
import time
import json
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from server import app
from data.db import DatabaseManager, db
from core.auth import create_user, authenticate_user
from core.sessions import create_session, validate_session, revoke_session
from core.sandbox import UserSandbox
from core.audit import log_audit_event, create_hitl_approval, resolve_hitl_approval, list_hitl_approvals, verify_audit_log_integrity
from agents import (
    AgentStatus,
    AgentRegistry,
    CodingAgent,
    ResearchAgent,
    CybersecurityAgent,
    RiskLevel,
    SharedContext,
    agent_registry,
)

client = TestClient(app)

def test_acceptance_end_to_end_suite():
    print("\n" + "=" * 70)
    print("STARTING COMPREHENSIVE PHASE 4 FINAL ACCEPTANCE AUDIT")
    print("=" * 70)

    # 1. Database & Migrations Verification
    db_mgr = DatabaseManager()
    with db_mgr.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.upper() == "WAL", f"Expected WAL mode, got {journal_mode}"

        cursor.execute("PRAGMA foreign_keys;")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1, "Foreign keys not enforced"

        # Check triggers
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger';")
        triggers = [row[0] for row in cursor.fetchall()]
        assert "prevent_audit_log_update" in triggers, "Missing trigger prevent_audit_log_update"
        assert "prevent_audit_log_delete" in triggers, "Missing trigger prevent_audit_log_delete"
    print("  [1/8] Database Foundation & SQLite Triggers: VERIFIED (WAL, FK, Triggers)")

    # 2. Multi-User Creation & Authentication
    ts = int(time.time() * 1000) % 1000000
    owner_username = f"owneraudit{ts}"
    user_a_username = f"usera{ts}"
    user_b_username = f"userb{ts}"
    password = "AuditPassword123!"

    # 2a. Provision Owner via setup function (simulating setup_owner.py)
    owner = create_user(owner_username, password, role="OWNER")
    assert owner["role"] == "OWNER", "Owner creation failed to set OWNER role"

    # 2b. Register User A and User B via Public API
    # Attempt privilege escalation by passing role: OWNER in public register
    res_a = client.post("/api/v1/auth/register", json={"username": user_a_username, "password": password, "role": "OWNER"})
    assert res_a.status_code == 201
    user_a = res_a.json()["user"]
    assert user_a["role"] == "USER", "Security failure: public registration escalated to OWNER!"

    res_b = client.post("/api/v1/auth/register", json={"username": user_b_username, "password": password})
    assert res_b.status_code == 201
    user_b = res_b.json()["user"]
    assert user_b["role"] == "USER"
    print("  [2/8] User Provisioning & Anti-Escalation: VERIFIED")

    # 3. Session Persistence & Token Revocation
    # Login Owner
    login_owner = client.post("/api/v1/auth/login", json={"username": owner_username, "password": password})
    assert login_owner.status_code == 200
    owner_token = login_owner.json()["token"]

    # Login User A
    login_a = client.post("/api/v1/auth/login", json={"username": user_a_username, "password": password})
    assert login_a.status_code == 200
    token_a = login_a.json()["token"]

    # Login User B
    login_b = client.post("/api/v1/auth/login", json={"username": user_b_username, "password": password})
    assert login_b.status_code == 200
    token_b = login_b.json()["token"]

    # Test Session Revocation
    logout_b = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token_b}"})
    assert logout_b.status_code == 200
    # Trying to use revoked token should be 401
    chk_b = client.get("/api/v1/conversations", headers={"Authorization": f"Bearer {token_b}"})
    assert chk_b.status_code == 401, "Revoked session was not rejected"
    print("  [3/8] Session Lifecycle & Revocation: VERIFIED")

    # 4. Multi-User Isolation & Role Protection
    # 4a. Normal User A cannot access Owner-only endpoint (/api/v1/auth/users)
    res_users_a = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {token_a}"})
    assert res_users_a.status_code == 403, "Normal user accessed owner-only endpoint"

    # 4b. Owner CAN access Owner-only endpoint
    res_users_owner = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_users_owner.status_code == 200, "Owner was forbidden from admin users endpoint"
    all_users = res_users_owner.json()
    assert len(all_users) >= 3

    # 4c. Conversation Isolation (IDOR Defense)
    # User A creates a private conversation
    conv_a = client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "User A Financial Secret"}
    ).json()
    conv_a_id = conv_a["id"]

    # Login fresh User B for IDOR test
    login_b_fresh = client.post("/api/v1/auth/login", json={"username": user_b_username, "password": password})
    fresh_token_b = login_b_fresh.json()["token"]

    res_idor = client.get(
        f"/api/v1/conversations/{conv_a_id}",
        headers={"Authorization": f"Bearer {fresh_token_b}"}
    )
    assert res_idor.status_code == 404, "IDOR Vulnerability: User B accessed User A's conversation!"

    # 4d. Sandbox Isolation & Path Traversal Prevention
    from core.sandbox import user_sandbox, UserSandboxError
    root_a = user_sandbox.get_user_root(user_a["id"])
    root_b = user_sandbox.get_user_root(user_b["id"])
    assert root_a != root_b

    file_a = user_sandbox.write_file(user_a["id"], "workspace/confidential.txt", "User A Secret Data")
    assert file_a.exists()

    # User B cannot read User A's file
    blocked_read = False
    try:
        user_sandbox.read_file(user_b["id"], f"../../{user_a['id']}/workspace/confidential.txt")
    except UserSandboxError:
        blocked_read = True
    assert blocked_read, "User B was able to read User A's file"

    # Path traversal attack detection
    traversal_blocked_1 = False
    try:
        user_sandbox.write_file(user_a["id"], "../../system_hack.txt", "exploit")
    except UserSandboxError:
        traversal_blocked_1 = True
    assert traversal_blocked_1, "Path traversal in write_file was not blocked"

    traversal_blocked_2 = False
    try:
        user_sandbox.get_user_root("invalid/../user")
    except UserSandboxError:
        traversal_blocked_2 = True
    assert traversal_blocked_2, "Path traversal in UserSandbox was not blocked"
    print("  [4/8] Multi-User Isolation & Path Traversal Defense: VERIFIED")

    # 5. Cryptographic Hash-Chained Audit Logs & Tamper Resistance
    # Verify hash integrity
    integrity = verify_audit_log_integrity()
    assert integrity["valid"] is True, f"Audit log integrity check failed: {integrity}"

    # Verify SQLite trigger blocks manual UPDATE
    with db_mgr.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM audit_logs LIMIT 1;")
        row = cursor.fetchone()
        if row:
            audit_id = row[0]
            update_blocked = False
            try:
                cursor.execute("UPDATE audit_logs SET action = 'TAMPERED' WHERE id = ?;", (audit_id,))
            except sqlite3.IntegrityError:
                update_blocked = True
            assert update_blocked, "Trigger failed to block UPDATE on audit_logs"

            # Verify SQLite trigger blocks manual DELETE
            delete_blocked = False
            try:
                cursor.execute("DELETE FROM audit_logs WHERE id = ?;", (audit_id,))
            except sqlite3.IntegrityError:
                delete_blocked = True
            assert delete_blocked, "Trigger failed to block DELETE on audit_logs"
    print("  [5/8] Tamper-Resistant Cryptographic Audit Log: VERIFIED")

    # 6. Human-In-The-Loop (HITL) Security Lifecycle
    # 6a. Create HITL Approval for User A
    approval_id = create_hitl_approval(
        user_id=user_a["id"],
        agent_name="cybersec_agent",
        action="execute_system_command",
        reason="Execution of shell command requires explicit human authorization",
        risk_level="CRITICAL",
        ttl_seconds=3600
    )
    assert approval_id is not None

    # 6b. User B cannot resolve User A's HITL request
    res_cross_resolve = client.post(
        f"/api/v1/security/approvals/{approval_id}/resolve",
        headers={"Authorization": f"Bearer {fresh_token_b}"},
        json={"approved": True}
    )
    assert res_cross_resolve.status_code == 404, "User B was able to resolve User A's HITL request"

    # 6c. User A resolves own request
    res_a_resolve = client.post(
        f"/api/v1/security/approvals/{approval_id}/resolve",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"approved": True}
    )
    assert res_a_resolve.status_code == 200
    assert res_a_resolve.json()["status"] == "APPROVED"

    # 6d. Deduplication: cannot resolve already-resolved request
    res_a_dup = client.post(
        f"/api/v1/security/approvals/{approval_id}/resolve",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"approved": False}
    )
    assert res_a_dup.status_code == 404, "Allowed duplicate resolution of HITL request"

    # 6e. Expiration check
    expired_id = create_hitl_approval(
        user_id=user_a["id"],
        agent_name="cybersec_agent",
        action="delete_database",
        reason="Test expired approval",
        risk_level="HIGH",
        ttl_seconds=-60  # already expired
    )
    res_expired_resolve = client.post(
        f"/api/v1/security/approvals/{expired_id}/resolve",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"approved": True}
    )
    assert res_expired_resolve.status_code == 404, "Expired approval was resolved"
    print("  [6/8] HITL Authorization, Expiration & Deduplication: VERIFIED")

    # 7. Multi-Agent Intelligence & Zero-Trust HITL Triggering
    assert agent_registry.get("coding_agent") is not None
    assert agent_registry.get("research_agent") is not None
    assert agent_registry.get("cybersec_agent") is not None

    # CodingAgent executes AST syntax validation
    coding_agent_inst = agent_registry.get("coding_agent")
    ast_check = coding_agent_inst.validate_python_syntax("def add(a, b):\n    return a + b\n")
    assert ast_check["valid"] is True
    assert ast_check["node_count"] > 0

    # Intent routing check
    routed_code = agent_registry.route_task("code_generation", "Write a python function")
    assert routed_code.name == "coding_agent"

    routed_sec = agent_registry.route_task("general", "Audit security vulnerabilities")
    assert routed_sec.name == "cybersec_agent"

    # CybersecurityAgent intercepts dangerous command and triggers HITL
    cybersec_agent_inst = agent_registry.get("cybersec_agent")
    dangerous_code = "import subprocess\nsubprocess.run(['rm', '-rf', '/'])\n"
    scan_res = cybersec_agent_inst.audit_code_security(dangerous_code)
    assert scan_res["passed"] is False
    assert scan_res["overall_risk"] == RiskLevel.HIGH

    ctx = SharedContext(user_id=user_a["id"])
    ctx.set("last_generated_code", dangerous_code)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(cybersec_agent_inst.execute("Audit latest generated code", ctx))
    loop.close()

    assert result.status == AgentStatus.BLOCKED_AWAITING_APPROVAL
    assert len(ctx.get_pending_approvals()) == 1
    print("  [7/8] Multi-Agent Intelligence & Zero-Trust Defense: VERIFIED")

    # 8. Local Inference & Performance Benchmark
    start_bench = time.perf_counter()
    chat_res = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "messages": [{"role": "user", "content": "Respond with the single word: READY"}],
            "stream": False
        }
    )
    bench_latency = time.perf_counter() - start_bench
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "content" in chat_data
    reply_content = chat_data["content"]
    tps = chat_data.get("tokens_per_sec", 0.0)
    eval_count = chat_data.get("eval_count", 0)
    print(f"  [8/8] Local Inference (Ollama {chat_data['model']}): {bench_latency:.2f}s latency | {tps:.1f} tokens/sec ({eval_count} tokens) | Response: '{reply_content.strip()}'")

    print("\n" + "=" * 70)
    print("ALL 8 ACCEPTANCE CATEGORIES COMPLETED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    test_acceptance_end_to_end_suite()
