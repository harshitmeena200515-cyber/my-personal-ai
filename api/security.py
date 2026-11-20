"""
Security, Audit Log, and Human-in-the-Loop (HITL) Endpoints for MY PERSONAL AI.

Enforces:
- Strict user authentication and role-based access control (RBAC).
- Human confirmation of high-risk actions.
- Access to immutable audit trail records.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.auth import get_current_user
from core.audit import (
    create_hitl_approval,
    list_audit_logs,
    list_hitl_approvals,
    log_audit_event,
    resolve_hitl_approval,
    verify_audit_log_integrity,
)
from agents import cybersec_agent

router = APIRouter(prefix="/api/v1/security", tags=["Security & HITL"])


class ResolveApprovalRequest(BaseModel):
    approved: bool = Field(..., description="True to authorize execution, False to deny")


class CodeScanRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Source code to analyze for vulnerabilities")


@router.get("/approvals", response_model=List[Dict[str, Any]], summary="List HITL approvals")
async def get_approvals(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Enumerate HITL approvals requiring human authorization."""
    return list_hitl_approvals(user_id=current_user["user_id"], status=status_filter)


@router.post("/approvals/{approval_id}/resolve", summary="Approve or deny a HITL action")
async def resolve_approval(
    approval_id: str,
    req: ResolveApprovalRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Authorize or reject a pending security/agent action."""
    success = resolve_hitl_approval(
        approval_id=approval_id,
        user_id=current_user["user_id"],
        approved=req.approved,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found or already resolved.",
        )
    return {
        "message": f"Approval {approval_id} {'AUTHORIZED' if req.approved else 'DENIED'} successfully.",
        "status": "APPROVED" if req.approved else "DENIED",
    }


@router.get("/audit-logs", response_model=List[Dict[str, Any]], summary="View security audit trail")
async def get_audit_logs(
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """View immutable security audit log entries. OWNER sees all logs, USER sees their own."""
    user_filter = None if current_user.get("role") == "OWNER" else current_user["user_id"]
    return list_audit_logs(
        user_id=user_filter,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )


@router.get("/audit-logs/verify", summary="Verify cryptographic audit trail integrity")
async def verify_audit_trail(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Run cryptographic SHA-256 hash chain verification over the entire audit log."""
    return verify_audit_log_integrity()


@router.post("/scan-code", summary="Perform static cybersecurity audit on code")
async def scan_code(
    req: CodeScanRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Scan source code for dangerous imports, calls, secrets, and traversal vulnerabilities."""
    result = cybersec_agent.audit_code_security(req.code)
    log_audit_event(
        event_type="CODE_SCAN",
        action="scan_code",
        user_id=current_user["user_id"],
        severity=result["overall_risk"].value,
        details={"findings_count": result["findings_count"], "passed": result["passed"]},
    )
    return {
        "passed": result["passed"],
        "overall_risk": result["overall_risk"].value,
        "findings_count": result["findings_count"],
        "findings": result["findings"],
    }
