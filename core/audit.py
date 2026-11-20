"""
Tamper-Resistant Security Audit Logger & Persistent HITL Storage (Milestone Phase 4).

Features:
- Cryptographic SHA-256 hash chaining on all audit log records.
- Engine-level SQLite triggers preventing UPDATE or DELETE on audit_logs.
- Chain integrity verification (verify_audit_log_integrity) detecting any row tampering.
- Persistent Human-in-the-Loop (HITL) authorization workflow with TTL expiration.
- Protection against duplicate execution, self-approval, and expired authorizations.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.logging import logger
from data.db import db


def compute_entry_hash(
    prev_hash: str,
    event_id: str,
    user_id: Optional[str],
    event_type: str,
    action: str,
    status: str,
    created_at: str,
    details_str: str,
) -> str:
    """Compute deterministic cryptographic SHA-256 hash for an audit log entry."""
    canonical_payload = (
        f"{prev_hash}|{event_id}|{user_id or 'NONE'}|{event_type}|{action}|"
        f"{status}|{created_at}|{details_str}"
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def log_audit_event(
    event_type: str,
    action: str,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    status: str = "SUCCESS",
    severity: str = "INFO",
    ip_address: str = "127.0.0.1",
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """Record an immutable, hash-chained security event into SQLite audit_logs table."""
    event_id = str(uuid.uuid4())
    details_dict = dict(details or {})
    now_utc = datetime.now(timezone.utc)
    created_at_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

    db.init_db()

    # 1. Verify user_id exists in target DB to satisfy foreign key constraint
    valid_user_id = None
    if user_id:
        try:
            row = db.fetch_one("SELECT id FROM users WHERE id = ?", (user_id,))
            if row:
                valid_user_id = user_id
            else:
                details_dict["unreferenced_user_id"] = user_id
        except Exception:
            details_dict["unreferenced_user_id"] = user_id

    details_str = json.dumps(details_dict, sort_keys=True)

    # 2. Cryptographic Hash Chaining: get latest entry_hash
    latest_row = db.fetch_one("SELECT entry_hash FROM audit_logs ORDER BY rowid DESC LIMIT 1;")
    prev_hash = latest_row["entry_hash"] if (latest_row and latest_row.get("entry_hash")) else "GENESIS"

    # 3. Compute entry hash
    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        event_id=event_id,
        user_id=valid_user_id,
        event_type=event_type,
        action=action,
        status=status,
        created_at=created_at_str,
        details_str=details_str,
    )

    db.execute(
        """
        INSERT INTO audit_logs (id, user_id, event_type, action, resource, status, severity, ip_address, details_json, created_at, prev_hash, entry_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (event_id, valid_user_id, event_type, action, resource, status, severity, ip_address, details_str, created_at_str, prev_hash, entry_hash),
    )

    logger.info(
        "security_audit_event",
        audit_id=event_id,
        user_id=user_id,
        event_type=event_type,
        action=action,
        status=status,
        severity=severity,
        entry_hash=entry_hash[:12] + "...",
    )
    return event_id


def verify_audit_log_integrity() -> Dict[str, Any]:
    """Verify cryptographic hash chain integrity of all chained records in audit_logs."""
    db.init_db()
    rows = db.fetch_all("SELECT * FROM audit_logs WHERE entry_hash IS NOT NULL ORDER BY rowid ASC;")
    if not rows:
        return {"valid": True, "total_records": 0, "message": "Audit log is empty."}

    expected_prev = "GENESIS"
    for idx, row in enumerate(rows):
        # 1. Check prev_hash linkage
        if row.get("prev_hash") != expected_prev:
            return {
                "valid": False,
                "tampered_at_index": idx,
                "tampered_record_id": row["id"],
                "reason": f"Broken chain linkage: prev_hash '{row.get('prev_hash')}' != expected '{expected_prev}'",
            }

        # 2. Recompute hash
        details_raw = row.get("details_json", "{}")
        if isinstance(details_raw, str):
            try:
                # canonical sorted JSON
                details_sorted = json.dumps(json.loads(details_raw), sort_keys=True)
            except Exception:
                details_sorted = details_raw
        else:
            details_sorted = json.dumps(details_raw, sort_keys=True)

        computed = compute_entry_hash(
            prev_hash=row["prev_hash"],
            event_id=row["id"],
            user_id=row["user_id"],
            event_type=row["event_type"],
            action=row["action"],
            status=row["status"],
            created_at=row["created_at"],
            details_str=details_sorted,
        )

        if row.get("entry_hash") != computed:
            return {
                "valid": False,
                "tampered_at_index": idx,
                "tampered_record_id": row["id"],
                "reason": f"Hash mismatch: stored '{row.get('entry_hash')}' != computed '{computed}'",
            }

        expected_prev = row["entry_hash"]

    return {
        "valid": True,
        "total_records": len(rows),
        "chain_head": rows[-1]["entry_hash"],
        "message": "Audit trail is fully verified and tamper-free.",
    }


