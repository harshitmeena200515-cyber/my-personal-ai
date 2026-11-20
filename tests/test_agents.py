"""
Multi-Agent Intelligence Foundation Unit and Integration Tests (Milestone E).

Verifies:
  1. SharedContext blackboard, event timeline, and HITL approval queue.
  2. AgentRegistry discovery and intelligent intent routing.
  3. CodingAgent AST validation and code synthesis.
  4. ResearchAgent tool inspection and synthesis.
  5. CybersecurityAgent static AST security, secret detection, path traversal, risk scoring, and HITL gating.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import (
    AgentStatus,
    CodingAgent,
    CybersecurityAgent,
    ResearchAgent,
    RiskLevel,
    SharedContext,
    agent_registry,
    coding_agent,
    cybersec_agent,
    research_agent,
)


def test_shared_context_blackboard_and_hitl():
    """Verify SharedContext state storage, event logging, and HITL workflow."""
    ctx = SharedContext(user_id="test_user_001")

    # 1. Blackboard key-value operations
    ctx.set("framework", "FastAPI")
    ctx.set("max_tokens", 2048)
    assert ctx.get("framework") == "FastAPI"
    assert ctx.get("max_tokens") == 2048
    assert ctx.get("non_existent", "default_val") == "default_val"

    # 2. Event logging
    ctx.add_event("coding_agent", "code_generated", {"lines": 42})
    events = ctx.get_events()
    assert len(events) == 1
    assert events[0]["agent"] == "coding_agent"
    assert events[0]["data"]["lines"] == 42

    # 3. HITL approval request
    approval_id = ctx.request_human_approval(
        action="delete_database_records",
        agent_name="cybersec_agent",
        reason="Potentially destructive SQL command",
        risk_level="HIGH",
    )
    assert len(ctx.get_pending_approvals()) == 1
    assert ctx.get_pending_approvals()[0]["id"] == approval_id

    # 4. Resolve approval
    assert ctx.resolve_human_approval(approval_id, approved=True) is True
    assert len(ctx.get_pending_approvals()) == 0

    print("✅ test_shared_context_blackboard_and_hitl PASSED")


def test_agent_registry_and_routing():
    """Verify registry listing and intelligent task routing."""
    # 1. Check all 3 agents are registered
    assert agent_registry.get("coding_agent") is not None
    assert agent_registry.get("research_agent") is not None
    assert agent_registry.get("cybersec_agent") is not None

    agents = agent_registry.list_agents()
    assert len(agents) >= 3
    agent_names = [a["name"] for a in agents]
    assert "coding_agent" in agent_names
    assert "research_agent" in agent_names
    assert "cybersec_agent" in agent_names

    # 2. Routing checks
    # Code tasks -> coding_agent
    routed_code = agent_registry.route_task("code_generation", "Write a Python function to compute fibonacci")
    assert routed_code.name == "coding_agent"

    # Security tasks -> cybersec_agent
    routed_sec = agent_registry.route_task("general", "Audit this file for security vulnerabilities and CVEs")
    assert routed_sec.name == "cybersec_agent"

    # Research / System tasks -> research_agent
    routed_research = agent_registry.route_task("system_query", "What is the GPU and current date?")
    assert routed_research.name == "research_agent"

    print("✅ test_agent_registry_and_routing PASSED")


def test_coding_agent_ast_validation():
    """Verify CodingAgent static Python AST parsing."""
    agent = CodingAgent()

    # Valid Python code
    valid_code = "def add(a, b):\n    return a + b\n"
    res_valid = agent.validate_python_syntax(valid_code)
    assert res_valid["valid"] is True
    assert res_valid["error"] is None
    assert res_valid["node_count"] > 0

    # Invalid Python syntax
    invalid_code = "def broken_syntax(a, b:\n    return a +"
    res_invalid = agent.validate_python_syntax(invalid_code)
    assert res_invalid["valid"] is False
    assert "SyntaxError" in res_invalid["error"]

    print("✅ test_coding_agent_ast_validation PASSED")


def test_cybersecurity_agent_auditing_and_hitl():
    """Verify CybersecurityAgent security scanning, risk scoring, and HITL gating."""
    agent = CybersecurityAgent()
    ctx = SharedContext(user_id="test_user_sec")

    # 1. Clean code -> SAFE
    clean_code = "def calculate_area(r):\n    import math\n    return math.pi * r * r\n"
    audit_clean = agent.audit_code_security(clean_code)
    assert audit_clean["passed"] is True
    assert audit_clean["overall_risk"] == RiskLevel.SAFE

    # 2. Dangerous imports -> HIGH
    dangerous_code = "import subprocess\nsubprocess.run(['rm', '-rf', '/'])\n"
    audit_danger = agent.audit_code_security(dangerous_code)
    assert audit_danger["passed"] is False
    assert audit_danger["overall_risk"] == RiskLevel.HIGH
    assert any(f["type"] == "DANGEROUS_IMPORT" for f in audit_danger["findings"])

    # 3. Dangerous call -> CRITICAL
    critical_call = "user_input = '__import__(\"os\").system(\"calc\")'\neval(user_input)\n"
    audit_crit = agent.audit_code_security(critical_call)
    assert audit_crit["passed"] is False
    assert audit_crit["overall_risk"] == RiskLevel.CRITICAL
    assert any(f["type"] == "DANGEROUS_CALL" for f in audit_crit["findings"])

    # 4. Secret leak -> CRITICAL
    secret_code = "api_key = 'sk-live-1234567890abcdef12345'\n"
    audit_secret = agent.audit_code_security(secret_code)
    assert audit_secret["passed"] is False
    assert audit_secret["overall_risk"] == RiskLevel.CRITICAL
    assert any(f["type"] == "SECRET_LEAK" for f in audit_secret["findings"])

    # 5. Path traversal -> HIGH
    traversal_code = "filename = '../../etc/passwd'\nwith open(filename) as f: pass\n"
    audit_trav = agent.audit_code_security(traversal_code)
    assert audit_trav["passed"] is False
    assert audit_trav["overall_risk"] == RiskLevel.HIGH
    assert any(f["type"] == "PATH_TRAVERSAL" for f in audit_trav["findings"])

    # 6. Execute with high-risk code triggers HITL blocking
    ctx.set("last_generated_code", dangerous_code)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(agent.execute("Audit latest generated code", ctx))
    loop.close()

    assert result.status == AgentStatus.BLOCKED_AWAITING_APPROVAL
    assert result.risk_level == RiskLevel.HIGH
    assert len(ctx.get_pending_approvals()) == 1

    print("✅ test_cybersecurity_agent_auditing_and_hitl PASSED")


if __name__ == "__main__":
    test_shared_context_blackboard_and_hitl()
    test_agent_registry_and_routing()
    test_coding_agent_ast_validation()
    test_cybersecurity_agent_auditing_and_hitl()
    print("\nALL AGENT TESTS PASSED SUCCESSFULLY!")
