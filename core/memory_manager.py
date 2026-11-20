"""
Two-Part Memory Architecture Engine (ADR-009).

Provides:
- PrivateAgentMemory: In-process isolated memory per agent (scratchpad + learned heuristics).
- SharedMemoryStore: Authoritative store in SQLite (app.db) holding strictly owner-approved rules.
- DataSanitizer: Inbound filter rejecting passwords, API keys, and sensitive PII patterns.
- Provenance: USER_CONFIRMED, AGENT_INFERRED, EXTERNALLY_VERIFIED, PENDING_APPROVAL.
"""

import re
import uuid
import threading
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from data.db import db
from core.logging import logger


class Provenance(str, Enum):
    """Mandatory provenance taxonomy for all memory records."""
    USER_CONFIRMED = "USER_CONFIRMED"
    AGENT_INFERRED = "AGENT_INFERRED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"


class SecurityException(Exception):
    """Raised when sensitive data or unauthorized memory access is detected."""
    pass


class DataSanitizer:
    """Detects and rejects secrets, API keys, passwords, and PII patterns."""

    SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),          # OpenAI keys
        re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE),          # Google API keys
        re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),             # GitHub tokens
        re.compile(r"Bearer\s+[a-zA-Z0-9\._\-]{20,}", re.IGNORECASE),  # Bearer tokens
        re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),     # Private keys
        re.compile(r"(?:password|passwd|secret|api_key)\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.IGNORECASE),
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Scan text and raise SecurityException if an unredacted secret is found."""
        if not text:
            return text
        for pattern in cls.SECRET_PATTERNS:
            if pattern.search(text):
                logger.warning("security_alert_sensitive_data_blocked", pattern=pattern.pattern)
                raise SecurityException(
                    "Security Violation: Sensitive secret, API key, or credential pattern detected. "
                    "Memory insertion blocked under ADR-004 & ADR-009."
                )
        return text


class PrivateAgentMemory:
    """Isolated, in-process working memory for a single agent."""

    def __init__(self, agent_id: str, user_id: str):
        self.agent_id = agent_id
        self.user_id = user_id
        self._lock = threading.RLock()
        self._scratchpad: Dict[str, Any] = {}
        self._positive_heuristics: List[Dict[str, Any]] = []
        self._negative_case_ledger: List[Dict[str, Any]] = []

    def set_scratchpad(self, key: str, value: Any) -> None:
        """Set a task-scoped working variable (ephemeral)."""
        with self._lock:
            if isinstance(value, str):
                DataSanitizer.sanitize(value)
            self._scratchpad[key] = {
                "value": value,
                "provenance": Provenance.AGENT_INFERRED.value,
                "timestamp": datetime.utcnow().isoformat(),
            }

    def get_scratchpad(self, key: str) -> Optional[Any]:
        """Retrieve a task-scoped variable."""
        with self._lock:
            entry = self._scratchpad.get(key)
            return entry["value"] if entry else None

    def clear_scratchpad(self) -> None:
        """Clear task-scoped scratchpad after subtask completion."""
        with self._lock:
            self._scratchpad.clear()

    def record_heuristic(self, domain: str, rule: str, successful: bool) -> None:
        """Record domain-specific procedural heuristics (positive or negative)."""
        DataSanitizer.sanitize(rule)
        with self._lock:
            entry = {
                "id": str(uuid.uuid4()),
                "domain": domain,
                "rule": rule,
                "successful": successful,
                "provenance": Provenance.AGENT_INFERRED.value,
                "recorded_at": datetime.utcnow().isoformat(),
            }
            if successful:
                self._positive_heuristics.append(entry)
            else:
                self._negative_case_ledger.append(entry)

    def get_heuristics(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return private heuristics for this agent only."""
        with self._lock:
            if domain:
                return [h for h in self._positive_heuristics if h["domain"] == domain]
            return list(self._positive_heuristics)

    def get_negative_cases(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return known pitfalls to avoid."""
        with self._lock:
            if domain:
                return [n for n in self._negative_case_ledger if n["domain"] == domain]
            return list(self._negative_case_ledger)


class SharedMemoryStore:
    """Authoritative, SQLite-backed shared memory holding owner-approved rules."""

    def __init__(self, db_instance=None):
        self.db = db_instance or db

    def propose_entry(
        self,
        user_id: str,
        key: str,
        content: str,
        category: str = "rule",
        proposed_by: str = "agent"
    ) -> Dict[str, Any]:
        """Propose a rule or decision into shared memory (status: PENDING_APPROVAL)."""
        DataSanitizer.sanitize(content)
        entry_id = str(uuid.uuid4())
        provenance = Provenance.PENDING_APPROVAL.value

        query = """
        INSERT INTO shared_memory (id, user_id, key, content, category, provenance, proposed_by, version)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """
        self.db.execute(query, (entry_id, user_id, key, content, category, provenance, proposed_by))
        logger.info("shared_memory_entry_proposed", id=entry_id, user_id=user_id, key=key, proposed_by=proposed_by)

        return {
            "id": entry_id,
            "user_id": user_id,
            "key": key,
            "content": content,
            "category": category,
            "provenance": provenance,
            "proposed_by": proposed_by,
        }

    def approve_entry(self, entry_id: str, user_id: str) -> Dict[str, Any]:
        """Promote a pending entry to USER_CONFIRMED. Strictly requires owner action."""
        entry = self.get_entry(entry_id)
        if not entry:
            raise ValueError(f"Entry with ID {entry_id} not found.")
        if entry["user_id"] != user_id:
            raise SecurityException("Access Denied: Cannot approve another user's memory entry.")

        now = datetime.utcnow().isoformat()
        provenance = Provenance.USER_CONFIRMED.value

        query = """
        UPDATE shared_memory
        SET provenance = ?, approved_by = ?, approved_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """
        self.db.execute(query, (provenance, user_id, now, entry_id, user_id))
        logger.info("shared_memory_entry_approved", id=entry_id, user_id=user_id, approved_by=user_id)

        entry["provenance"] = provenance
        entry["approved_by"] = user_id
        entry["approved_at"] = now
        return entry

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific shared memory entry by ID."""
        query = "SELECT * FROM shared_memory WHERE id = ?"
        return self.db.fetch_one(query, (entry_id,))

    def get_approved_rules(self, user_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch strictly USER_CONFIRMED rules for grounding agent reasoning."""
        if category:
            query = """
            SELECT * FROM shared_memory
            WHERE user_id = ? AND provenance = ? AND category = ?
            ORDER BY created_at ASC
            """
            return self.db.fetch_all(query, (user_id, Provenance.USER_CONFIRMED.value, category))
        else:
            query = """
            SELECT * FROM shared_memory
            WHERE user_id = ? AND provenance = ?
            ORDER BY created_at ASC
            """
            return self.db.fetch_all(query, (user_id, Provenance.USER_CONFIRMED.value))

    def get_pending_proposals(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetch all PENDING_APPROVAL proposals awaiting owner review."""
        query = """
        SELECT * FROM shared_memory
        WHERE user_id = ? AND provenance = ?
        ORDER BY created_at ASC
        """
        return self.db.fetch_all(query, (user_id, Provenance.PENDING_APPROVAL.value))


class MemoryManager:
    """Central Memory Architecture Manager coordinating private memories and shared store."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MemoryManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_instance=None):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._private_stores: Dict[str, PrivateAgentMemory] = {}
            self._shared_store = SharedMemoryStore(db_instance)
            self._initialized = True

    def get_private_memory(self, agent_id: str, user_id: str) -> PrivateAgentMemory:
        """Get or initialize private memory isolated for a specific agent and user."""
        key = f"{user_id}:{agent_id}"
        with self._lock:
            if key not in self._private_stores:
                self._private_stores[key] = PrivateAgentMemory(agent_id=agent_id, user_id=user_id)
            return self._private_stores[key]

    @property
    def shared_memory(self) -> SharedMemoryStore:
        """Access the authoritative shared memory store."""
        return self._shared_store


# Global singleton instance
memory_manager = MemoryManager()
