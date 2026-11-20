"""
Session Management Unit Tests for MY PERSONAL AI (Phase 4A).

Verifies:
1. CSPRNG 256-bit secure token generation
2. SHA-256 token hashing (zero plaintext tokens in database)
3. Session validation and profile retrieval
4. Session expiration behavior
5. Session revocation on logout
6. Revocation of all sessions for a user
7. Malformed or empty token handling
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auth import create_user
from core.sessions import (
    _hash_token,
    cleanup_expired_sessions,
    create_session,
    revoke_all_user_sessions,
    revoke_session,
    validate_session,
)
from data.db import DatabaseManager
import core.auth
import core.sessions


def test_session_lifecycle():
    """Verify session creation, token hashing, and validation."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_sess.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr

        try:
            # Create a user
            user = create_user("bob_session_test", "BobPassword123!")
            user_id = user["id"]

            # 1. Create Session
            raw_token, sess_info = create_session(user_id=user_id, ttl_seconds=3600)
            assert raw_token is not None
            assert len(raw_token) >= 32, "Raw token must have sufficient entropy"

            # 2. Verify Database stores ONLY the hash, never raw token
            expected_hash = _hash_token(raw_token)
            db_row = test_mgr.fetch_one("SELECT * FROM sessions WHERE id = ?;", (sess_info["id"],))
            assert db_row is not None
            assert db_row["token_hash"] == expected_hash
            assert raw_token not in db_row["token_hash"]
            print("✅ Token generation & hashed storage PASSED")

            # 3. Validate Session
            valid_profile = validate_session(raw_token)
            assert valid_profile is not None
            assert valid_profile["username"] == "bob_session_test"
            assert valid_profile["user_id"] == user_id
            print("✅ Session validation PASSED")

            # 4. Revoke Session
            revoked = revoke_session(raw_token)
            assert revoked is True
            assert validate_session(raw_token) is None, "Revoked session must not validate"
            print("✅ Session revocation PASSED")

            # 5. Revoking already revoked session returns False
            assert revoke_session(raw_token) is False

            # 6. Invalid and Empty Tokens
            assert validate_session("") is None
            assert validate_session("non_existent_token_12345") is None
            assert validate_session(None) is None
            print("✅ Invalid token safety PASSED")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db


def test_session_expiration():
    """Verify that an expired session fails validation."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_exp.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr

        try:
            user = create_user("charlie_exp", "CharliePassword123!")
            # Create a session with negative TTL (already expired)
            raw_token, sess_info = create_session(user_id=user["id"], ttl_seconds=-10)

            # Validation must return None
            res = validate_session(raw_token)
            assert res is None, "Expired session must fail validation"
            print("✅ Session expiration verification PASSED")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db


def test_revoke_all_sessions():
    """Verify bulk revocation of all user sessions."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_revoke_all.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr

        try:
            user = create_user("david_multi_sess", "DavidPassword123!")
            token1, _ = create_session(user["id"], ttl_seconds=3600)
            token2, _ = create_session(user["id"], ttl_seconds=3600)

            assert validate_session(token1) is not None
            assert validate_session(token2) is not None

            # Revoke all
            count = revoke_all_user_sessions(user["id"])
            assert count == 2, f"Expected 2 revoked sessions, got {count}"

            assert validate_session(token1) is None
            assert validate_session(token2) is None
            print("✅ Bulk session revocation PASSED")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db


def test_cleanup_expired_sessions_lifecycle():
    """Verify purge of expired or revoked sessions older than threshold."""
    with tempfile.TemporaryDirectory() as td:
        test_db_path = Path(td) / "test_cleanup.db"
        test_mgr = DatabaseManager(str(test_db_path))
        test_mgr.init_db()

        orig_auth_db = core.auth.db
        orig_sess_db = core.sessions.db
        core.auth.db = test_mgr
        core.sessions.db = test_mgr

        try:
            user = create_user("clean_test_user", "CleanPass123!")
            # 1. Create expired session (ttl = -100s)
            token_exp, _ = create_session(user["id"], ttl_seconds=-100)
            # 2. Create active session
            token_active, _ = create_session(user["id"], ttl_seconds=3600)

            # Cleanup sessions with 0-second retention (deletes expired sessions)
            deleted = cleanup_expired_sessions(retention_days=0)
            assert deleted >= 1, "Expected at least 1 expired session to be purged"

            # Active session remains valid
            assert validate_session(token_active) is not None
            print("✅ test_cleanup_expired_sessions_lifecycle PASSED")

        finally:
            core.auth.db = orig_auth_db
            core.sessions.db = orig_sess_db


if __name__ == "__main__":
    test_session_lifecycle()
    test_session_expiration()
    test_revoke_all_sessions()
    test_cleanup_expired_sessions_lifecycle()
    print("\nALL SESSION TESTS PASSED SUCCESSFULLY!")
