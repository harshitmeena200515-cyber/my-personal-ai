"""
Secure Session Management Engine for MY PERSONAL AI.

Provides:
- Cryptographically secure random session tokens (256-bit CSPRNG via secrets).
- Token hashing (SHA-256) so plaintext tokens are NEVER stored in the database.
- Session expiration and immediate revocation on logout.
- Constant-time lookup and validation.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from core.config import settings
from core.logging import logger
from data.db import db


def _hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of a session token for secure database storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(
    user_id: str,
    ttl_seconds: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Generate a new secure session token and store its hash in the database.

    Returns:
        (raw_token, session_dict)
    """
    db.init_db()

    # 1. Generate 256-bit secure random token (43-44 base64 characters)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    # 2. Compute expiration
    ttl = ttl_seconds if ttl_seconds is not None else getattr(settings, "SESSION_TTL_SECONDS", 604800)
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(seconds=ttl)
    expires_at_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

    # 3. Insert session into database
    session_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO sessions (id, user_id, token_hash, expires_at)
        VALUES (?, ?, ?, ?);
        """,
        (session_id, user_id, token_hash, expires_at_str),
    )

    logger.info("session_created", user_id=user_id, session_id=session_id, expires_at=expires_at_str)

    return raw_token, {
        "id": session_id,
        "user_id": user_id,
        "expires_at": expires_at_str,
    }


def validate_session(raw_token: str) -> Optional[Dict[str, Any]]:
    """Validate a raw session token against the database.

    Returns user session profile if token is valid, unexpired, and not revoked.
    """
    if not raw_token or not raw_token.strip():
        return None

    db.init_db()
    token_hash = _hash_token(raw_token.strip())

    # Query active session joined with user record
    row = db.fetch_one(
        """
        SELECT 
            s.id as session_id,
            s.user_id,
            s.expires_at,
            s.revoked_at,
            u.username,
            u.role,
            u.is_active
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token_hash = ?;
        """,
        (token_hash,),
    )

    if not row:
        return None

    # Check revocation
    if row["revoked_at"] is not None:
        return None

    # Check user active status
    if not row["is_active"]:
        return None

    # Check expiration (UTC comparison)
    try:
        # SQLite CURRENT_TIMESTAMP is in UTC format '%Y-%m-%d %H:%M:%S'
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            return None
    except Exception as e:
        logger.warning("session_date_parse_error", error=str(e))
        return None

    return {
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
        "expires_at": row["expires_at"],
    }


def revoke_session(raw_token: str) -> bool:
    """Revoke an active session token immediately upon logout."""
    if not raw_token or not raw_token.strip():
        return False

    db.init_db()
    token_hash = _hash_token(raw_token.strip())
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    affected = db.execute(
        """
        UPDATE sessions
        SET revoked_at = ?
        WHERE token_hash = ? AND revoked_at IS NULL;
        """,
        (now_utc_str, token_hash),
    )

    if affected > 0:
        logger.info("session_revoked", token_hash=token_hash[:12] + "...")
        return True
    return False


def revoke_all_user_sessions(user_id: str) -> int:
    """Revoke all active sessions for a given user."""
    db.init_db()
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    affected = db.execute(
        """
        UPDATE sessions
        SET revoked_at = ?
        WHERE user_id = ? AND revoked_at IS NULL;
        """,
        (now_utc_str, user_id),
    )
    logger.info("all_user_sessions_revoked", user_id=user_id, count=affected)
    return affected


def cleanup_expired_sessions(retention_days: int = 30) -> int:
    """Permanently delete expired or revoked sessions older than retention threshold."""
    db.init_db()
    cutoff_utc = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_str = cutoff_utc.strftime("%Y-%m-%d %H:%M:%S")

    deleted = db.execute(
        """
        DELETE FROM sessions
        WHERE (expires_at < ? OR revoked_at < ?);
        """,
        (cutoff_str, cutoff_str),
    )
    if deleted > 0:
        logger.info("expired_sessions_cleaned", count=deleted, cutoff=cutoff_str)
    return deleted

