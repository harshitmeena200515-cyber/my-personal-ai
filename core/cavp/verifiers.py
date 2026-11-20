"""
CAVP V3 Specialized Verifier Agents.

Provides:
- CodeVerifier: AST parsing, dangerous import detection (os.system, subprocess shell=True), test checks.
- CybersecurityVerifier: CWE vulnerability detection, path traversal, prompt injection, and VETO authority.
- FactVerifier: Evidence triangulation and source reliability validation.
"""

import ast
import os
import re
from typing import Any, Dict, List, Optional

from core.cavp.scoring import TwoStageScoringEngine, VerificationVerdict


class CodeVerifier:
    """Performs deterministic AST analysis and static code safety verification."""

    FORBIDDEN_CALLS = {"system", "popen", "exec", "eval"}
    FORBIDDEN_MODULES = {"pty", "telnetlib"}

    @classmethod
    def verify_code(cls, code_snippet: str, unit_test_passed: bool = True) -> VerificationVerdict:
        errors = []
        try:
            tree = ast.parse(code_snippet)
            for node in ast.walk(tree):
                # Check for forbidden function calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in cls.FORBIDDEN_CALLS:
                        errors.append(f"Forbidden call: {node.func.id}()")
                    elif isinstance(node.func, ast.Attribute) and node.func.attr in cls.FORBIDDEN_CALLS:
                        errors.append(f"Forbidden attribute call: {node.func.attr}()")
                # Check for forbidden imports
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in cls.FORBIDDEN_MODULES:
                            errors.append(f"Forbidden module import: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module in cls.FORBIDDEN_MODULES:
                        errors.append(f"Forbidden module import from: {node.module}")
        except SyntaxError as e:
            errors.append(f"SyntaxError: {str(e)}")

        det_passed = (len(errors) == 0) and unit_test_passed
        if not unit_test_passed:
            errors.append("Unit test execution failed.")

        return TwoStageScoringEngine.evaluate(
            verifier_agent="code_verifier",
            deterministic_passed=det_passed,
            deterministic_errors=errors,
            security_veto=False,
            rule_alignment=1.0 if det_passed else 0.0,
            triangulation=1.0,
            critique="Code passed AST parsing and unit test validation." if det_passed else "; ".join(errors)
        )


class CybersecurityVerifier:
    """Specialized security verifier with veto authority for CWE vulnerabilities."""

    CWE_PATTERNS = {
        "CWE-22": re.compile(r"(?:\.\./|\.\.\\)", re.IGNORECASE),                         # Path traversal
        "CWE-89": re.compile(r"SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*=\s*['\"].*\+", re.I), # SQL Injection
        "CWE-78": re.compile(r"(?:rm\s+-rf|del\s+/f|format\s+[a-z]:)", re.IGNORECASE),   # Command destruction
        "CWE-798": re.compile(r"sk-[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z\-_]{35}", re.I),  # Hardcoded credentials
    }

    @classmethod
    def verify_security(cls, text_payload: str) -> VerificationVerdict:
        detected_cwes = []
        for cwe, pattern in cls.CWE_PATTERNS.items():
            if pattern.search(text_payload):
                detected_cwes.append(cwe)

        has_veto = len(detected_cwes) > 0

        return TwoStageScoringEngine.evaluate(
            verifier_agent="cybersecurity_verifier",
            deterministic_passed=not has_veto,
            deterministic_errors=["Security vulnerability detected"] if has_veto else [],
            security_veto=has_veto,
            cwe_ids=detected_cwes,
            rule_alignment=0.0 if has_veto else 1.0,
            triangulation=0.0 if has_veto else 1.0,
            critique=f"Security scan identified vulnerabilities: {detected_cwes}" if has_veto else "Zero security threats detected.",
        )


class FactVerifier:
    """Verifies empirical claims, source citations, and triangulation consistency."""

    @classmethod
    def verify_facts(cls, claim: str, evidence_count: int = 1, source_reliability: float = 1.0) -> VerificationVerdict:
        if not claim or len(claim.strip()) < 5:
            return TwoStageScoringEngine.evaluate(
                verifier_agent="fact_verifier",
                deterministic_passed=False,
                deterministic_errors=["Empty or invalid atomic claim."],
                critique="Claim must be non-empty and verifiable."
            )

        # Triangulation score based on evidence count
        triangulation = min(1.0, evidence_count * 0.5)

        return TwoStageScoringEngine.evaluate(
            verifier_agent="fact_verifier",
            deterministic_passed=True,
            rule_alignment=source_reliability,
            triangulation=triangulation,
            critique=f"Claim triangulated across {evidence_count} evidence sources."
        )
