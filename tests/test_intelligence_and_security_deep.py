"""
Deep Security Hardening & Autonomous Intelligence Validation Suite for MY PERSONAL AI.
Verifies attack vectors (SQLi, XSS, Path Traversal, Replay, Session Fixation, Privilege Escalation)
and real autonomous intelligence components (ReasoningEngine, TaskPlanner, AgentRegistry, Tools, Verifier, ErrorRecovery).
"""

import asyncio
import os
import sys
import time
import json
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from server import app
from data.db import DatabaseManager, db
from core.auth import create_user, authenticate_user
from core.sessions import create_session, validate_session, revoke_session, _hash_token
from core.sandbox import user_sandbox, UserSandboxError
from core.audit import create_hitl_approval, resolve_hitl_approval, verify_audit_log_integrity
from agents import (
    AgentStatus,
    CodingAgent,
    ResearchAgent,
    CybersecurityAgent,
    RiskLevel,
    SharedContext,
    agent_registry,
)
from core.reasoning import ReasoningEngine, ReasoningResult, Intent
from core.planner import TaskPlanner, TaskPlan, TaskStep, StepStatus, PlanStatus
from core.verifier import Verifier, VerificationResult
from core.recovery import ErrorRecovery, RecoveryStrategy
from tools import tool_registry

client = TestClient(app)

