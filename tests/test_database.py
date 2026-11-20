"""
Unit and integration tests for SQLite Database Foundation (Phase 4A).

Verifies:
1. Schema initialization and migrations
2. SQLite Pragmas (WAL mode, Foreign Keys)
3. Foreign key enforcement (integrity constraints)
4. Cascade deletion of sessions on user delete
5. Migration idempotency
6. Thread-safe execution
"""

import sys
import tempfile
import threading
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.db import DatabaseManager
import sqlite3


def test_database_init():
    """Verify table creation from migration files."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_init.db"
        manager = DatabaseManager(str(db_path))
        manager.init_db()

        assert db_path.exists(), "Database file must exist after init"

        tables = [r["name"] for r in manager.fetch_all("SELECT name FROM sqlite_master WHERE type='table';")]
        assert "users" in tables, "users table must be present"
        assert "sessions" in tables, "sessions table must be present"
        assert "schema_migrations" in tables, "schema_migrations table must be present"
        print("✅ test_database_init PASSED")


def test_pragmas():
    """Verify WAL mode and foreign key enforcement."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_pragmas.db"
        manager = DatabaseManager(str(db_path))
        manager.init_db()

        conn = manager.get_connection()
        try:
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert fk == 1, f"Expected foreign_keys=1, got {fk}"
            assert jm.lower() == "wal", f"Expected journal_mode=wal, got {jm}"
        finally:
            conn.close()
        print("✅ test_pragmas PASSED")


def test_migration_idempotency():
    """Verify running migrations multiple times is safe and skips applied ones."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_idempotent.db"
        manager = DatabaseManager(str(db_path))
        applied_first = manager.run_migrations()
        assert applied_first >= 1, "First run should apply at least 1 migration"

        applied_second = manager.run_migrations()
        assert applied_second == 0, "Second run should apply 0 migrations"
        print("✅ test_migration_idempotency PASSED")


def test_foreign_key_enforcement():
    """Verify foreign key constraint blocks orphan session insertion."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_fk.db"
        manager = DatabaseManager(str(db_path))
        manager.init_db()

        # Attempt to insert a session with non-existent user_id
        try:
            manager.execute(
                "INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?);",
                ("sess_1", "non_existent_user", "hash123", "2099-01-01 00:00:00"),
            )
            assert False, "Expected sqlite3.IntegrityError on foreign key violation"
        except sqlite3.IntegrityError:
            print("✅ test_foreign_key_enforcement PASSED (Foreign key violation correctly rejected)")


def test_cascade_delete():
    """Verify deleting a user cascades and removes their sessions."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_cascade.db"
        manager = DatabaseManager(str(db_path))
        manager.init_db()

        # Insert user
        manager.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?);",
            ("user_1", "alice", "$argon2id$mockhash", "USER"),
        )
        # Insert session for user
        manager.execute(
            "INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?);",
            ("sess_1", "user_1", "hash123", "2099-01-01 00:00:00"),
        )

        assert manager.fetch_one("SELECT * FROM sessions WHERE id = 'sess_1';") is not None

        # Delete user
        manager.execute("DELETE FROM users WHERE id = 'user_1';")

        # Session should be cascaded
        sess = manager.fetch_one("SELECT * FROM sessions WHERE id = 'sess_1';")
        assert sess is None, "Session must be deleted when user is deleted"
        print("✅ test_cascade_delete PASSED")


def test_thread_safety():
    """Verify concurrent writes from multiple threads execute safely."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_threads.db"
        manager = DatabaseManager(str(db_path))
        manager.init_db()

        errors = []

        def worker(idx: int):
            try:
                manager.execute(
                    "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?);",
                    (f"user_{idx}", f"user_{idx}", "$argon2id$mockhash", "USER"),
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors occurred: {errors}"
        count = manager.fetch_one("SELECT COUNT(*) as c FROM users;")["c"]
        assert count == 10, f"Expected 10 users, got {count}"
        print("✅ test_thread_safety PASSED")


if __name__ == "__main__":
    test_database_init()
    test_pragmas()
    test_migration_idempotency()
    test_foreign_key_enforcement()
    test_cascade_delete()
    test_thread_safety()
    print("\nALL DATABASE TESTS PASSED SUCCESSFULLY!")
