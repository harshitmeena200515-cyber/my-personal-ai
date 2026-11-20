"""
Cybersecurity Agent and Zero-Trust Policy Engine for MY PERSONAL AI (Milestone E).

Implements:
- Static AST code and import security auditing.
- Secret and credential leak scanning.
- Path traversal and sandbox escape detection.
- Multi-tier risk scoring (CRITICAL, HIGH, MEDIUM, LOW, SAFE).
- Human-in-the-Loop (HITL) gating for destructive or high-risk actions.
"""

import ast
import re
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, AgentStatus, BaseAgent, RiskLevel
from agents.context import SharedContext
from core.logging import logger

DANGEROUS_CALLS = {
    "eval": "Direct arbitrary expression evaluation",
    "exec": "Direct arbitrary statement execution",
    "__import__": "Dynamic unconstrained module loading",
}

DANGEROUS_MODULES = {
    "subprocess": "Execution of arbitrary OS processes",
    "os.system": "Raw command injection risk",
    "os.popen": "Shell piping risk",
    "pickle": "Unsafe object deserialization / RCE",
    "shutil.rmtree": "Recursive filesystem destruction",
    "ctypes": "Unmanaged native memory manipulation",
}

SECRET_PATTERNS = [
    (re.compile(r"""(?i)(?:api_key|apikey|secret|token|password|passwd)\s*[:=]\s*['"][a-zA-Z0-9_\-\.]{8,}['"]"""), "Hardcoded credential/API key"),
    (re.compile(r"""-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"""), "Hardcoded Private Key"),
]

TRAVERSAL_PATTERN = re.compile(r"""(?:\.\.[/\\]|[/\\]\.\.)""")


class CybersecurityAgent(BaseAgent):
    """Autonomous Cybersecurity Auditor enforcing Zero-Trust boundaries and HITL gating."""

    def __init__(self):
        super().__init__(
            name="cybersec_agent",
            role="Cybersecurity Auditor & Zero-Trust Guardian",
            system_prompt=(
                "You are an expert cybersecurity auditor. Your role is to inspect code, configurations, and plans "
                "for security vulnerabilities, secret leakage, injection attacks, and sandbox escape attempts. "
                "Flag any violation with strict risk classifications."
            ),
            allowed_tools=["code_analyzer", "file_reader"],
            max_iterations=5,
        )

    def audit_code_security(self, code_str: str) -> Dict[str, Any]:
        """Perform deep static AST and regex security scanning on code."""
        findings: List[Dict[str, Any]] = []

        # 1. Regex check for secrets and credentials
        for pattern, desc in SECRET_PATTERNS:
            matches = pattern.findall(code_str)
            if matches:
                findings.append({
                    "type": "SECRET_LEAK",
                    "severity": RiskLevel.CRITICAL.value,
                    "description": desc,
                    "matches_count": len(matches),
                })

        # 2. Path Traversal Pattern Check
        if TRAVERSAL_PATTERN.search(code_str):
            findings.append({
                "type": "PATH_TRAVERSAL",
                "severity": RiskLevel.HIGH.value,
                "description": "Path traversal pattern (..) detected in string literal or code",
            })

        # 3. AST Inspection for dangerous calls and imports
        try:
            tree = ast.parse(code_str)
            for node in ast.walk(tree):
                # Check imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in DANGEROUS_MODULES:
                            findings.append({
                                "type": "DANGEROUS_IMPORT",
                                "severity": RiskLevel.HIGH.value,
                                "module": alias.name,
                                "description": DANGEROUS_MODULES[alias.name],
                                "line": node.lineno,
                            })
                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    if module_name in DANGEROUS_MODULES:
                        findings.append({
                            "type": "DANGEROUS_IMPORT",
                            "severity": RiskLevel.HIGH.value,
                            "module": module_name,
                            "description": DANGEROUS_MODULES[module_name],
                            "line": node.lineno,
                        })

                # Check function calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in DANGEROUS_CALLS:
                            findings.append({
                                "type": "DANGEROUS_CALL",
                                "severity": RiskLevel.CRITICAL.value,
                                "function": node.func.id,
                                "description": DANGEROUS_CALLS[node.func.id],
                                "line": node.lineno,
                            })
                    elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        full_call = f"{node.func.value.id}.{node.func.attr}"
                        if full_call in ("os.system", "os.popen", "subprocess.run", "subprocess.Popen", "subprocess.call", "shutil.rmtree"):
                            findings.append({
                                "type": "DANGEROUS_CALL",
                                "severity": RiskLevel.HIGH.value,
                                "function": full_call,
                                "description": f"Dangerous system call: {full_call}",
                                "line": node.lineno,
                            })
        except SyntaxError as e:
            findings.append({
                "type": "SYNTAX_ERROR",
                "severity": RiskLevel.LOW.value,
                "description": f"Code parsing failed: {e.msg}",
            })

        # 4. Determine overall risk level
        overall_risk = RiskLevel.SAFE
        severities = [f["severity"] for f in findings]
        if RiskLevel.CRITICAL.value in severities:
            overall_risk = RiskLevel.CRITICAL
        elif RiskLevel.HIGH.value in severities:
            overall_risk = RiskLevel.HIGH
        elif RiskLevel.MEDIUM.value in severities:
            overall_risk = RiskLevel.MEDIUM
        elif RiskLevel.LOW.value in severities:
            overall_risk = RiskLevel.LOW

        return {
            "passed": len(findings) == 0,
            "overall_risk": overall_risk,
            "findings_count": len(findings),
            "findings": findings,
        }

    async def execute(self, task: str, context: SharedContext) -> AgentResult:
        """Audit the given task or the latest code in the shared blackboard."""
        context.add_event(self.name, "audit_started", {"task": task})
        logger.info("cybersec_agent_auditing", task=task[:60])

        # Retrieve target code from blackboard if present, or use task text
        target_code = context.get("last_generated_code") or task
        audit_result = self.audit_code_security(target_code)
        risk = audit_result["overall_risk"]

        # Store audit report in blackboard
        context.set("security_audit", audit_result)

        # Trigger Human-in-the-Loop if risk is HIGH or CRITICAL
        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            approval_id = context.request_human_approval(
                action="execute_high_risk_code",
                agent_name=self.name,
                reason=f"Identified {audit_result['findings_count']} security violation(s): {audit_result['findings']}",
                risk_level=risk.value,
                metadata=audit_result,
            )
            context.add_event(self.name, "audit_blocked_awaiting_hitl", {"approval_id": approval_id})

            summary = (
                f"🚨 CYBERSECURITY ALERT: Operation blocked. Risk Level: {risk.value}.\n"
                f"Violations detected: {len(audit_result['findings'])}\n"
                f"Action queued for Human-in-the-Loop approval (ID: {approval_id})."
            )
            return AgentResult(
                agent_name=self.name,
                task_id=context.task_id,
                status=AgentStatus.BLOCKED_AWAITING_APPROVAL,
                output=summary,
                risk_level=risk,
                metadata={"approval_id": approval_id, "audit": audit_result},
            )

        context.add_event(self.name, "audit_passed", {"risk": risk.value})
        summary = f"🛡️ Cybersecurity Audit Passed. Risk Level: {risk.value}. Zero critical violations detected."

        return AgentResult(
            agent_name=self.name,
            task_id=context.task_id,
            status=AgentStatus.SUCCESS,
            output=summary,
            risk_level=risk,
            metadata={"audit": audit_result},
        )
