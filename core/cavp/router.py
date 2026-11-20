"""
CAVP V3 Star-Topology Orchestrator Router & Action Card Escalation Engine.

Provides:
- Orchestrator-mediated routing: Strict star-topology, zero peer-to-peer leaks.
- Action Card creation in app.db (hitl_approvals) when security veto or PENDING_APPROVAL occurs.
- Session key management and monotonic nonce replay defense.
"""

import os
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.cavp.envelope import EphemeralVerificationEnvelope
from core.cavp.scoring import RiskLevel, VerdictStatus, VerificationVerdict
from core.cavp.verifiers import CodeVerifier, CybersecurityVerifier, FactVerifier
from core.dpapi import dpapi_encrypt, dpapi_decrypt
from core.logging import logger
from data.db import db


class CAVPRouter:
    """Central Star-Topology Router for Cross-Agent Verification."""

    def __init__(self, db_instance=None):
        self.db = db_instance or db
        # Protect ephemeral session HMAC key in RAM via Windows DPAPI (ADR-004 / Phase 7)
        self._encrypted_session_key: bytes = dpapi_encrypt(secrets.token_bytes(32))
        self._nonces: Dict[str, int] = {}  # Track last seen nonce per agent

    def _get_session_key(self) -> bytes:
        """Decrypt session HMAC key from Windows DPAPI buffer."""
        return dpapi_decrypt(self._encrypted_session_key)

    def rotate_session_key(self) -> None:
        """Rotate transient session HMAC key and re-encrypt under DPAPI."""
        self._encrypted_session_key = dpapi_encrypt(secrets.token_bytes(32))
        logger.info("cavp_session_key_rotated")

    def create_envelope(
        self,
        task_id: str,
        user_id: str,
        originator_agent: str,
        target_verifier: str,
        artifact_type: str,
        artifact_payload: Any,
        ttl_ms: int = 3000,
    ) -> EphemeralVerificationEnvelope:
        """Construct, deep-freeze, and cryptographically sign an immutable envelope."""
        last_nonce = self._nonces.get(originator_agent, int(time.time() * 1000))
        current_nonce = max(int(time.time() * 1000), last_nonce + 1)
        self._nonces[originator_agent] = current_nonce

        envelope = EphemeralVerificationEnvelope(
            task_id=task_id,
            user_id=user_id,
            originator_agent=originator_agent,
            target_verifier=target_verifier,
            artifact_type=artifact_type,
            artifact_payload=artifact_payload,
            ttl_ms=ttl_ms,
            nonce=current_nonce,
        )
        envelope.sign(self._get_session_key())
        return envelope

    def route_and_verify(
        self,
        envelope: EphemeralVerificationEnvelope,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[VerificationVerdict, Optional[str]]:
        """
        Verify envelope authenticity, route to target verifier, and escalate Action Card if needed.
        Returns: (VerificationVerdict, action_card_id or None)
        """
        # 1. Verify envelope authenticity & TTL
        if not envelope.verify(self._get_session_key()):
            logger.warning("cavp_envelope_verification_failed", envelope_id=envelope.envelope_id)
            verdict = VerificationVerdict(
                verifier_agent="router_auth",
                status=VerdictStatus.FAIL,
                confidence=0.0,
                risk_level=RiskLevel.CRITICAL,
                deterministic_passed=False,
                security_veto=True,
                critique="Envelope authentication failed or TTL expired (possible tampering or replay)."
            )
            card_id = self._escalate_action_card(envelope, verdict, "TAMPER_DETECTED")
            return verdict, card_id

        # 2. Dispatch to designated verifier
        target = envelope.target_verifier
        payload = envelope.artifact_payload

        if target == "code_verifier":
            code = payload if isinstance(payload, str) else str(payload.get("code", ""))
            unit_passed = True
            if extra_context and "unit_passed" in extra_context:
                unit_passed = bool(extra_context["unit_passed"])
            verdict = CodeVerifier.verify_code(code, unit_test_passed=unit_passed)

        elif target == "cybersecurity_verifier":
            text_to_scan = str(payload)
            verdict = CybersecurityVerifier.verify_security(text_to_scan)

        elif target == "fact_verifier":
            claim = payload if isinstance(payload, str) else str(payload.get("claim", ""))
            ev_count = extra_context.get("evidence_count", 1) if extra_context else 1
            rel = extra_context.get("source_reliability", 1.0) if extra_context else 1.0
            verdict = FactVerifier.verify_facts(claim, evidence_count=ev_count, source_reliability=rel)

        else:
            verdict = VerificationVerdict(
                verifier_agent=target,
                status=VerdictStatus.FAIL,
                confidence=0.0,
                risk_level=RiskLevel.HIGH,
                deterministic_passed=False,
                critique=f"Unknown target verifier: {target}"
            )

        # 3. Check for escalation triggers (Security Veto or PENDING_APPROVAL)
        action_card_id = None
        if verdict.security_veto:
            action_card_id = self._escalate_action_card(envelope, verdict, reason="SECURITY_VETO")
        elif verdict.status == VerdictStatus.PENDING_APPROVAL:
            action_card_id = self._escalate_action_card(envelope, verdict, reason="CONFIDENCE_ESCALATION")

        return verdict, action_card_id

    def _escalate_action_card(
        self,
        envelope: EphemeralVerificationEnvelope,
        verdict: VerificationVerdict,
        reason: str
    ) -> str:
        """Create a cryptographically traceable HITL Action Card in app.db."""
        import json
        card_id = str(uuid.uuid4())
        prompt = (
            f"Action Required ({reason}): Agent '{envelope.originator_agent}' produced artifact '{envelope.artifact_type}'. "
            f"Verifier '{verdict.verifier_agent}' issued {verdict.status.value} (Risk: {verdict.risk_level.value}, "
            f"Confidence: {verdict.confidence}). Critique: {verdict.critique}"
        )
        
        # Insert into hitl_approvals table conforming to 003_security_audit_and_hitl.sql
        query = """
        INSERT INTO hitl_approvals (id, user_id, agent_name, action, reason, risk_level, status, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, CURRENT_TIMESTAMP)
        """
        metadata = json.dumps(verdict.to_dict())
        self.db.execute(query, (card_id, envelope.user_id, envelope.originator_agent, f"CAVP_{reason}", prompt, verdict.risk_level.value, metadata))
        logger.info("cavp_action_card_created", id=card_id, user_id=envelope.user_id, reason=reason)
        return card_id


# Global singleton router
cavp_router = CAVPRouter()
