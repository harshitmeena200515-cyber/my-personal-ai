"""
Database connection and migration manager for MY PERSONAL AI.

Provides:
- SQLite connection management with WAL mode, foreign keys, and 5s busy timeout.
- Automated SQL migration runner.
- Thread-safe parameterized query helpers (execute, fetch_one, fetch_all).
"""

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from core.config import settings
from core.logging import logger


class DatabaseManager:
    """Thread-safe SQLite database manager with WAL mode and migrations."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            self.db_path = Path(settings.APP_DB_PATH).resolve()

        self.migrations_dir = Path(__file__).parent / "migrations"
        self._lock = threading.RLock()
        self._initialized = False

    def _ensure_dir(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection with required pragmas."""
        self._ensure_dir()
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

        # Security & concurrency pragmas
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing a managed connection with transaction handling."""
        conn = self.get_connection()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def run_migrations(self) -> int:
        """Discover and execute all unapplied SQL migrations in order."""
        self._ensure_dir()
        applied_count = 0

        with self._lock:
            conn = self.get_connection()
            try:
                # Ensure migration tracker table exists
                with conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version INTEGER PRIMARY KEY,
                            name TEXT NOT NULL,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)

                # Fetch applied migration versions
                cursor = conn.execute("SELECT version FROM schema_migrations;")
                applied_versions = {row["version"] for row in cursor.fetchall()}

                # Discover migration files
                if not self.migrations_dir.exists():
                    logger.warning("migrations_dir_not_found", path=str(self.migrations_dir))
                    return 0

                migration_files = sorted(self.migrations_dir.glob("*.sql"))

                for mf in migration_files:
                    match = re.match(r"^(\d+)_", mf.name)
                    if not match:
                        continue
                    version = int(match.group(1))

                    if version not in applied_versions:
                        logger.info("applying_migration", version=version, name=mf.name)
                        sql_content = mf.read_text(encoding="utf-8")

                        # executescript handles DDL statements in their own transactions
                        conn.executescript(sql_content)

                        # Record migration in tracking table
                        with conn:
                            conn.execute(
                                "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                                (version, mf.name),
                            )
                        applied_count += 1
                        logger.info("migration_applied_successfully", version=version, name=mf.name)

            finally:
                conn.close()

        return applied_count

    def init_db(self) -> None:
        """Initialize database and apply all pending migrations."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            applied = self.run_migrations()
            self._initialized = True
            logger.info("database_initialized", path=str(self.db_path), migrations_applied=applied)

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> int:
        """Execute a write statement with parameters and return affected rows."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single record as a dictionary."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Fetch all records as a list of dictionaries."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# Singleton database instance using application settings
db = DatabaseManager()
