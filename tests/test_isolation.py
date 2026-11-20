"""
Isolation & Security Integration Test Suite for MY PERSONAL AI (Phase 4B).

Verifies:
  1. Unauthenticated requests to protected endpoints return HTTP 401 Unauthorized.
  2. Multi-user conversation isolation (User A cannot read, modify, or delete User B's conversations).
  3. Message-level isolation and IDOR prevention.
  4. Cascade deletion: Deleting a conversation purges its messages.
  5. Per-User File Sandbox boundaries: Traversal attacks (../) and escapes are blocked.
  6. Cross-user file isolation: User A cannot read or delete User B's files.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from core.auth import create_user
from core.sandbox import UserSandbox, UserSandboxError
from core.sessions import create_session
from data.db import db
from server import app

client = TestClient(app)


def _setup_test_user(username: str, role: str = "USER") -> dict:
    """Helper to create a user and return user info + auth headers."""
    db.init_db()
    # Check if user already exists in db
    row = db.fetch_one("SELECT id, username, role FROM users WHERE username = ?", (username,))
    if row:
        user_id = row["id"]
        role = row["role"]
    else:
        user = create_user(username=username, password="StrongPassword123!", role=role)
        user_id = user["id"]

    raw_token, session = create_session(user_id=user_id)
    headers = {"Authorization": f"Bearer {raw_token}"}
    return {
        "user_id": user_id,
        "username": username,
        "token": raw_token,
        "headers": headers,
    }


def test_unauthenticated_endpoints_return_401():
    """Verify that all protected endpoints reject requests without a valid session token."""
    client.cookies.clear()

    # Protected GET endpoints
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.get("/api/v1/conversations/nonexistent-id").status_code == 401
    assert client.get("/api/v1/conversations/nonexistent-id/messages").status_code == 401
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.get("/api/v1/tools").status_code == 401

    # Protected POST endpoints
    assert client.post("/api/v1/conversations", json={"title": "Test"}).status_code == 401
    assert client.post("/api/v1/conversations/dummy/messages", json={"role": "user", "content": "hi"}).status_code == 401
    assert client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401
    assert client.post("/api/v1/think", json={"message": "calculate 2+2"}).status_code == 401

    print("✅ test_unauthenticated_endpoints_return_401 PASSED")


def test_cross_user_conversation_isolation():
    """Verify that User A cannot read, update, or delete User B's conversations."""
    client.cookies.clear()
    user_a = _setup_test_user("iso_user_alpha")
    user_b = _setup_test_user("iso_user_beta")

    # User A creates a conversation
    res_a = client.post(
        "/api/v1/conversations",
        json={"title": "Alpha Confidential Project"},
        headers=user_a["headers"],
    )
    assert res_a.status_code == 201
    conv_a = res_a.json()
    conv_a_id = conv_a["id"]

    # User B lists conversations: conv_a_id MUST NOT be present
    res_b_list = client.get("/api/v1/conversations", headers=user_b["headers"])
    assert res_b_list.status_code == 200
    b_conv_ids = [c["id"] for c in res_b_list.json()]
    assert conv_a_id not in b_conv_ids

    # User B attempts to read User A's conversation directly (IDOR check)
    res_b_get = client.get(f"/api/v1/conversations/{conv_a_id}", headers=user_b["headers"])
    assert res_b_get.status_code == 404

    # User B attempts to rename User A's conversation
    res_b_patch = client.patch(
        f"/api/v1/conversations/{conv_a_id}",
        json={"title": "Hijacked Title"},
        headers=user_b["headers"],
    )
    assert res_b_patch.status_code == 404

    # User B attempts to read messages from User A's conversation
    res_b_msgs = client.get(
        f"/api/v1/conversations/{conv_a_id}/messages",
        headers=user_b["headers"],
    )
    assert res_b_msgs.status_code == 404

    # User B attempts to post a message into User A's conversation
    res_b_post_msg = client.post(
        f"/api/v1/conversations/{conv_a_id}/messages",
        json={"role": "user", "content": "Unauthorized injection"},
        headers=user_b["headers"],
    )
    assert res_b_post_msg.status_code == 404

    # User B attempts to delete User A's conversation
    res_b_delete = client.delete(f"/api/v1/conversations/{conv_a_id}", headers=user_b["headers"])
    assert res_b_delete.status_code == 404

    # Verify User A still owns and can access the conversation untouched
    res_a_verify = client.get(f"/api/v1/conversations/{conv_a_id}", headers=user_a["headers"])
    assert res_a_verify.status_code == 200
    assert res_a_verify.json()["title"] == "Alpha Confidential Project"

    print("✅ test_cross_user_conversation_isolation PASSED")