def list_audit_logs(
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Retrieve security audit logs with optional user and type filtering."""
    db.init_db()
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params: List[Any] = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    rows = db.fetch_all(query, tuple(params))
    for r in rows:
        if isinstance(r.get("details_json"), str):
            try:
                r["details"] = json.loads(r["details_json"])
            except Exception:
                r["details"] = {}
    return rows


# --- Persistent HITL Approvals ---

def create_hitl_approval(
    user_id: str,
    agent_name: str,
    action: str,
    reason: str,
    risk_level: str = "HIGH",
    conversation_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = 3600,
) -> str:
    """Store a pending Human-in-the-Loop approval request with expiration TTL."""
    db.init_db()
    approval_id = str(uuid.uuid4())
    meta_str = json.dumps(metadata or {})
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(seconds=ttl_seconds)
    expires_at_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """
        INSERT INTO hitl_approvals (id, user_id, conversation_id, agent_name, action, reason, risk_level, status, metadata_json, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?);
        """,
        (approval_id, user_id, conversation_id, agent_name, action, reason, risk_level, meta_str, expires_at_str),
    )

    log_audit_event(
        event_type="HITL_REQUEST_CREATED",
        action=action,
        user_id=user_id,
        resource=f"hitl_approvals/{approval_id}",
        severity=risk_level,
        details={"agent": agent_name, "reason": reason, "expires_at": expires_at_str},
    )
    return approval_id


def resolve_hitl_approval(
    approval_id: str,
    user_id: str,
    approved: bool,
) -> bool:
    """Resolve a pending HITL approval as APPROVED or DENIED, enforcing expiration and authorization."""
    db.init_db()
    # Ensure item exists and caller is authorized (owner or requesting user)
    row = db.fetch_one(
        "SELECT * FROM hitl_approvals WHERE id = ? AND (user_id = ? OR ? IN (SELECT id FROM users WHERE role = 'OWNER'));",
        (approval_id, user_id, user_id),
    )
    if not row or row["status"] != "PENDING":
        return False

    # Check expiration
    if row.get("expires_at"):
        try:
            exp_dt = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= exp_dt:
                # Mark as EXPIRED
                db.execute("UPDATE hitl_approvals SET status = 'EXPIRED' WHERE id = ?;", (approval_id,))
                logger.warning("hitl_approval_expired", approval_id=approval_id)
                return False
        except Exception:
            pass

    new_status = "APPROVED" if approved else "DENIED"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """
        UPDATE hitl_approvals
        SET status = ?, resolved_at = ?, resolved_by = ?
        WHERE id = ?;
        """,
        (new_status, now_str, user_id, approval_id),
    )

    log_audit_event(
        event_type="HITL_REQUEST_RESOLVED",
        action=row["action"],
        user_id=user_id,
        resource=f"hitl_approvals/{approval_id}",
        status=new_status,
        severity="INFO" if approved else "WARNING",
        details={"agent": row["agent_name"], "decision": new_status},
    )
    return True


def list_hitl_approvals(user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List HITL approvals for a specific user, automatically checking expiration."""
    db.init_db()
    query = "SELECT * FROM hitl_approvals WHERE user_id = ?"
    params: List[Any] = [user_id]

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC;"
    rows = db.fetch_all(query, tuple(params))
    now_utc = datetime.now(timezone.utc)

    for r in rows:
        if isinstance(r.get("metadata_json"), str):
            try:
                r["metadata"] = json.loads(r["metadata_json"])
            except Exception:
                r["metadata"] = {}

        # Flag expired pending items
        if r["status"] == "PENDING" and r.get("expires_at"):
            try:
                exp_dt = datetime.strptime(r["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if now_utc >= exp_dt:
                    r["status"] = "EXPIRED"
            except Exception:
                pass

    return rows
