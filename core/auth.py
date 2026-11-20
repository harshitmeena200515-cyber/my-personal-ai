"""
Authentication and Password Management Engine for MY PERSONAL AI.

Provides:
- Argon2id password hashing and constant-time verification.
- Password complexity validation.
- User creation with automatic first-user OWNER assignment.
- User credential authentication.
"""

import re
import uuid
from typing import Any, Dict, Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from core.logging import logger
from data.db import db

# Argon2id hasher configured per OWASP recommendations for high security
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against an Argon2id hash in constant time."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception as e:
        logger.warning("password_verification_error", error=str(e))
        return False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Validate password meets minimum complexity requirements.

    Requirements:
    - At least 8 characters
    - Contains at least one letter
    - Contains at least one number or special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"[\d\W_]", password):
        return False, "Password must contain at least one number or special character."
    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    """Validate username format.

    Requirements:
    - 3 to 30 characters
    - Alphanumeric, underscores, hyphens only
    """
    cleaned = username.strip()
    if len(cleaned) < 3 or len(cleaned) > 30:
        return False, "Username must be between 3 and 30 characters."
    if not re.match(r"^[a-zA-Z0-9_\-]+$", cleaned):
        return False, "Username can only contain alphanumeric characters, underscores, and hyphens."
    return True, ""


def create_user(
    username: str,
    password: str,
    role: str = "USER",
) -> Dict[str, Any]:
    """Create a new user account with Argon2id password hash.

    By default, creates an account with 'USER' role.
    'OWNER' role can only be assigned when explicitly requested by authorized callers (e.g. CLI setup).
    Public registration through the API is strictly restricted to 'USER'.
    """
    db.init_db()

    # 1. Validate username
    is_valid_user, user_err = validate_username(username)
    if not is_valid_user:
        raise ValueError(user_err)

    cleaned_username = username.strip()

    # 2. Check duplicate username
    existing = db.fetch_one("SELECT id FROM users WHERE username = ? COLLATE NOCASE;", (cleaned_username,))
    if existing:
        raise ValueError(f"Username '{cleaned_username}' is already registered.")

    # 3. Validate password strength
    is_valid_pwd, pwd_err = validate_password_strength(password)
    if not is_valid_pwd:
        raise ValueError(pwd_err)

    # 4. Determine role (strictly enforce role, default USER)
    assigned_role = (role or "USER").upper()
    if assigned_role not in ("OWNER", "USER", "ADMIN"):
        assigned_role = "USER"

    # 5. Hash password and insert
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)

    db.execute(
        """
        INSERT INTO users (id, username, password_hash, role, is_active)
        VALUES (?, ?, ?, ?, 1);
        """,
        (user_id, cleaned_username, pw_hash, assigned_role),
    )

    logger.info("user_created", user_id=user_id, username=cleaned_username, role=assigned_role)

    return {
        "id": user_id,
        "username": cleaned_username,
        "role": assigned_role,
        "is_active": True,
    }


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user credentials and return user profile if valid."""
    db.init_db()
    cleaned_username = username.strip()

    user = db.fetch_one(
        "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ? COLLATE NOCASE;",
        (cleaned_username,),
    )
    if not user:
        # Constant-time dummy verification to thwart user enumeration timing attacks
        try:
            _hasher.verify(
                "$argon2id$v=19$m=65536,t=3,p=4$dummyhashtopreventtimingattacks$dummyhashbytesdummyhashbytesdummyha",
                "dummy",
            )
        except Exception:
            pass
        return None

    if not user["is_active"]:
        logger.warning("auth_failed_inactive_user", username=cleaned_username)
        return None

    if not verify_password(user["password_hash"], password):
        logger.warning("auth_failed_invalid_password", username=cleaned_username)
        return None

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
    }


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by unique ID (excluding password hash)."""
    db.init_db()
    user = db.fetch_one(
        "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?;",
        (user_id,),
    )
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
        "created_at": user["created_at"],
    }