def test_conversation_cascade_delete():
    """Verify that deleting a conversation properly cleans up all associated messages."""
    client.cookies.clear()
    user = _setup_test_user("iso_cascade_user")

    # Create conversation
    res_conv = client.post(
        "/api/v1/conversations",
        json={"title": "Temporary Chat"},
        headers=user["headers"],
    )
    conv_id = res_conv.json()["id"]

    # Add messages
    res_msg1 = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Message 1 to be deleted"},
        headers=user["headers"],
    )
    assert res_msg1.status_code == 201

    res_msg2 = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "assistant", "content": "Response 1 to be deleted"},
        headers=user["headers"],
    )
    assert res_msg2.status_code == 201

    # Verify messages exist in DB
    db_msgs_before = db.fetch_all(
        "SELECT id FROM messages WHERE conversation_id = ?",
        (conv_id,),
    )
    assert len(db_msgs_before) == 2

    # Delete the conversation
    res_del = client.delete(f"/api/v1/conversations/{conv_id}", headers=user["headers"])
    assert res_del.status_code == 200

    # Verify conversation is gone from API
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=user["headers"]).status_code == 404

    # Verify messages were cascade deleted from the database
    db_msgs_after = db.fetch_all(
        "SELECT id FROM messages WHERE conversation_id = ?",
        (conv_id,),
    )
    assert len(db_msgs_after) == 0

    print("✅ test_conversation_cascade_delete PASSED")


def test_user_file_sandbox_isolation_and_traversal_prevention():
    """Verify that UserSandbox enforces directory confinement and stops traversal attacks."""
    temp_dir = tempfile.mkdtemp(prefix="ai_sandbox_test_")
    try:
        sandbox = UserSandbox(base_dir=temp_dir)
        user_1_id = "user-uuid-111"
        user_2_id = "user-uuid-222"

        # 1. Write file in user 1's sandbox
        p1 = sandbox.write_file(user_1_id, "workspace/secret_plan.txt", "Top secret agent plan")
        assert p1.exists()
        assert sandbox.read_file(user_1_id, "workspace/secret_plan.txt") == "Top secret agent plan"

        # 2. Verify User 2 cannot access User 1's file through sandbox
        try:
            sandbox.read_file(user_2_id, "workspace/secret_plan.txt")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass

        # 3. Path traversal attack attempts by User 1
        for attack_path in [
            "../user-uuid-222/workspace/secret_plan.txt",
            "../../system32/cmd.exe",
            "..\\..\\sensitive_file.txt",
        ]:
            try:
                sandbox.resolve_path(user_1_id, attack_path)
                assert False, f"Should have blocked traversal for {attack_path}"
            except UserSandboxError:
                pass

        # 4. Malicious user_id escape attempt
        for malicious_id in ["../../escaped_user", "   ", ""]:
            try:
                sandbox.get_user_root(malicious_id)
                assert False, f"Should have blocked malicious user_id: {malicious_id}"
            except UserSandboxError:
                pass

        # 5. File deletion isolation
        assert sandbox.delete_file(user_1_id, "workspace/secret_plan.txt") is True
        assert sandbox.delete_file(user_1_id, "workspace/secret_plan.txt") is False

        print("✅ test_user_file_sandbox_isolation_and_traversal_prevention PASSED")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_unauthenticated_endpoints_return_401()
    test_cross_user_conversation_isolation()
    test_conversation_cascade_delete()
    test_user_file_sandbox_isolation_and_traversal_prevention()
    print("\nALL ISOLATION TESTS PASSED SUCCESSFULLY!")