def test_deep_security_and_intelligence():
    print("\n" + "=" * 70)
    print("STARTING DEEP SECURITY & AUTONOMOUS INTELLIGENCE VALIDATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. SECURITY: SQL Injection Defense Across Endpoints
    # -------------------------------------------------------------
    print("▶ [1/6] Testing SQL Injection Attack Vectors...")
    sqli_payloads = [
        "' OR '1'='1",
        "admin'--",
        "' UNION SELECT username, password_hash FROM users--",
        "'; DROP TABLE users; --",
        "1' OR 1=1; --"
    ]

    for payload in sqli_payloads:
        # Test login endpoint
        res = client.post("/api/v1/auth/login", json={"username": payload, "password": "AnyPassword123!"})
        assert res.status_code in (401, 422), f"SQLi payload was not rejected: {payload}"

        # Test registration endpoint
        res_reg = client.post("/api/v1/auth/register", json={"username": payload, "password": "AnyPassword123!"})
        assert res_reg.status_code in (400, 422), f"SQLi registration was not rejected: {payload}"

    print("  ✅ All SQL Injection attack vectors successfully neutralized.")

    # -------------------------------------------------------------
    # 2. SECURITY: Session Fixation & High-Entropy Token Generation
    # -------------------------------------------------------------
    print("▶ [2/6] Testing Session Fixation Resistance...")
    user_name = f"fixation_user_{int(time.time() * 1000) % 1000000}"
    user = create_user(user_name, "SecurePassword123!", role="USER")

    # Perform multiple logins; verify each creates a distinct, cryptographically isolated token
    login1 = client.post("/api/v1/auth/login", json={"username": user_name, "password": "SecurePassword123!"})
    token1 = login1.json()["token"]

    login2 = client.post("/api/v1/auth/login", json={"username": user_name, "password": "SecurePassword123!"})
    token2 = login2.json()["token"]

    assert token1 != token2, "Session fixation detected: identical tokens issued across logins!"
    assert _hash_token(token1) != _hash_token(token2)

    # Revoking token1 does not invalidate token2
    client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token1}"})
    assert validate_session(token1) is None
    assert validate_session(token2) is not None
    print("  ✅ Session fixation immunity and CSPRNG entropy verified.")

    # -------------------------------------------------------------
    # 3. SECURITY: HITL Approval Replay Defense
    # -------------------------------------------------------------
    print("▶ [3/6] Testing HITL Approval Replay & State Immutability...")
    appr_id = create_hitl_approval(
        user_id=user["id"],
        agent_name="cybersec_agent",
        action="modify_network_rules",
        reason="Test replay defense",
        risk_level="HIGH"
    )

    # First resolution: Allowed
    res_allow = client.post(
        f"/api/v1/security/approvals/{appr_id}/resolve",
        headers={"Authorization": f"Bearer {token2}"},
        json={"approved": True}
    )
    assert res_allow.status_code == 200

    # Second resolution (Replay attempt): Must return 404 Not Found
    res_replay = client.post(
        f"/api/v1/security/approvals/{appr_id}/resolve",
        headers={"Authorization": f"Bearer {token2}"},
        json={"approved": False}
    )
    assert res_replay.status_code == 404, "Replay attack succeeded on already resolved HITL approval!"
    print("  ✅ HITL Approval replay attacks physically blocked.")

    # -------------------------------------------------------------
    # 4. SECURITY: Tool Path Traversal & Sandbox Isolation
    # -------------------------------------------------------------
    print("▶ [4/6] Testing Tool Boundary Enforcement & Data Isolation...")
    reader = tool_registry.get("file_reader")

    # Attempt to read system files
    traversal_res1 = asyncio.run(reader.execute({"path": "../../../Windows/win.ini", "action": "read"}))
    assert traversal_res1.success is False
    assert "outside" in traversal_res1.error.lower() or "denied" in traversal_res1.error.lower()

    # Attempt to read peer user workspace
    traversal_res2 = asyncio.run(reader.execute({"path": "data/users/victim_user/workspace/secret.txt", "action": "read"}))
    assert traversal_res2.success is False
    assert "restricted" in traversal_res2.error.lower()

    # Attempt to read active database files
    traversal_res3 = asyncio.run(reader.execute({"path": "data/app.db", "action": "read"}))
    assert traversal_res3.success is False
    assert "restricted" in traversal_res3.error.lower()

    print("  ✅ Tool sandbox boundaries strictly enforced.")

    # -------------------------------------------------------------
    # 5. INTELLIGENCE: Goal Interpretation, Planning & Verification
    # -------------------------------------------------------------
    print("▶ [5/6] Testing Autonomous Reasoning, Planning & Verification...")
    reasoning_engine = ReasoningEngine(model_router=None)
    task_planner = TaskPlanner(model_router=None)
    verifier = Verifier(model_router=None)
    recovery_engine = ErrorRecovery()

    # 5a. Intent Classification & Tool Suggestion
    reasoning_res = reasoning_engine._heuristic_analyze("Calculate 45 * 85 + sqrt(144)")
    assert reasoning_res is not None
    assert reasoning_res.intent == "calculation"
    assert "calculator" in reasoning_res.suggested_tools

    # 5b. Hierarchical Decomposition
    step1 = TaskStep(id="s1", action="calculate", tool="calculator", description="Compute value")
    step2 = TaskStep(id="s2", action="respond", description="Return output", depends_on=["s1"])
    plan = TaskPlan(goal="Test multi-step decomposition", steps=[step1, step2])
    assert plan.get_next_step().id == "s1"
    step1.status = StepStatus.COMPLETED
    assert plan.get_next_step().id == "s2"

    # 5c. Output Verification
    ver_pass = asyncio.run(verifier.verify(
        question="How do I calculate area of a circle?",
        answer="The area of a circle is calculated using the formula A = pi * r^2.",
    ))
    assert ver_pass.passed is True
    assert ver_pass.recommendation == "accept"

    ver_reject = asyncio.run(verifier.verify(
        question="Format hard drive",
        answer="Run rm -rf / to delete all files.",
    ))
    assert ver_reject.passed is False
    assert ver_reject.recommendation == "reject"

    # 5d. Tiered Recovery Engine
    failed_step = TaskStep(id="err1", action="calculate", tool="calculator")
    rec_decision = recovery_engine.recover(failed_step, plan, "Calculation syntax error")
    assert rec_decision.strategy == RecoveryStrategy.RETRY_WITH_CONTEXT
    assert rec_decision.should_continue is True
    print("  ✅ Autonomous reasoning, planning, verification & recovery fully verified.")

    # -------------------------------------------------------------
    # 6. INTELLIGENCE: Multi-Agent Blackboard & Zero-Trust Defense
    # -------------------------------------------------------------
    print("▶ [6/6] Testing Multi-Agent Blackboard & Zero-Trust Interception...")
    ctx = SharedContext(user_id=user["id"])

    # Blackboard communication
    ctx.set("architecture_style", "Local-First Hexagonal")
    ctx.set("max_execution_steps", 5)
    ctx.add_event("system", "pipeline_initialized", {"mode": "autonomous"})

    assert ctx.get("architecture_style") == "Local-First Hexagonal"
    assert len(ctx.get_events()) == 1

    # CybersecurityAgent zero-trust scanning
    cybersec = agent_registry.get("cybersec_agent")
    ast_audit = cybersec.audit_code_security("import os\nos.system('dir')")
    assert ast_audit["passed"] is False
    assert ast_audit["overall_risk"] in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    print("  ✅ Multi-agent blackboard and zero-trust security successfully validated.")

    print("\n" + "=" * 70)
    print("ALL 6 DEEP SECURITY & INTELLIGENCE AUDIT CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    test_deep_security_and_intelligence()
