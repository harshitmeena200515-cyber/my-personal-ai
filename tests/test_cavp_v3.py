"""
Unit and integration tests for Cross-Agent Verification Protocol (CAVP V3 / Phase 6).

Verifies:
1. Recursive deep-freeze immutability.
2. Cryptographic signature and tampering detection.
3. Two-Stage hierarchical scoring (deterministic gates first).
4. CodeVerifier AST and forbidden import/call detection.
5. CybersecurityVerifier CWE detection and VETO escalation to Action Cards.
6. Star-Topology routing and TTL expiry.
"""

import sys
import tempfile
import time
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.cavp.envelope import EphemeralVerificationEnvelope, deep_freeze
from core.cavp.scoring import RiskLevel, TwoStageScoringEngine, VerdictStatus
from core.cavp.verifiers import CodeVerifier, CybersecurityVerifier, FactVerifier
from core.cavp.router import CAVPRouter
from data.db import DatabaseManager


def test_deep_freeze_immutability():
    """Verify recursive deep freezing prevents in-memory tampering."""
    payload = {"code": "def add(a, b): return a + b", "nested": [1, 2, {"key": "val"}]}
    frozen = deep_freeze(payload)

    # Dictionary should be MappingProxyType
    try:
        frozen["code"] = "modified"
        assert False, "Should raise TypeError on dict modification"
    except TypeError:
        pass

    # Nested list should be tuple
    try:
        frozen["nested"].append(3)
        assert False, "Should raise AttributeError on tuple modification"
    except AttributeError:
        pass

    print("✅ test_deep_freeze_immutability PASSED")


def test_envelope_cryptographic_integrity():
    """Verify HMAC-SHA256 signing and tamper detection."""
    secret_key = b"super_secret_session_key_32_bytes!!"
    env = EphemeralVerificationEnvelope(
        task_id="t-1",
        user_id="u-1",
        originator_agent="coder",
        target_verifier="code_verifier",
        artifact_type="code_snippet",
        artifact_payload="x = 10",
        ttl_ms=3000,
    )
    sig = env.sign(secret_key)
    assert len(sig) == 64, "Signature must be 64-char hex SHA256"
    assert env.verify(secret_key), "Valid signature must verify successfully"

    # Wrong key fails
    assert not env.verify(b"wrong_key_1234567890123456789012345"), "Wrong key must fail verification"

    # Expired TTL fails
    assert not env.verify(secret_key, current_time=time.time() + 10.0), "Expired TTL must fail verification"
    print("✅ test_envelope_cryptographic_integrity PASSED")


def test_code_verifier_deterministic_gates():
    """Verify CodeVerifier detects dangerous calls and forbidden imports."""
    # 1. Clean code
    clean_code = "def greet(name):\n    return f'Hello, {name}'\n"
    v_clean = CodeVerifier.verify_code(clean_code, unit_test_passed=True)
    assert v_clean.status == VerdictStatus.PASS
    assert v_clean.confidence >= 0.90
    assert v_clean.deterministic_passed is True

    # 2. Forbidden call (eval)
    eval_code = "def run_input(x):\n    return eval(x)\n"
    v_eval = CodeVerifier.verify_code(eval_code, unit_test_passed=True)
    assert v_eval.status == VerdictStatus.FAIL
    assert v_eval.confidence == 0.0
    assert v_eval.deterministic_passed is False
    assert "Forbidden call: eval()" in v_eval.critique

    # 3. Unit test failure overrides clean syntax
    v_test_fail = CodeVerifier.verify_code(clean_code, unit_test_passed=False)
    assert v_test_fail.status == VerdictStatus.FAIL
    assert v_test_fail.confidence == 0.0
    assert "Unit test execution failed" in v_test_fail.critique
    print("✅ test_code_verifier_deterministic_gates PASSED")


def test_cybersecurity_verifier_veto_and_action_card():
    """Verify CybersecurityVerifier detects CWE vulnerabilities and halts with VETO."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_cavp.db"
        db_mgr = DatabaseManager(str(db_path))
        db_mgr.run_migrations()

        user_id = str(uuid.uuid4())
        db_mgr.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?);",
            (user_id, "harshit_owner", "$argon2id$mockhash")
        )

        router = CAVPRouter(db_mgr)

        # Injected SQL payload
        malicious_payload = "SELECT * FROM users WHERE username = 'admin' + ' OR 1=1';"
        env = router.create_envelope(
            task_id="t-sec",
            user_id=user_id,
            originator_agent="research_agent",
            target_verifier="cybersecurity_verifier",
            artifact_type="query_draft",
            artifact_payload=malicious_payload,
        )

        verdict, action_card_id = router.route_and_verify(env)

        assert verdict.security_veto is True, "Must trigger security veto"
        assert verdict.status == VerdictStatus.FAIL
        assert verdict.risk_level == RiskLevel.CRITICAL
        assert "CWE-89" in verdict.cwe_ids
        assert action_card_id is not None, "Must escalate an Action Card for owner"

        # Verify Action Card in app.db
        card = db_mgr.fetch_one("SELECT * FROM hitl_approvals WHERE id = ?;", (action_card_id,))
        assert card is not None
        assert card["user_id"] == user_id
        assert card["action"] == "CAVP_SECURITY_VETO"
        assert "CWE-89" in card["reason"]
        print("✅ test_cybersecurity_verifier_veto_and_action_card PASSED")


def test_fact_verifier_triangulation():
    """Verify FactVerifier scores based on evidence triangulation."""
    # Well-triangulated claim (2 sources)
    v_high = FactVerifier.verify_facts("Ollama runs on port 11434 by default", evidence_count=2, source_reliability=1.0)
    assert v_high.status == VerdictStatus.PASS
    assert v_high.confidence >= 0.90

    # Low-evidence claim (1 source, lower reliability)
    v_med = FactVerifier.verify_facts("Hypothetical unverified event", evidence_count=1, source_reliability=0.7)
    assert v_med.status == VerdictStatus.PENDING_APPROVAL
    assert 0.70 <= v_med.confidence < 0.90
    print("✅ test_fact_verifier_triangulation PASSED")


if __name__ == "__main__":
    test_deep_freeze_immutability()
    test_envelope_cryptographic_integrity()
    test_code_verifier_deterministic_gates()
    test_cybersecurity_verifier_veto_and_action_card()
    test_fact_verifier_triangulation()
    print("\nALL PHASE 6 CAVP V3 TESTS PASSED 100%!")
