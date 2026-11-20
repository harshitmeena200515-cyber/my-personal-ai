"""
CAVP V3 Hierarchical Two-Stage Scoring Engine.

Provides:
- Stage 1: Deterministic non-negotiable checks (syntax, imports, AST security, CWE checks).
- Stage 2: Composite confidence scoring (DeterministicPass + RuleAlignment + Triangulation).
- Thresholds: >= 0.90 PASS, 0.70-0.89 PENDING_APPROVAL, < 0.70 FAIL.
- Cybersecurity Agent veto enforcement.
"""

from enum import Enum
from typing import Any, Dict, List, Optional


class VerdictStatus(str, Enum):
    PASS = "PASS"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    FAIL = "FAIL"


class RiskLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class VerificationVerdict:
    """Standardized verification verdict output by a verifier agent."""

    def __init__(
        self,
        verifier_agent: str,
        status: VerdictStatus,
        confidence: float,
        risk_level: RiskLevel,
        deterministic_passed: bool,
        critique: str,
        security_veto: bool = False,
        cwe_ids: Optional[List[str]] = None,
        evidence_references: Optional[List[str]] = None,
    ):
        self.verifier_agent = verifier_agent
        self.status = status
        self.confidence = round(confidence, 3)
        self.risk_level = risk_level
        self.deterministic_passed = deterministic_passed
        self.critique = critique
        self.security_veto = security_veto
        self.cwe_ids = cwe_ids or []
        self.evidence_references = evidence_references or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verifier_agent": self.verifier_agent,
            "status": self.status.value,
            "confidence": self.confidence,
            "risk_level": self.risk_level.value,
            "deterministic_passed": self.deterministic_passed,
            "security_veto": self.security_veto,
            "cwe_ids": self.cwe_ids,
            "critique": self.critique,
            "evidence_references": self.evidence_references,
        }


class TwoStageScoringEngine:
    """Evaluates Stage 1 deterministic gates before computing Stage 2 confidence."""

    PASS_THRESHOLD = 0.90
    ESCALATE_THRESHOLD = 0.70

    @classmethod
    def evaluate(
        cls,
        verifier_agent: str,
        deterministic_passed: bool,
        deterministic_errors: Optional[List[str]] = None,
        security_veto: bool = False,
        cwe_ids: Optional[List[str]] = None,
        rule_alignment: float = 1.0,
        triangulation: float = 1.0,
        critique: str = "",
        evidence_references: Optional[List[str]] = None,
    ) -> VerificationVerdict:
        """Execute two-stage hierarchical evaluation."""
        cwe_list = cwe_ids or []
        errors = deterministic_errors or []

        # STAGE 1: Deterministic Non-Negotiables
        if security_veto or len(cwe_list) > 0:
            critique_msg = f"SECURITY VETO: Critical vulnerabilities detected: {cwe_list}. {critique}".strip()
            return VerificationVerdict(
                verifier_agent=verifier_agent,
                status=VerdictStatus.FAIL,
                confidence=0.0,
                risk_level=RiskLevel.CRITICAL,
                deterministic_passed=False,
                security_veto=True,
                cwe_ids=cwe_list,
                critique=critique_msg,
                evidence_references=evidence_references,
            )

        if not deterministic_passed or len(errors) > 0:
            critique_msg = f"DETERMINISTIC FAILURE: Unit tests or static safety checks failed: {errors}. {critique}".strip()
            return VerificationVerdict(
                verifier_agent=verifier_agent,
                status=VerdictStatus.FAIL,
                confidence=0.0,
                risk_level=RiskLevel.HIGH,
                deterministic_passed=False,
                security_veto=False,
                cwe_ids=[],
                critique=critique_msg,
                evidence_references=evidence_references,
            )

        # STAGE 2: Composite Confidence Scoring
        # Confidence = 0.50 * DeterministicPass (1.0) + 0.30 * RuleAlignment + 0.20 * Triangulation
        det_score = 1.0
        rule_score = max(0.0, min(1.0, rule_alignment))
        tri_score = max(0.0, min(1.0, triangulation))

        confidence = (0.50 * det_score) + (0.30 * rule_score) + (0.20 * tri_score)

        if confidence >= cls.PASS_THRESHOLD:
            status = VerdictStatus.PASS
            risk = RiskLevel.NONE if confidence >= 0.95 else RiskLevel.LOW
        elif confidence >= cls.ESCALATE_THRESHOLD:
            status = VerdictStatus.PENDING_APPROVAL
            risk = RiskLevel.MEDIUM
        else:
            status = VerdictStatus.FAIL
            risk = RiskLevel.HIGH

        return VerificationVerdict(
            verifier_agent=verifier_agent,
            status=status,
            confidence=confidence,
            risk_level=risk,
            deterministic_passed=True,
            security_veto=False,
            cwe_ids=[],
            critique=critique or "All deterministic and rule-alignment verifications satisfied.",
            evidence_references=evidence_references,
        )
