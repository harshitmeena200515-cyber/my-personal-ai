"""
Per-User File Sandbox Manager for MY PERSONAL AI (Phase 4B).

Provides:
- Strict path confinement to data/users/{user_id}/.
- Prevention of directory traversal (../), absolute path escapes, and symlink attacks.
- Isolated user workspaces for file operations, artifacts, and multi-user tenancy.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.audit import log_audit_event
from core.config import settings
from core.logging import logger


class UserSandboxError(Exception):
    """Raised when an operation violates user sandbox boundaries."""
    pass


class UserSandbox:
    """Manages file storage isolated to a specific authenticated user."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            self.base_dir = Path(settings.APP_DB_PATH).resolve().parent / "users"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_user_root(self, user_id: str) -> Path:
        """Get the root directory for a specific user, creating it if needed."""
        if not user_id or not user_id.strip():
            raise UserSandboxError("Invalid user_id provided for sandbox access.")

        # Disallow path traversal or dangerous characters in user_id
        if any(c in user_id for c in ("/", "\\", "..", "\x00")):
            raise UserSandboxError("Path traversal or illegal characters detected in user_id.")

        safe_id = "".join(c for c in user_id.strip() if c.isalnum() or c in ("-", "_"))
        if not safe_id or safe_id != user_id.strip():
            raise UserSandboxError("Invalid characters in user_id.")

        user_dir = (self.base_dir / safe_id).resolve()

        # Enforce that user_dir is strictly inside self.base_dir
        if not str(user_dir).startswith(str(self.base_dir)):
            raise UserSandboxError("Sandbox root escape attempt detected.")

        # Ensure standard subdirectories
        (user_dir / "workspace").mkdir(parents=True, exist_ok=True)
        (user_dir / "scratch").mkdir(parents=True, exist_ok=True)
        return user_dir

    def resolve_path(self, user_id: str, relative_path: str) -> Path:
        """Resolve a relative path inside the user's sandbox with traversal protection."""
        user_root = self.get_user_root(user_id)

        # Normalize path
        clean_rel = os.path.normpath(relative_path).lstrip("/\\")
        target_path = (user_root / clean_rel).resolve()

        # Strict containment check
        if not str(target_path).startswith(str(user_root)):
            logger.warning(
                "sandbox_traversal_blocked",
                user_id=user_id,
                target_path=str(target_path),
                user_root=str(user_root),
            )
            try:
                log_audit_event(
                    event_type="SANDBOX_TRAVERSAL_BLOCKED",
                    action="file_access",
                    user_id=user_id,
                    resource=relative_path,
                    status="BLOCKED",
                    severity="HIGH",
                    details={"target_path": str(target_path)},
                )
            except Exception:
                pass
            raise UserSandboxError(f"Access denied: path '{relative_path}' is outside user sandbox.")

        return target_path

    def list_files(self, user_id: str, subfolder: str = "workspace") -> List[Dict[str, Any]]:
        """List files in user's sandbox directory."""
        folder = self.resolve_path(user_id, subfolder)
        if not folder.exists() or not folder.is_dir():
            return []

        results = []
        for p in folder.iterdir():
            if p.is_file():
                results.append({
                    "name": p.name,
                    "size_bytes": p.stat().st_size,
                    "modified_at": p.stat().st_mtime,
                    "relative_path": str(p.relative_to(self.get_user_root(user_id))).replace("\\", "/"),
                })
        return results

    def write_file(self, user_id: str, relative_path: str, content: str) -> Path:
        """Write content to a file inside the user's sandbox."""
        resolved = self.resolve_path(user_id, relative_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        logger.info("sandbox_file_written", user_id=user_id, path=str(resolved))
        return resolved

    def read_file(self, user_id: str, relative_path: str) -> str:
        """Read content from a file inside the user's sandbox."""
        resolved = self.resolve_path(user_id, relative_path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return resolved.read_text(encoding="utf-8")

    def delete_file(self, user_id: str, relative_path: str) -> bool:
        """Delete a file inside the user's sandbox."""
        resolved = self.resolve_path(user_id, relative_path)
        if resolved.exists() and resolved.is_file():
            resolved.unlink()
            logger.info("sandbox_file_deleted", user_id=user_id, path=str(resolved))
            return True
        return False


# Singleton sandbox instance
user_sandbox = UserSandbox()
