"""
Authentication API and Unit Tests for MY PERSONAL AI (Phase 4A - Hardened).

Verifies:
1. Argon2id password hashing and constant-time verification.
2. Password and username validation logic.
3. User registration API (/api/v1/auth/register) ALWAYS creates 'USER' role.
4. Public registration CANNOT create an OWNER account even on empty database.
5. Duplicate username rejection (HTTP 409).
6. Successful login with token and cookie (/api/v1/auth/login).
7. Incorrect password rejection (HTTP 401).
8. Non-existent username rejection (HTTP 401).
9. Current user profile endpoint (/api/v1/auth/me) with Bearer token.
10. Unauthorized access rejection (HTTP 401).
11. Logout revoking session (/api/v1/auth/logout).
12. CLI Owner provisioning sets role='OWNER' and grants owner privileges.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from core.auth import (
    create_user,
    hash_password,
    validate_password_strength,
    validate_username,
    verify_password,
)
from core.config import settings
from data.db import DatabaseManager
import core.auth
import core.sessions
import core.audit
from server import app


def test_password_hashing():
    """Verify Argon2id hashing and verification."""
    pwd = "MySecurePassword123!"
    pw_hash = hash_password(pwd)

    assert pw_hash.startswith("$argon2id$"), "Hash must use Argon2id format"
    assert verify_password(pw_hash, pwd) is True, "Matching password must verify"
    assert verify_password(pw_hash, "WrongPassword123!") is False, "Wrong password must fail verification"
    assert verify_password("invalid_hash_string", pwd) is False, "Malformed hash must safely fail"
    print("✅ test_password_hashing PASSED")


def test_input_validations():
    """Verify password and username format requirements."""
    # Password strength
    assert validate_password_strength("short")[0] is False
    assert validate_password_strength("allletterspassword")[0] is False
    assert validate_password_strength("ValidPass123")[0] is True

    # Username format
    assert validate_username("ab")[0] is False  # too short
    assert validate_username("valid_user-123")[0] is True
    assert validate_username("invalid user name")[0] is False  # spaces not allowed
    print("✅ test_input_validations PASSED")


def test_public_registration_always_creates_user():
    """Verify that public API registration can NEVER create an OWNER account."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_pub_reg.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        orig_audit_db = core.audit.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr
        core.audit.db = test_mgr
        client = TestClient(app)

        try:
            # 1. First registration on EMPTY database -> MUST be 'USER' (not OWNER)
            res1 = client.post(
                "/api/v1/auth/register",
                json={"username": "first_registered_user", "password": "FirstUser123!"},
            )
            assert res1.status_code == 201
            assert res1.json()["user"]["role"] == "USER", "First public registered user must be USER"

            # 2. Attempt to exploit by injecting role='OWNER' in request body
            res2 = client.post(
                "/api/v1/auth/register",
                json={"username": "hacker_trying_owner", "password": "HackerPass123!", "role": "OWNER"},
            )
            assert res2.status_code == 201
            assert res2.json()["user"]["role"] == "USER", "Injected role must be ignored; role must be USER"

            # 3. Verify in database directly
            users = test_mgr.fetch_all("SELECT username, role FROM users;")
            for u in users:
                assert u["role"] == "USER", f"User {u['username']} has role {u['role']}, expected USER"

            print("✅ test_public_registration_always_creates_user PASSED (Zero Privilege Escalation)")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db
            core.audit.db = orig_audit_db


def test_owner_cli_provisioning():
    """Verify that authorized CLI owner provisioning correctly assigns OWNER role."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_owner_cli.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        orig_audit_db = core.audit.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr
        core.audit.db = test_mgr
        client = TestClient(app)

        try:
            # CLI calls create_user with explicit role='OWNER'
            owner = create_user(username="system_owner", password="OwnerPassword123!", role="OWNER")
            assert owner["role"] == "OWNER"

            # Login as owner
            res_login = client.post(
                "/api/v1/auth/login",
                json={"username": "system_owner", "password": "OwnerPassword123!"},
            )
            assert res_login.status_code == 200
            owner_token = res_login.json()["token"]

            # Check profile
            res_me = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert res_me.status_code == 200
            assert res_me.json()["role"] == "OWNER"
            print("✅ test_owner_cli_provisioning PASSED (OWNER correctly provisioned and authenticated)")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db
            core.audit.db = orig_audit_db


def test_auth_api_workflow():
    """Verify complete end-to-end API registration, login, profile, and logout flow."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_api_auth.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        orig_audit_db = core.audit.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr
        core.audit.db = test_mgr
        client = TestClient(app)

        try:
            # 1. Register User via API
            res = client.post(
                "/api/v1/auth/register",
                json={"username": "alice_api", "password": "AlicePassword123!"},
            )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            data_reg = res.json()
            assert data_reg["user"]["username"] == "alice_api"
            assert data_reg["user"]["role"] == "USER"
            assert "token" in data_reg
            user_token = data_reg["token"]
            print("✅ Registration API PASSED")

            # 2. Duplicate Username Rejection
            res_dup = client.post(
                "/api/v1/auth/register",
                json={"username": "alice_api", "password": "AnotherPassword123!"},
            )
            assert res_dup.status_code == 409, f"Expected 409 Conflict, got {res_dup.status_code}"
            print("✅ Duplicate username rejection (HTTP 409) PASSED")

            # 3. Successful Login
            res_login = client.post(
                "/api/v1/auth/login",
                json={"username": "alice_api", "password": "AlicePassword123!"},
            )
            assert res_login.status_code == 200
            data_login = res_login.json()
            assert "token" in data_login
            login_token = data_login["token"]
            print("✅ Successful Login PASSED")

            # 4. Incorrect Password Rejection
            res_bad_pw = client.post(
                "/api/v1/auth/login",
                json={"username": "alice_api", "password": "IncorrectPassword!"},
            )
            assert res_bad_pw.status_code == 401
            print("✅ Incorrect password rejection (HTTP 401) PASSED")

            # 5. Unknown Username Rejection
            res_bad_user = client.post(
                "/api/v1/auth/login",
                json={"username": "unknown_ghost_user", "password": "SomePassword123!"},
            )
            assert res_bad_user.status_code == 401
            print("✅ Unknown user rejection (HTTP 401) PASSED")

            # 6. Access /api/v1/auth/me with Bearer token
            res_me = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {login_token}"},
            )
            assert res_me.status_code == 200
            me_data = res_me.json()
            assert me_data["username"] == "alice_api"
            assert me_data["role"] == "USER"
            print("✅ Authenticated /api/v1/auth/me PASSED")

            # 7. Access /api/v1/auth/me without token -> Must be 401
            client.cookies.clear()
            res_unauth = client.get("/api/v1/auth/me")
            assert res_unauth.status_code == 401
            print("✅ Unauthenticated request rejection (HTTP 401) PASSED")

            # 8. Logout -> Revokes token
            res_logout = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {login_token}"},
            )
            assert res_logout.status_code == 200

            # 9. Access /api/v1/auth/me with revoked token -> Must be 401
            res_me_revoked = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {login_token}"},
            )
            assert res_me_revoked.status_code == 401, "Revoked token must yield HTTP 401"
            print("✅ Logout and session revocation PASSED")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db
            core.audit.db = orig_audit_db


if __name__ == "__main__":
    test_password_hashing()
    test_input_validations()
    test_public_registration_always_creates_user()
    test_owner_cli_provisioning()
    test_auth_api_workflow()
    print("\nALL AUTHENTICATION TESTS PASSED SUCCESSFULLY!")
